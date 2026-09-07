"""Guide documents reflow from semantic roles without source-page bindings."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from component_layout import ComponentLayout
from reference_rules import ReferenceRules
from rule_typography import TypographyRules


class GuideCatalog:
    compress_ruby = True

    def width(self, char, size, bold=False, section='', role=None):
        if char.isascii():
            return size / 2
        return {11.3: 11.31017}.get(size, size)


class GuideDouble(ReferenceRules, TypographyRules, ComponentLayout):
    def __init__(self):
        self.catalog = GuideCatalog()
        self.section = 'R'
        self.left = 78.96
        self.width = 452.41
        self.y = 62.4928
        self.rows = []
        self.frames = []
        self.strokes = []
        self.needs = []

    def ensure(self, height):
        self.needs.append(height)

    def line(self, atoms, x, top, size, **kwargs):
        self.rows.append((x, top, size, ''.join(atom.text for atom in atoms)))

    def rect(self, *args, **kwargs):
        self.frames.append((args, kwargs))

    def rule(self, *args, **kwargs):
        self.strokes.append((args, kwargs))


def document(*blocks):
    return {'type': 'box', 'rule_style': 'guide', 'blocks': list(blocks)}


def paragraph(text, role='guide_paragraph'):
    return {'type': 'paragraph', 'rule_style': role, 'text': text}


class ReferenceRuleTests(unittest.TestCase):
    def setUp(self):
        self.layout = GuideDouble()

    def test_adding_prose_lines_moves_following_heading_and_frame(self):
        short = document(paragraph('ご案内', 'guide_title'), paragraph('日本語。'),
                         paragraph('① 次の項目', 'guide_section'))
        long = deepcopy(short)
        long['blocks'][1]['text'] = '日本語の説明文です。' * 12
        first = self.layout.guide_plan(short, 486.31)
        second = self.layout.guide_plan(long, 486.31)
        self.assertGreater(second.height, first.height)
        self.assertAlmostEqual(second.height - first.height,
                               second.operations[-1]['baseline'] - first.operations[-1]['baseline'])

    def test_extra_table_row_moves_following_content(self):
        table = {'type': 'table', 'rule_style': 'guide_table',
                 'header_rows': 1, 'rows': [['図書館', '閲覧', '貸出'], ['大学', '可', '不可']]}
        short = document(table, paragraph('② 次の案内', 'guide_subsection'))
        longer = deepcopy(short)
        longer['blocks'][0]['rows'].append(['別の大学', '可', '可'])
        before = self.layout.guide_plan(short, 486.31)
        after = self.layout.guide_plan(longer, 486.31)
        self.assertAlmostEqual(after.height - before.height, 15.591)

    def test_long_table_cells_wrap_and_increase_row_height(self):
        short = document({'type': 'table', 'rows': [['大学', '可', '可']]})
        long = deepcopy(short)
        long['blocks'][0]['rows'][0][1] = '利用条件についての長い説明です。'
        before = self.layout.guide_plan(short, 486.31)
        after = self.layout.guide_plan(long, 486.31)
        self.assertGreater(after.height, before.height)
        self.assertGreater(sum(operation['kind'] == 'row' for operation in after.operations), 3)

    def test_table_columns_remain_positive_and_inside_frame(self):
        for columns in (1, 3, 6, 10):
            with self.subTest(columns=columns):
                plan = self.layout.guide_plan(document({'type': 'table', 'rows': [['字'] * columns]}), 486.31)
                verticals = [operation['x'] for operation in plan.operations if operation['kind'] == 'vertical']
                self.assertTrue(all(0 < position < plan.width for position in verticals))
                self.assertGreater(max(verticals), min(verticals))

    def test_unreadable_or_invalid_tables_fail_clearly(self):
        for table in ({'rows': [[]]}, {'rows': [['字'] * 40]},
                      {'rows': [['字'], ['字', '字']]}, {'rows': [['字']], 'header_rows': True}):
            with self.subTest(table=table), self.assertRaises(ValueError):
                self.layout.guide_plan(document({'type': 'table', **table}), 486.31)

    def test_caption_follows_the_width_of_its_table(self):
        def caption_offset(columns):
            plan = self.layout.guide_plan(document(paragraph('表の説明', 'guide_caption'),
                                                   {'type': 'table', 'rows': [['字'] * columns]}), 486.31)
            caption = next(operation for operation in plan.operations if operation['kind'] == 'row')
            table_left = min(operation['x'] for operation in plan.operations if operation['kind'] == 'vertical')
            return caption['x'] - table_left

        self.assertAlmostEqual(caption_offset(2), caption_offset(5))

    def test_double_table_borders_leave_an_open_gutter(self):
        plan = self.layout.guide_plan(document({'type': 'table', 'header_rows': 1,
                                                'rows': [['項目', '条件'], ['大学', '可']]}), 486.31)
        verticals = [operation for operation in plan.operations if operation['kind'] == 'vertical']
        positions = sorted({operation['x'] for operation in verticals})
        gap_center = (positions[1] + positions[2]) / 2
        horizontals = [operation for operation in plan.operations if operation['kind'] == 'rule']
        outer = (min(operation['y'] for operation in horizontals), max(operation['y'] for operation in horizontals))
        for operation in horizontals:
            if operation['y'] not in outer:
                self.assertFalse(operation['x'] < gap_center < operation['x'] + operation['width'])
        self.assertEqual(len([operation for operation in verticals if operation['x'] == positions[1]]), 2)

    def test_empty_or_unknown_guide_documents_fail_clearly(self):
        for block in (document(), document(paragraph('本文', 'guide_paragraf'))):
            with self.assertRaises(ValueError):
                self.layout.guide_plan(block, 486.31)

    def test_long_title_and_intro_wrap_without_crossing_frame(self):
        plan = self.layout.guide_plan(document(paragraph('長い表題です' * 10, 'guide_title'),
                                               paragraph('長い説明文です。' * 15, 'guide_intro')), 486.31)
        rows = [operation for operation in plan.operations if operation['kind'] == 'row']
        self.assertGreater(len(rows), 2)
        for operation in rows:
            extent = sum(atom.width for atom in operation['atoms'])
            extent += operation['tracking'] * max(0, sum(self.layout.tracking_units(atom) for atom in operation['atoms']) - 1)
            self.assertGreaterEqual(operation['x'], 0)
            self.assertLessEqual(operation['x'] + extent, plan.width)

    def test_long_indivisible_title_has_a_clear_error(self):
        with self.assertRaisesRegex(ValueError, 'Indivisible cluster'):
            self.layout.guide_plan(document(paragraph('A' * 200, 'guide_title')), 486.31)

    def test_page_translation_preserves_document_geometry(self):
        block = document(paragraph('ご案内', 'guide_title'), paragraph('本文です。'))
        self.layout.guide_document(block, 62.01, 486.31)
        first_rows = list(self.layout.rows)
        first_frame = self.layout.frames[-1][0]
        self.layout.y = 112.4928
        self.layout.rows = []
        self.layout.guide_document(block, 82.01, 486.31)
        second_frame = self.layout.frames[-1][0]
        self.assertEqual(len(self.layout.rows), len(first_rows))
        for first, second in zip(first_rows, self.layout.rows):
            self.assertAlmostEqual(second[0] - first[0], 20)
            self.assertAlmostEqual(second[1] - first[1], 50)
        self.assertEqual(first_frame[2:], second_frame[2:])
        self.assertIsNone(self.layout._guide_glyph_style)

    def test_page_break_preserves_inset_from_new_page_origin(self):
        block = document(paragraph('本文です。'))
        original_left = self.layout.left

        def move_page(height):
            self.layout.left += 16.95
            self.layout.y = 62.4928

        self.layout.ensure = move_page
        self.layout.guide_document(block, original_left - 16.95, 486.31)
        self.assertAlmostEqual(self.layout.frames[-1][0][0], self.layout.left - 16.95 - .017)


if __name__ == '__main__':
    unittest.main()
