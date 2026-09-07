"""Rule generation is content-independent and isolated from calibrated bodies."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'engine'))

from build import load
from inline import Atom, measure, parse
from rule_layout import RuleLayout
from semantic_bindings import layout_fingerprint
from written_rules import balance_instruction_tail, instruction_enumerations, expand_instruction_atoms


class Catalog:
    compress_ruby = True

    def width(self, char, size, *args, **kwargs):
        return size / 2 if char.isascii() else size * 1.0009

    def route(self, char, *args, **kwargs):
        return 'test-font', ord(char)

    def preferred(self, *args, **kwargs):
        return 'test-font'


class NoMeasuredBodies:
    def __init__(self):
        self.resolved = {}

    def __getattr__(self, name):
        if name in ('take_group', 'take_page', 'heading', 'slice_item', 'components'):
            raise AssertionError('Rule body accessed calibration: ' + name)
        raise AttributeError(name)


class WrittenRuleTests(unittest.TestCase):
    def layout(self, directory, section='R', **page):
        layout = RuleLayout(Catalog(), {'page': {'body_bottom': 783, **page}},
                            ROOT / 'resources', directory, NoMeasuredBodies())
        layout.section = section
        return layout

    def test_reading_instruction_policy_matches_all_six_specimen_breaks(self):
        endings = [
            ('ものを、', '一つ選びなさい。'), ('ものを、', '一つ選びなさい。'),
            ('４から', '一つ選びなさい。'), ('ものを、', '一つ選びなさい。'),
            ('４から', '一つ選びなさい。'), ('であ', '選び', 'なさい。'),
        ]
        with tempfile.TemporaryDirectory() as directory:
            layout = self.layout(directory)
            for group, expected in zip(load(ROOT / 'content/paper-a/R.yaml')['groups'], endings):
                with self.subTest(group=group['id']):
                    atoms = layout.written_instruction_atoms(group['instruction'])
                    rows, gaps, tracking = layout.reading_instruction_rows(atoms, 11.3, 401.53, 412.84, {})
                    self.assertEqual(len(rows), len(expected))
                    for row, ending in zip(rows, expected):
                        self.assertTrue(''.join(atom.text for atom in row).endswith(ending))
                    if gaps is not None:
                        extent = sum(atom.width + tracking * max(0, layout.tracking_units(atom) - 1)
                                     for atom in rows[0]) + sum(gaps)
                        self.assertLessEqual(extent, 401.53 + .05)

    def test_instruction_enumerations_preserve_style_and_annotation_boundaries(self):
        for text in ('１・２・３・４', '１**・２**・３', '１・２・｜３《さん》・４',
                     '__１・２__・３', '１・{{注|２}}・３'):
            with self.subTest(text=text):
                atoms = measure(parse(text), Catalog(), 11.3, 'R')
                grouped = instruction_enumerations(atoms)
                expanded = expand_instruction_atoms(grouped)
                self.assertEqual(expanded, atoms)
                self.assertTrue(all(first is second for first, second in zip(expanded, atoms)))

    def test_short_or_wide_instruction_does_not_shrink(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = self.layout(directory)
            atoms = layout.written_instruction_atoms('１・２・３・４から選びなさい。')
            rows, gaps, tracking = layout.reading_instruction_rows(atoms, 11.3, 500, 500, {})
            self.assertEqual(len(rows), 1)
            self.assertIsNone(gaps)
            self.assertEqual(tracking, 0)

    def test_first_row_contraction_can_be_disabled_and_scales_to_custom_width(self):
        text = '新しい案内の説明文を読んで内容に合った選択肢を選んでください。' * 3
        with tempfile.TemporaryDirectory() as directory:
            layout = self.layout(directory)
            atoms = layout.written_instruction_atoms(text)
            for width in (180, 260, 350, 430):
                rows, gaps, tracking = layout.reading_instruction_rows(
                    atoms, 11.3, width, width + 11.31,
                    {'instruction_first_line_max_negative_tracking': 0})
                self.assertIsNone(gaps)
                self.assertEqual(tracking, 0)
                self.assertEqual(''.join(atom.text for row in rows for atom in row), text)

    def test_manual_instruction_breaks_do_not_duplicate_or_drop_blank_rows(self):
        cases = [('甲\n乙', ['甲', '乙']), ('甲\n\n乙', ['甲', '', '乙']),
                 ('\n甲', ['', '甲']), ('甲\n', ['甲'])]
        with tempfile.TemporaryDirectory() as directory:
            layout = self.layout(directory)
            for text, expected in cases:
                with self.subTest(text=text):
                    rows, _, _ = layout.reading_instruction_rows(
                        layout.written_instruction_atoms(text), 11.3, 200, 220, {})
                    self.assertEqual([''.join(atom.text for atom in row) for row in rows], expected)

    def test_narrow_first_row_can_try_compact_enumeration_before_failing(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = self.layout(directory)
            rows, gaps, tracking = layout.reading_instruction_rows(
                layout.written_instruction_atoms('１・２・３・４から選びなさい。'), 11.3, 65, 100, {})
            self.assertEqual(''.join(atom.text for atom in rows[0]), '１・２・３・４')
            self.assertLess(tracking, 0)
            self.assertEqual(len(gaps), len(rows[0]) - 1)
            with self.assertRaisesRegex(ValueError, 'Indivisible cluster exceeds instruction width'):
                layout.reading_instruction_rows(layout.written_instruction_atoms('A' * 200),
                                                11.3, 65, 100, {})

    def test_reading_choice_does_not_rebalance_an_already_planned_first_row(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = self.layout(directory)
            group = {'id': 'R-independent', 'kind': 'choice', 'title': '問題８',
                     'instruction': '文' * 37, 'items': []}
            layout.render_group(group, {'sidebar': False})
            body = [glyph for glyph in layout.semantic_glyphs if glyph['char'] == '文']
            self.assertEqual(len(body), 37)
            self.assertEqual(len({glyph['y'] for glyph in body}), 2)

    def test_captioned_figure_measures_and_moves_as_one_relative_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = self.layout(directory, body_bottom=400, line_height=24.05996)
            layout.group = {'id': 'R-independent', 'kind': 'reading'}
            layout.gc = {'sidebar': False}
            layout.new_page()
            layout.y = 300
            layout.image_geometry = lambda image, width: ('assets/test.pdf', 240.24, 138.18)
            blocks = [{'type': 'paragraph', 'text': '図の説明', 'rule_style': 'figure_caption'},
                      {'type': 'image', 'asset': 'assets/test.pdf'}]
            measured = layout.material_height(blocks, layout.width - 16.95)
            layout.blocks(blocks, layout.left + 16.95, layout.width - 16.95)
            self.assertEqual(len(layout.pages), 2)
            self.assertAlmostEqual(layout.y - layout.top, measured)
            image = next(command for command in layout.page['commands'] if command['type'] == 'image')
            self.assertAlmostEqual(image['x'], layout.left + (layout.width - 240.24) / 2)
            longer = dict(blocks[0], text='説明' * 30)
            self.assertGreater(layout.figure_plan(longer, blocks[1])['total'], measured)

    def test_caption_requires_an_adjacent_image(self):
        with self.assertRaisesRegex(ValueError, 'immediately precede'):
            list(RuleLayout.material_segments([{'type': 'paragraph', 'rule_style': 'figure_caption', 'text': '説明'}]))

    def test_written_instruction_size_is_shared_by_measurement_and_drawing(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = self.layout(directory)
            group = {'id': 'R-independent', 'kind': 'reading', 'title': '問題８',
                     'instruction': '文章' * 20, 'items': []}
            measured, drawn = [], []
            original = layout.written_instruction_atoms
            def observe_atoms(text, size=11.3, bold=True):
                measured.append(size)
                return original(text, size, bold)
            layout.written_instruction_atoms = observe_atoms
            layout.line_gaps = lambda atoms, x, top, size, gaps, **kwargs: drawn.append(size)
            layout.line = lambda atoms, x, top, size, *args, **kwargs: drawn.append(size)
            layout.render_group(group, {'instruction_font_size': 14, 'sidebar': False})
            self.assertEqual(measured, [14])
            self.assertTrue(drawn)
            self.assertTrue(all(size == 14 for size in drawn))

    def test_rule_only_semantic_style_does_not_change_legacy_fingerprint(self):
        block = {'type': 'paragraph', 'text': '本文'}
        self.assertEqual(layout_fingerprint(block),
                         layout_fingerprint(dict(block, rule_style='quotation')))
        self.assertNotEqual(layout_fingerprint(block),
                            layout_fingerprint(dict(block, indent=0)))
        self.assertNotEqual(layout_fingerprint(block),
                            layout_fingerprint(dict(block, unknown_layout_option=True)))

    def test_instruction_tail_rule_keeps_ruby_cluster_and_input_unchanged(self):
        rows = [[Atom(char, width=10) for char in '本文から選びな'],
                [Atom('さい', ruby='さい', width=20), Atom('。', width=10)]]
        before = copy.deepcopy(rows)
        balanced = balance_instruction_tail(rows, 60)
        self.assertEqual(''.join(atom.text for atom in balanced[-1]), '選びなさい。')
        self.assertEqual(rows, before)
        self.assertEqual(balanced[-1][-2].ruby, 'さい')

    def test_arbitrary_choice_never_reads_measured_body_or_heading(self):
        group = {
            'id': 'V-independent', 'kind': 'choice', 'title': '練習',
            'instruction': '最もよいものを選んでください。',
            'items': [{'id': 'different-question', 'prompt': 'これは__問題__です。',
                       'options': ['文章', '図形', '記号', '説明']}],
        }
        with tempfile.TemporaryDirectory() as directory:
            layout = self.layout(directory, section='V')
            layout.render_group(group, {'use_measured': True, 'sidebar': False})
            self.assertEqual(len(layout.pages), 1)
            self.assertEqual(layout.component_audit[0]['mode'], 'rules')
            self.assertEqual(layout.component_audit[0]['placement'], 'composed')
            self.assertEqual(layout.item_records[0]['id'], 'different-question')
            self.assertTrue(layout.resolved)

    def test_reading_and_listening_do_not_lookup_measured_fragments(self):
        groups = [
            {'id': 'R-independent', 'kind': 'reading', 'title': '問題８',
             'instruction': '次の文章を読んでください。',
             'items': [{'id': 'article', 'stimulus': [
                 {'type': 'paragraph', 'text': 'これは新しい文章です。'}]}]},
            {'id': 'L-independent', 'kind': 'listening_choice', 'title': '問題１',
             'instruction': '答えを選んでください。',
             'items': [{'id': 'question', 'options': ['場所', '時間', '方向', '名前']}]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            for group in groups:
                with self.subTest(section=group['id'][0]):
                    layout = self.layout(directory, section=group['id'][0])
                    layout.render_group(group, {'use_measured': True, 'sidebar': False})
                    self.assertEqual(layout.component_audit[0]['mode'], 'rules')
                    self.assertTrue(layout.resolved)


if __name__ == '__main__':
    unittest.main()
