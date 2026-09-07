"""Listening group continuation uses real orchestration and shared first-panel plans."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from rule_layout import RuleLayout
from test_written_rules import Catalog


class SamePageListeningTests(unittest.TestCase):
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
