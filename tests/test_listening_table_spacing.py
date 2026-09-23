"""Table ruby padding and optional whole-page listening panels use real glyphs."""
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


class ListeningTableSpacingTests(unittest.TestCase):
    def layout(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        reference = SimpleNamespace(profile=ROOT / 'profiles/n1-original', resolved={}, ledger=[])
        page = {'margin_top': 61.4489, 'body_bottom': 783,
                'font_size': 14.2, 'line_height': 28.35}
        return RuleLayout(Catalog(), {'page': page, 'sidebar': False},
                          ROOT / 'resources', temporary.name, reference)

    @staticmethod
    def group():
        return {'id': 'L1', 'kind': 'listening_choice', 'title': '問題１',
                'instruction': '話を聞いてください。',
                'items': [{'id': f'q{index}', 'options': ['日本', '学校', '電車', '会社']}
                          for index in range(1, 7)]}

    def test_full_page_diagram_preserves_two_short_items_on_other_pages(self):
        for selected, expected in [('q1', [2, 3, 3, 4, 4, 5]),
                                   ('q3', [2, 2, 3, 4, 4, 5]),
                                   ('q6', [2, 2, 3, 3, 4, 5])]:
            with self.subTest(selected=selected):
                layout, group = self.layout(), self.group()
                layout.resources = layout.out / 'test-resources'
                assets = layout.resources / 'assets'
                assets.mkdir(parents=True)
                with fitz.open() as document:
                    document.new_page(width=300, height=400)
                    document.save(assets / 'diagram.pdf')
                for item in group['items']:
                    if item['id'] == selected:
                        item['stimulus'] = [{'type': 'image', 'asset': 'diagram.pdf', 'width': 300}]
                before = deepcopy(group)
                layout.render_group(group, {'sidebar': False, 'items_per_page': 2,
                                            'full_page_items': [selected]})
                self.assertEqual([record['pages'][0] for record in layout.item_records], expected)
                self.assertEqual([record['label'] for record in layout.item_records],
                                 [f'{index}番' for index in range(1, 7)])
                self.assertEqual(group, before)
                self.assertEqual(sum(command['type'] == 'image' for page in layout.pages
                                     for command in page['commands']), 1)

    def test_invalid_full_page_selection_fails_before_drawing(self):
        for selected in ('q1', ['q1', 'q1'], ['absent'], [True], ['']):
            with self.subTest(selected=selected):
                layout = self.layout()
                with self.assertRaisesRegex(ValueError, 'full_page_items'):
                    layout.render_group(self.group(), {'full_page_items': selected})
                self.assertEqual(layout.pages, [])
                self.assertEqual(layout.semantic_glyphs, [])

    def test_table_ruby_has_clear_padding_and_measurement_matches_drawing(self):
        layout = self.layout()
        layout.group, layout.section, layout.gc = self.group(), 'L', {}
        table = {'type': 'table', 'header_rows': 1,
                 'rows': [['｜名前《なまえ》', '｜学年《がくねん》'],
                          ['｜林《はやし》', '2｜年生《ねんせい》']]}
        layout.new_page()
        origin = layout.y
        expected = layout.estimate_block(table, layout.width)
        with patch.object(layout, 'rect', wraps=layout.rect) as rectangles:
            layout.table(table, layout.left, layout.width)
        self.assertAlmostEqual(layout.y - origin, expected)
        for call in rectangles.call_args_list:
            x, y, width, height = call.args[:4]
            glyphs = [glyph for glyph in layout.semantic_glyphs
                      if x <= glyph['x'] < x + width and y < glyph['y'] < y + height]
            self.assertTrue(glyphs)
            self.assertGreaterEqual(min(g['y'] - g['size'] for g in glyphs), y + 4 - 1e-6)
            self.assertLessEqual(max(g['y'] + g['size'] * .25 for g in glyphs),
                                 y + height - 6 + 1e-6)

    def test_compact_table_expands_when_old_row_height_cannot_clear_ruby(self):
        layout = self.layout()
        layout.group, layout.section, layout.gc = self.group(), 'L', {}
        table = {'type': 'table', 'table_line_height': 18,
                 'rows': [['｜名前《なまえ》', '｜学年《がくねん》']]}
        layout.new_page()
        origin = layout.y
        plan = layout.table_rows(table, layout.width)
        self.assertGreater(plan[1][0], 18 + 4 + 6)
        layout.table(table, layout.left, layout.width)
        self.assertGreaterEqual(min(g['y'] - g['size'] for g in layout.semantic_glyphs),
                                origin + 4 - 1e-6)
        self.assertLessEqual(max(g['y'] + g['size'] * .25 for g in layout.semantic_glyphs),
                             origin + plan[1][0] - 6 + 1e-6)

    def test_borderless_alignment_table_does_not_acquire_new_padding(self):
        layout = self.layout()
        layout.section, layout.gc = 'G', {}
        table = {'type': 'table', 'borders': False, 'header_rows': 0,
                 'rows': [['｜山田《やまだ》', '本文']]}
        plan = layout.table_rows(table, 300)
        self.assertEqual(plan[-1], 4)
        self.assertAlmostEqual(plan[1][0], plan[4] + 10)

    def test_first_option_ruby_clears_table_by_its_existing_six_point_gap(self):
        layout, group = self.layout(), self.group()
        group['items'] = group['items'][:1]
        group['items'][0]['stimulus'] = [{'type': 'table', 'rows': [['氏名', '学年']]}]
        group['items'][0]['options'][0] = '｜山川《やまかわ》'
        with patch.object(layout, 'rect', wraps=layout.rect) as rectangles:
            layout.render_group(group, {'sidebar': False})
        table_bottom = max(call.args[1] + call.args[3] for call in rectangles.call_args_list)
        ruby = [glyph for glyph in layout.semantic_glyphs
                if glyph['size'] == 7.1 and glyph['y'] > table_bottom]
        self.assertTrue(ruby)
        self.assertAlmostEqual(min(g['y'] - g['size'] for g in ruby), table_bottom + 6)


if __name__ == '__main__':
    unittest.main()
