"""Listening group continuation uses real orchestration and shared first-panel plans."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from rule_layout import RuleLayout
from test_written_rules import Catalog


class SamePageListeningTests(unittest.TestCase):
    def image_panel(self, width=120, height=60, after_options=False):
        layout = self.layout()
        layout.resources = layout.out / 'test-resources'
        assets = layout.resources / 'assets'
        assets.mkdir(parents=True)
        with fitz.open() as document:
            document.new_page(width=width, height=height)
            document.save(assets / 'diagram.pdf')
        group = self.panel_group(example=False)
        item = group['items'][0]
        item['stimulus'] = [{'type': 'image', 'asset': 'diagram.pdf', 'width': width}]
        if after_options:
            item['stimulus_position'] = 'after_options'
        return layout, group

    def test_listening_image_is_drawn_on_the_option_page_without_overlap(self):
        for after in (False, True):
            with self.subTest(after_options=after):
                layout, group = self.image_panel(after_options=after)
                layout.render_group(group, {'sidebar': False})
                page = layout.pages[-1]
                images = [c for c in page['commands'] if c['type'] == 'image']
                self.assertEqual(len(images), 1)
                image = images[0]
                top = layout.H - image['y'] - image['height']
                options = [g for g in layout.semantic_glyphs
                           if g['page_ref'] == id(page) and g['role'] == 'listening-option']
                self.assertEqual(len(options), 4)
                if after:
                    self.assertGreater(top, max(g['y'] for g in options))
                else:
                    self.assertLess(top + image['height'], min(g['y'] - g['size'] for g in options))
                self.assertEqual(layout.item_records[-1]['pages'], [len(layout.pages)])

    def test_oversized_listening_image_is_rejected_before_panel_is_drawn(self):
        layout, group = self.image_panel(width=300, height=400)
        with self.assertRaisesRegex(ValueError, 'Listening panel exceeds its allocated space'):
            layout.render_group(group, {'sidebar': False})
        self.assertFalse(any(c['type'] == 'image' for p in layout.pages for c in p['commands']))

    def test_embedded_choices_draw_numbered_diagram_without_duplicate_text_options(self):
        layout, group = self.image_panel(width=220, height=250)
        group['items'][0]['options_embedded_in_stimulus'] = True
        layout.render_group(group, {'sidebar': False})
        self.assertEqual(sum(c['type'] == 'image' for c in layout.pages[-1]['commands']), 1)
        self.assertFalse(any(g['role'] == 'listening-option' for g in layout.semantic_glyphs))
        self.assertEqual(layout.item_records[-1]['options'], 4)

    def test_embedded_choices_cannot_silently_hide_text_when_diagram_is_missing(self):
        layout, group = self.image_panel()
        group['items'][0].update(options_embedded_in_stimulus=True, stimulus=[])
        with self.assertRaisesRegex(ValueError, 'require a listening stimulus image'):
            layout.render_group(group, {'sidebar': False})

    def test_memo_cannot_reserve_less_space_than_its_visible_label(self):
        layout = self.layout()
        self.seed(layout)
        before = deepcopy(layout.page)
        with self.assertRaisesRegex(ValueError, 'memo height must contain its label'):
            layout.render_group(self.memo_group('L2', height=1),
                                {'new_page': False, 'sidebar': False})
        self.assertEqual(layout.page, before)

    def layout(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        reference = SimpleNamespace(profile=ROOT / 'profiles/n1-original', resolved={}, ledger=[])
        page = {'margin_top': 61.4489, 'body_bottom': 783,
                'font_size': 14.2, 'line_height': 28.35}
        return RuleLayout(Catalog(), {'page': page, 'sidebar': False},
                          ROOT / 'resources', directory.name, reference)

    @staticmethod
    def memo_group(identifier='L1', height=100):
        return {
            'id': identifier, 'kind': 'listening_memo',
            'title': '｜問題《もんだい》１', 'instruction': '話を聞いてください。',
            'items': [{'id': identifier + '-memo', 'stimulus': [
                {'type': 'memo', 'label': '－メモ－', 'height': height},
            ]}],
        }

    @staticmethod
    def panel_group(identifier='L2', example=True):
        return {
            'id': identifier, 'kind': 'listening_choice',
            'title': '｜問題《もんだい》２', 'instruction': '話を聞いてください。',
            'items': [{'id': identifier + '-question', 'is_example': example,
                       'options': ['日本', '学校', '電車', '会社']}],
        }

    def seed(self, layout, cursor=None):
        layout.render_group(self.memo_group(), {'sidebar': False})
        if cursor is not None:
            layout.y = cursor

    def test_two_memo_groups_share_a_page_without_overprinting(self):
        layout = self.layout()
        self.seed(layout)
        cursor, count = layout.y, len(layout.semantic_glyphs)
        original = deepcopy(layout.page['commands'])
        layout.render_group(self.memo_group('L2'), {'new_page': False, 'sidebar': False})
        self.assertEqual(len(layout.pages), 1)
        self.assertEqual(layout.page['commands'][:len(original)], original)
        self.assertEqual(layout.page['group_ids'], ['L1', 'L2'])
        added = layout.semantic_glyphs[count:]
        self.assertTrue(all(glyph['page_ref'] == id(layout.pages[0]) for glyph in added))
        self.assertGreater(min(glyph['y'] - glyph['size'] for glyph in added), cursor)
        self.assertAlmostEqual(added[0]['y'], cursor + layout.leading + 34.0712)

    def test_zero_group_gap_still_reserves_title_ruby_overhang(self):
        layout = self.layout()
        self.seed(layout)
        cursor, count = layout.y, len(layout.semantic_glyphs)
        layout.render_group(self.memo_group('L2'),
                            {'new_page': False, 'group_gap': 0, 'sidebar': False})
        self.assertEqual(len(layout.pages), 1)
        ruby = [glyph for glyph in layout.semantic_glyphs[count:]
                if glyph['role'] == 'ruby-heading']
        self.assertAlmostEqual(min(glyph['y'] - glyph['size'] for glyph in ruby), cursor)

    def test_insufficient_room_moves_heading_and_memo_as_one_unit(self):
        layout = self.layout()
        self.seed(layout, cursor=650)
        original, count = deepcopy(layout.page), len(layout.semantic_glyphs)
        layout.render_group(self.memo_group('L2'), {'new_page': False, 'sidebar': False})
        self.assertEqual(len(layout.pages), 2)
        self.assertEqual(layout.pages[0], original)
        added = layout.semantic_glyphs[count:]
        self.assertTrue(all(glyph['page_ref'] == id(layout.pages[1]) for glyph in added))
        self.assertAlmostEqual(added[0]['x'], layout.page_left(2))
        self.assertAlmostEqual(added[0]['y'], layout.top + 34.0712)
        self.assertTrue(any(glyph['char'] == 'メ' for glyph in added))

    def test_heading_and_example_panel_each_use_their_preflight_plan_once(self):
        layout = self.layout()
        self.seed(layout)
        with patch.object(layout, 'listening_heading_plan', wraps=layout.listening_heading_plan) as heading, \
                patch.object(layout, 'listening_panel_metrics', wraps=layout.listening_panel_metrics) as panel:
            layout.render_group(self.panel_group(), {'new_page': False, 'sidebar': False})
        self.assertEqual(heading.call_count, 1)
        self.assertEqual(panel.call_count, 1)
        self.assertIsNone(layout._opening_listening)
        self.assertEqual(layout.item_records[-1]['pages'], [1])
        self.assertEqual(len(layout.pages), 1)

    def test_insufficient_room_moves_heading_and_example_panel_together(self):
        layout = self.layout()
        self.seed(layout, cursor=600)
        original, count = deepcopy(layout.page), len(layout.semantic_glyphs)
        layout.render_group(self.panel_group(), {'new_page': False, 'sidebar': False})
        self.assertEqual(len(layout.pages), 2)
        self.assertEqual(layout.pages[0], original)
        self.assertEqual(layout.item_records[-1]['pages'], [2])
        self.assertTrue(all(glyph['page_ref'] == id(layout.pages[1])
                            for glyph in layout.semantic_glyphs[count:]))

    def test_nonexample_panel_keeps_its_deliberate_separate_content_page(self):
        layout = self.layout()
        self.seed(layout)
        original, count = deepcopy(layout.page), len(layout.semantic_glyphs)
        layout.render_group(self.panel_group(example=False),
                            {'new_page': False, 'sidebar': False})
        self.assertEqual(len(layout.pages), 3)
        self.assertEqual(layout.pages[0], original)
        self.assertEqual(layout.item_records[-1]['pages'], [3])
        added = layout.semantic_glyphs[count:]
        self.assertEqual(added[0]['page_ref'], id(layout.pages[1]))
        option_labels = [glyph for glyph in added if glyph['role'] == 'listening-option']
        self.assertEqual(len(option_labels), 4)
        self.assertTrue(all(glyph['page_ref'] == id(layout.pages[2]) for glyph in option_labels))

    def test_panel_plan_cache_does_not_leak_into_the_next_group(self):
        layout = self.layout()
        self.seed(layout)
        layout.render_group(self.panel_group(), {'new_page': False, 'sidebar': False})
        with patch.object(layout, 'listening_panel_metrics', wraps=layout.listening_panel_metrics) as panel:
            layout.render_group(self.panel_group('L3'), {'new_page': False, 'sidebar': False})
        self.assertEqual(panel.call_count, 1)
        self.assertIsNone(layout._opening_listening)
        self.assertEqual([record['id'] for record in layout.item_records],
                         ['L2-question', 'L3-question'])


if __name__ == '__main__':
    unittest.main()
