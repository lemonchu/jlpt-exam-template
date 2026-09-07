"""Real group flow: no overprinting, orphaned starts, or stale mirrored origins."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from component_layout import ComponentLayout
from rule_layout import RuleLayout
from test_written_rules import Catalog


class SamePageGroupTests(unittest.TestCase):
    def layout(self, layout_type=RuleLayout, **page):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        reference = SimpleNamespace(profile=ROOT / 'profiles/n1-original', resolved={}, ledger=[])
        return layout_type(Catalog(), {'page': {'body_bottom': 783, **page}, 'sidebar': False},
                           ROOT / 'resources', directory.name, reference)

    @staticmethod
    def group(identifier='V1', **item):
        return {'id': identifier, 'kind': 'choice', 'title': '問題１',
                'instruction': '正しいものを選びなさい。', 'items': [
                    {'id': identifier + '-q', 'prompt': 'これは問題です。',
                     'options': ['日本', '学校', '電車', '会社'], **item},
                ]}

    def seed(self, layout, cursor=None):
        layout.render_group(self.group(), {'sidebar': False})
        if cursor is not None:
            layout.y = cursor

    def test_second_group_continues_below_previous_content(self):
        layout = self.layout()
        self.seed(layout)
        cursor, glyphs = layout.y, len(layout.semantic_glyphs)
        before = deepcopy(layout.page['commands'])
        layout.render_group(self.group('V2'), {'new_page': False, 'sidebar': False})
        self.assertEqual(len(layout.pages), 1)
        self.assertEqual(layout.page['commands'][:len(before)], before)
        self.assertEqual(layout.page['group_ids'], ['V1', 'V2'])
        self.assertGreater(min(glyph['y'] for glyph in layout.semantic_glyphs[glyphs:]), cursor)
        self.assertAlmostEqual(layout.semantic_glyphs[glyphs]['y'],
                               cursor + layout.leading + 12.6201)
        self.assertEqual([record['pages'] for record in layout.item_records], [[1], [1]])

    def test_not_enough_room_moves_heading_and_question_without_touching_old_page(self):
        layout = self.layout()
        self.seed(layout, 710)
        original, glyphs = deepcopy(layout.page), len(layout.semantic_glyphs)
        layout.render_group(self.group('V2'), {'new_page': False, 'sidebar': False})
        self.assertEqual(len(layout.pages), 2)
        self.assertEqual(layout.pages[0], original)
        self.assertEqual(layout.item_records[-1]['pages'], [2])
        first = layout.semantic_glyphs[glyphs]
        self.assertAlmostEqual(first['y'], layout.top + 12.6201)
        self.assertAlmostEqual(first['x'], layout.page_left(layout.n()))
        self.assertEqual(first['page_ref'], id(layout.pages[1]))

    def test_first_choice_uses_the_preflight_line_plan_once(self):
        layout = self.layout()
        self.seed(layout)
        with patch.object(layout, 'choice_metrics', wraps=layout.choice_metrics) as measure:
            layout.render_group(self.group('V2'), {'new_page': False, 'sidebar': False})
        self.assertEqual(measure.call_count, 1)

    def test_long_first_question_can_split_without_stranding_its_heading(self):
        layout = self.layout()
        self.seed(layout, 690)
        group = self.group('V2', prompt='日' * 1000)
        glyphs = len(layout.semantic_glyphs)
        layout.render_group(group, {'new_page': False, 'sidebar': False})
        heading_page = layout.semantic_glyphs[glyphs]['page_ref']
        first_body = next(glyph for glyph in layout.semantic_glyphs[glyphs:]
                          if glyph['char'] == '日' and glyph['role'] is None)
        self.assertEqual(first_body['page_ref'], heading_page)
        self.assertGreater(len(layout.item_records[-1]['pages']), 1)

    def test_group_gap_is_configurable_but_negative_is_invalid(self):
        layout = self.layout()
        self.seed(layout)
        cursor, glyphs = layout.y, len(layout.semantic_glyphs)
        layout.render_group(self.group('V2'), {'new_page': False, 'group_gap': 40, 'sidebar': False})
        self.assertAlmostEqual(layout.semantic_glyphs[glyphs]['y'], cursor + 40 + 12.6201)
        with self.assertRaisesRegex(ValueError, 'group_gap'):
            layout.render_group(self.group('V3'), {'new_page': False, 'group_gap': -1})

    def test_ordering_heading_and_example_move_as_one_unit(self):
        layout = self.layout()
        group = next(group for group in yaml.safe_load(
            (ROOT / 'content/paper-a/G.yaml').read_text())['groups']
                     if group['kind'] == 'word_order')
        group['items'] = group['items'][:1]
        layout.render_group(self.group('G5'), {'sidebar': False})
        layout.y = 500
        original = deepcopy(layout.page)
        layout.render_group(group, {'new_page': False, 'sidebar': False})
        self.assertEqual(len(layout.pages), 2)
        self.assertEqual(layout.pages[0], original)
        self.assertTrue(layout.component_audit[-1]['ordering_heading_template'])
        self.assertTrue(layout.component_audit[-1]['ordering_example_template'])
        self.assertEqual(layout.item_records[-1]['pages'], [2])

    def test_section_change_and_explicit_page_side_still_take_precedence(self):
        layout = self.layout()
        self.seed(layout)
        layout.render_group(self.group('G5'), {'new_page': False, 'sidebar': False})
        self.assertEqual(len(layout.pages), 2)
        layout.render_group(self.group('G6'), {'new_page': False, 'start_on': 'right', 'sidebar': False})
        self.assertEqual(len(layout.pages), 3)

    def test_long_opening_frames_keep_their_first_text_below_the_heading(self):
        for section, kind, paired in (('R', 'reading', False), ('R', 'reading', True),
                                      ('G', 'cloze', False)):
            with self.subTest(section=section, paired=paired):
                layout = self.layout()
                layout.render_group(self.group(section + '1'), {'sidebar': False})
                layout.y = 250
                box = {'type': 'box', 'blocks': [{'type': 'paragraph', 'text': '日' * 1040}]}
                stimulus = ([{'type': 'heading', 'text': 'A'}] if paired else []) + [box]
                group = {'id': section + '2', 'kind': kind, 'title': '問題２',
                         'instruction': '文章を読んでください。',
                         'items': [{'id': 'article', 'stimulus': stimulus, 'questions': []}]}
                start = len(layout.semantic_glyphs)
                layout.render_group(group, {'new_page': False, 'sidebar': False})
                added = layout.semantic_glyphs[start:]
                first_text = next(glyph for glyph in added if glyph['char'] == '日')
                self.assertEqual(first_text['page_ref'], added[0]['page_ref'])
                self.assertGreater(first_text['y'], added[0]['y'])
                self.assertGreater(len(layout.pages), 1)

    def test_negative_body_offset_cannot_pull_continued_content_into_the_heading(self):
        layout = self.layout()
        self.seed(layout)
        before = deepcopy(layout.page)
        with self.assertRaisesRegex(ValueError, 'nonnegative body_start_adjust'):
            layout.render_group(self.group('V2'), {'new_page': False, 'body_start_adjust': -10})
        self.assertEqual(layout.page, before)

    def test_legacy_mode_rejects_unsafe_continuation_before_replacing_a_page(self):
        layout = self.layout(ComponentLayout)
        config = {'use_measured': False, '_use_measured_heading': False, 'sidebar': False}
        layout.render_group(self.group(), config)
        original = deepcopy(layout.page)
        with self.assertRaisesRegex(ValueError, 'default rules mode'):
            layout.render_group(self.group('V2'), dict(config, new_page=False))
        self.assertEqual(layout.page, original)


if __name__ == '__main__':
    unittest.main()
