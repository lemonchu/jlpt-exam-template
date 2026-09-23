"""Variable-content vertical quotations without source column lookup."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'tests'))

from rule_layout import RuleLayout
from test_written_rules import Catalog, NoMeasuredBodies
from vertical_rules import pack_citation


class VerticalRuleTests(unittest.TestCase):
    def make_layout(self, directory):
        layout = RuleLayout(Catalog(), {'page': {'body_bottom': 500}},
                            ROOT / 'resources', directory, NoMeasuredBodies())
        layout.section = 'R'
        layout.group = {'id': 'R-independent', 'kind': 'reading'}
        layout.gc = {'sidebar': False}
        layout.new_page()
        return layout

    def test_citation_packs_bibliographic_units_without_splitting_markup(self):
        text = '（小林賢太郎『僕がコントや演劇のために考えていること』幻冬舎による）'
        columns = pack_citation(text, 30)
        self.assertEqual([sum(len(atom.text) for atom in column) for column in columns], [27, 7])
        annotated = pack_citation('（｜作者《さくしゃ》『' + '題' * 35 + '』出版社）', 30)
        self.assertTrue(any(atom.ruby == 'さくしゃ' for column in annotated for atom in column))
        self.assertTrue(all(sum(len(atom.text) for atom in column) <= 30 for column in annotated))

    def test_quote_paragraph_starts_at_edge_and_ordinary_paragraph_indents(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = self.make_layout(directory)
            plan = layout.vertical_plan({'blocks': [{'type': 'vertical', 'text': '文章。\n「言葉」です。'}]})
            self.assertGreater(plan['columns'][0]['indent'], 0)
            self.assertEqual(plan['columns'][1]['indent'], 0)

    def test_more_text_adds_columns_and_cell_setting_controls_frame_height(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = self.make_layout(directory)
            short = layout.vertical_plan({'blocks': [{'type': 'vertical', 'text': '文' * 20}]})
            long = layout.vertical_plan({'blocks': [{'type': 'vertical', 'text': '文' * 60}]})
            self.assertGreater(long['width'], short['width'])
            self.assertEqual(long['height'], short['height'])
            layout.gc['vertical_cells'] = 30
            taller = layout.vertical_plan({'blocks': [{'type': 'vertical', 'text': '文' * 60}]})
            self.assertGreater(taller['height'], long['height'])

    def test_page_break_reanchors_centered_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = self.make_layout(directory)
            layout.y = 400
            block = {'type': 'box', 'blocks': [{'type': 'vertical', 'text': '本文。'}]}
            x, width = layout.left + 10, layout.width - 20
            plan = layout.vertical_plan(block)
            rectangles = []
            layout.rect = lambda *args, **kwargs: rectangles.append(args)
            layout.vertical_box(block, x, width)
            self.assertEqual(len(layout.pages), 2)
            self.assertAlmostEqual(rectangles[0][0], layout.left + 10 + (width - plan['width']) / 2)
            self.assertAlmostEqual(layout.y - layout.top,
                                   plan['before'] + plan['height'] + plan['after'])

    def test_bad_cell_counts_and_overwide_quotes_fail_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = self.make_layout(directory)
            block = {'type': 'box', 'blocks': [{'type': 'vertical', 'text': '文' * 1000}]}
            with self.assertRaisesRegex(ValueError, 'page width'):
                layout.vertical_box(block, layout.left, layout.width)
            for value in (True, 1, 2.5, float('inf')):
                layout.gc['vertical_cells'] = value
                with self.assertRaisesRegex(ValueError, 'vertical_cells'):
                    layout.vertical_plan(block)

    def test_note_is_visible_left_of_its_word_and_ruby_stays_right(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = self.make_layout(directory)
            calls = []
            layout.glyph = lambda char, size, x, y, *a, **kw: calls.append(
                dict(char=kw.get('semantic_char') or char, size=size, x=x, y=y))
            block = {'type': 'box', 'blocks': [
                {'type': 'vertical', 'text': '前{{注1|｜言葉《ことば》}}後'}]}
            layout.vertical_box(block, layout.left, layout.width)
            body = [g for g in calls if g['size'] == 11.3]
            notes = [g for g in calls if g['size'] == 6.4]
            ruby = [g for g in calls if g['size'] == 5.65]
            self.assertEqual(''.join(g['char'] for g in body), '前言葉後')
            self.assertEqual(''.join(g['char'] for g in notes), '（注1）')
            self.assertTrue(all(g['x'] < body[1]['x'] for g in notes))
            self.assertTrue(all(g['x'] > body[1]['x'] for g in ruby))
            self.assertGreater(notes[0]['y'], body[0]['y'])
            self.assertLess(notes[0]['y'], body[1]['y'])

    def test_wrapped_annotated_word_keeps_one_note_at_its_first_column(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = self.make_layout(directory)
            layout.gc['vertical_cells'] = 5
            plain = {'blocks': [{'type': 'vertical', 'text': '前前前言葉後'}]}
            annotated = {'blocks': [{'type': 'vertical', 'text': '前前前{{注|言葉}}後'}]}
            old = layout.vertical_plan(plain)
            new = layout.vertical_plan(annotated)
            rows = lambda plan: [''.join(a.text for a in c['atoms']) for c in plan['columns']]
            self.assertEqual(rows(old), rows(new))
            self.assertEqual(rows(new), ['前前前言', '葉後'])
            marked = [(i, a.text) for i,c in enumerate(new['columns']) for a in c['atoms'] if a.annotation]
            self.assertEqual(marked, [(0, '言')])

    def test_unsupported_children_cannot_disappear_from_vertical_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = self.make_layout(directory)
            for kind in ('table', 'image', 'box'):
                block = {'blocks': [{'type': 'vertical', 'text': '本文'}, {'type': kind}]}
                with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'citations only'):
                    layout.vertical_plan(block)


if __name__ == '__main__':
    unittest.main()
