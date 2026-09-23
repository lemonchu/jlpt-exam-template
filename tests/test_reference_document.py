"""Information sheets keep their full text, table geometry and page boundaries."""
from copy import deepcopy
import unittest

from test_reference_rules import GuideDouble
from rule_validation import validate_rule_content


def text(value, role='reference_body'):
    return {'type': 'paragraph', 'text': value, 'rule_style': role}


def document(*blocks):
    return {'type': 'box', 'rule_style': 'reference', 'blocks': list(blocks)}


class ReferenceDocumentTests(unittest.TestCase):
    def setUp(self):
        self.layout = GuideDouble()
        self.layout.top, self.layout.bottom = 62.49, 770
        self.layout.fs, self.layout.gc = 9.2, {}

    def test_measured_plan_and_drawing_preserve_text_and_nested_box(self):
        block = document(text('利用案内', 'reference_title'),
                         text('一、条件', 'reference_section'),
                         {'type': 'box', 'blocks': [text('書類は全部提出してください。' * 4)]},
                         text('電話：012-345-6789', 'reference_contact'))
        original = deepcopy(block)
        plan = self.layout.reference_document_plan(block, 450)
        start = self.layout.y
        self.layout.block(block, self.layout.left, 450)
        self.assertAlmostEqual(self.layout.y - start, plan.height)
        self.assertEqual(block, original)
        self.assertEqual(''.join(row[3] for row in self.layout.rows),
                         '利用案内一、条件' + '書類は全部提出してください。' * 4 + '電話：012-345-6789')
        self.assertEqual(len(self.layout.frames), 2)

    def test_table_respects_unequal_columns_and_wraps_inside_cells(self):
        table = {'type': 'table', 'header_rows': 1, 'column_widths': [1, 3],
                 'rows': [['区分', '条件'], ['学生', '費用と申込期限の説明。' * 8]]}
        plan = self.layout.reference_document_plan(document(table), 450)
        cells = [op for op in plan.operations if op['kind'] == 'rect']
        self.assertEqual(len(cells), 4)
        self.assertAlmostEqual(cells[1]['width'], cells[0]['width'] * 3)
        for op in plan.operations:
            if op['kind'] == 'row':
                self.assertLessEqual(sum(a.width for a in op['atoms']), op['width'] + .01)
                self.assertLessEqual(op['y'] + op['size'] * 1.3, plan.height)

    def test_long_sheet_reflows_and_overfull_sheet_fails_without_dropping_rows(self):
        short = document(text('募集要項', 'reference_title'), text('説明文。' * 50))
        long = document(text('募集要項', 'reference_title'), text('説明文。' * 200))
        self.assertGreater(self.layout.estimate_block(long, 450), self.layout.estimate_block(short, 450))
        with self.assertRaisesRegex(ValueError, 'Reference document needs'):
            self.layout.estimate_block(document(text('説明文。' * 5000)), 450)

    def test_reference_roles_cannot_escape_their_document(self):
        good = document({'type': 'box', 'blocks': [text('説明') ]})
        validate_rule_content({'id': 'R13', 'stimulus': [good]})
        for bad in ([text('説明')], [document({'type': 'image', 'asset': 'test.png'})]):
            with self.assertRaises(ValueError):
                validate_rule_content({'id': 'R13', 'stimulus': bad})

    def test_label_before_reference_keeps_specialized_measurement_and_drawing(self):
        self.layout.group = {'kind': 'reading'}
        self.layout.leading = 24.06
        block = document(text('募集案内', 'reference_title'), text('提出してください。'))
        label = {'type': 'heading', 'text': 'A'}
        validate_rule_content({'id': 'R13', 'stimulus': [label, block]})
        height = self.layout.estimate_block(block, self.layout.width)
        start = self.layout.y
        self.layout.blocks([label, block])
        self.assertAlmostEqual(self.layout.y - start, 19.03 + height)
        self.assertEqual(next(row[2] for row in self.layout.rows if row[3] == '募集案内'), 14.5)
        self.assertAlmostEqual(self.layout.frames[-1][0][-1], height)

    def test_reference_resets_prior_note_state_before_following_definition(self):
        self.layout.group = {'kind': 'reading'}
        self.layout.leading = 24.06
        self.layout._last_was_note = self.layout._last_note_wrapped = True
        self.layout._last_material_kind = 'note'
        block = document(text('資料'))
        note = {'type': 'paragraph', 'style': 'small', 'text': '（注1）用語：説明'}
        planned = self.layout.reading_sequence_height([block, note], self.layout.width)
        start = self.layout.y
        self.layout.block(block)
        after = self.layout.estimate_block(note, self.layout.width)
        self.assertAlmostEqual(self.layout.y - start + after, planned)
        self.assertFalse(self.layout._last_was_note)
        self.assertFalse(self.layout._last_note_wrapped)
        self.assertEqual(self.layout._last_material_kind, 'box')
        self.assertAlmostEqual(self.layout.reading_paragraph_gap(note), 19.021)


if __name__ == '__main__':
    unittest.main()
