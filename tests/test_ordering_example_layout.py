"""A worked example must keep each synthetic answer below one ordering slot."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from material_primitives import MaterialPrimitives


class FullCellCatalog:
    """Conservative glyph widths; Latin digits may not make the test easier."""
    compress_ruby = True

    @staticmethod
    def width(char, size, bold=False, section='', role=None):
        return size


class OrderingExampleLayoutTests(unittest.TestCase):
    @staticmethod
    def example_table():
        # Synthetic prefix, four ordering slots and suffix. Five full cells in
        # an answer reproduce the old narrow-column wrap without exam content.
        return {'type': 'table', 'header_rows': 0, 'borders': False,
                'rows': [['例文', '__　　　__', '__　　　__', '__★__', '__　　　__', 'です。'],
                         ['', '1　甲甲甲', '2　乙乙乙', '3　丙丙丙', '4　丁丁', '']]}

    @staticmethod
    def layout():
        layout = MaterialPrimitives(FullCellCatalog(), {'page': {'font_size': 11.3}}, ROOT, ROOT)
        layout.section = 'G'
        return layout

    def test_new_worked_example_keeps_every_answer_on_one_line(self):
        for key in (6, '6'):
            with self.subTest(column_count_key=key):
                table = self.example_table()
                layout = self.layout()
                layout.gc = {'table_column_widths': {key: [.13, .165, .165, .165, .165, .21]}}
                # Body width minus the ordinary example frame's two 8 bp insets.
                widths, _, cells, *_ = layout.table_rows(table, 452.41 - 16)
                self.assertEqual([widths[1]] * 4, widths[1:5])
                self.assertTrue(all(len(cell) == 1 for row in cells for cell in row))
                answers = [''.join(atom.text for atom in cell[0]) for cell in cells[1]]
                self.assertEqual(answers, table['rows'][1])

                # The answer-card table has its own two-column widths, unaffected
                # by the six-column example setting and still fitting each cell.
                answer_card = {'type': 'table', 'header_rows': 0, 'width': 135,
                               'align': 'center', 'column_widths': [.35, .65],
                               'rows': [['（例）', '①　●　③　④']]}
                _, card_width = layout.table_geometry(answer_card, 0, 452.41)
                card = layout.table_rows(answer_card, card_width)
                self.assertTrue(all(len(cell) == 1 for row in card[2] for cell in row))

if __name__ == '__main__':
    unittest.main()
