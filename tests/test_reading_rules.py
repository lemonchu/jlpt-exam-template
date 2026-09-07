"""Reading rules are tested against source typography and variable content."""
from pathlib import Path
import copy
import sys
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from component_layout import ComponentLayout
from inline import Atom
from reference_components import ReferenceComponents
from semantic_bindings import CalibrationMismatch, chars_for
from reading_rules import (CompactReference, MaterialColon, MaterialDash, ReadingRules,
                           citation_parts, cloze_frame, justified_gaps, kana_compressed_gaps, punctuation_gaps,
                           row_ink_height)


class MonoCatalog:
    compress_ruby = True

    def width(self, char, size, *args, **kwargs):
        return size * 11.31017 / 11.3


class FlowProbe(ReadingRules, ComponentLayout):
    def __init__(self):
        self.catalog = MonoCatalog()
        self.section = 'R'
        self.group = {'kind': 'reading'}
        self.gc = {}
        self.fs, self.leading = 11.3, 24.05996
        self.top, self.bottom = 62.4928, 783.0
        self.left, self.width = 0.0, 452.41
        self.y = self.top
        self.pages = [{}]
        self.page = self.pages[0]
        self.drawn = []
        self.decorations = []
        self._rule_reading_block = {'type': 'paragraph'}

    def new_page(self):
        self.page = {}
        self.pages.append(self.page)
        self.y = self.top
        self.left += 15.33

    def line(self, atoms, x, top, size, *args, **kwargs):
        self.drawn.append((len(self.pages), x, top + size, ''.join(a.text for a in atoms)))

    def rule(self, *args):
        self.decorations.append(args)

    def frame_segments(self, *args):
        self.decorations.append(args)


class ReadingRuleTests(unittest.TestCase):
    def test_a_restored_vector_dash_keeps_exact_glyphs_and_strict_contract(self):
        group = yaml.safe_load((ROOT / 'content/paper-a/G.yaml').read_text())['groups'][2]
        field = 'G:/groups/2/items/0/stimulus/1/blocks/8/text#base'
        text = group['items'][0]['stimulus'][1]['blocks'][8]['text']
        self.assertIn('足を踏ん張り、――行うのだ。', text)
        self.assertEqual(chars_for(text, 'base')[108:110], ['―', '―'])
        reference = ReferenceComponents(ROOT / 'profiles/n1-original', ROOT / 'content/common/metadata.yaml')
        reference.require_layout_compatibility(group)
        self.assertEqual(reference.bindings['fields'][field]['shape']['vector_marks'][-2:],
                         [[108, '―'], [109, '―']])
        resolved, _ = reference.resolve_runs(group, ['G-p05-r52', 'G-p05-r53', 'G-p05-r54'])
        self.assertEqual(''.join(resolved['G-p05-r52']['glyphs']),
                         'いうように中に入ってくる。そして、足を踏ん張り、行うのだ。')
        self.assertEqual(''.join(resolved['G-p05-r53']['glyphs']), '（注４）')
        self.assertEqual(''.join(resolved['G-p05-r54']['glyphs']), 'これ見よがしに。')
        changed = copy.deepcopy(group)
        changed['items'][0]['stimulus'][1]['blocks'][8]['text'] = text.replace('――行う', '行う')
        with self.assertRaises(CalibrationMismatch):
            reference.require_layout_compatibility(changed)
        with self.assertRaises(CalibrationMismatch):
            reference.resolve_runs(changed, ['G-p05-r52'])

    def test_a_expanded_row_uses_quantized_space_and_rigid_punctuation(self):
        # A R10: its first line contains 38 base glyphs in a 39-cell measure.
        text = '暮らしの中で身近な木といえば、街路樹と公園の樹木、そして住宅の庭の木あたりで'
        atoms = [Atom(char, width=11.31017) for char in text]
        gaps = justified_gaps(atoms, 39 * 11.31017, 11.3)
        self.assertAlmostEqual(sum(gaps), 11.31017, places=6)
        for index in (0, 1, 2):
            self.assertAlmostEqual(gaps[index], 0.17967, places=5)
        self.assertAlmostEqual(gaps[4], 0.35934, places=5)
        for index, char in enumerate(text):
            if char == '、':
                self.assertEqual(gaps[index - 1:index + 1], [0, 0])

    def test_hanging_period_does_not_stretch_a_full_row(self):
        atoms = [Atom(char, width=10) for char in '本文。']
        self.assertEqual(justified_gaps(atoms, 20, 10), [0, 0])
        self.assertEqual(justified_gaps(atoms, 30, 10), [0, 0])

    def test_kana_contraction_protects_dense_kanji_and_run_leading_cells(self):
        atoms = [Atom(char, width=11.31017) for char in '考えを認め合える']
        width = sum(atom.width for atom in atoms) - .9
        gaps = kana_compressed_gaps(atoms, width, 11.3)
        for actual, expected in zip(gaps, [0, -.3, 0, -.3, 0, 0, -.3]):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(sum(atom.width for atom in atoms) + sum(gaps), width)

    def test_kana_run_policy_depends_on_script_context_not_a_phrase_lookup(self):
        for text, expected in [('話を聞', [-.3, 0]), ('話をして', [0, -.15, -.15])]:
            atoms = [Atom(char, width=11.31017) for char in text]
            gaps = kana_compressed_gaps(atoms, sum(atom.width for atom in atoms) - .3, 11.3)
            for actual, wanted in zip(gaps, expected):
                self.assertAlmostEqual(actual, wanted)

    def test_kana_contraction_is_bounded_and_respects_ruby_and_underlines(self):
        atoms = [Atom(char, width=11.31017) for char in 'あいう']
        natural = sum(atom.width for atom in atoms)
        self.assertIsNone(kana_compressed_gaps(atoms, natural + 1, 11.3))
        self.assertIsNone(kana_compressed_gaps(atoms, natural - 1, 11.3))
        for attribute, value in [('ruby', 'い'), ('underline', True)]:
            protected = copy.deepcopy(atoms)
            setattr(protected[1], attribute, value)
            self.assertIsNone(kana_compressed_gaps(protected, natural - .2, 11.3))

    def test_adjacent_closing_punctuation_shares_one_half_cell(self):
        atoms = [Atom(char, width=11.31017) for char in '文）、（次']
        self.assertEqual(punctuation_gaps(atoms, 11.3), [0, -5.655085, -5.655085, 0])

    def test_line_can_use_bottom_grid_baseline_without_its_empty_leading(self):
        flow = FlowProbe()
        flow.y = 760.23164
        flow.paragraph('本文')
        self.assertEqual(flow.drawn[0][0], 1)
        self.assertAlmostEqual(flow.drawn[0][2], 771.53164)
        flow.paragraph('次の行')
        self.assertEqual(flow.drawn[1][0], 2)
        self.assertAlmostEqual(flow.drawn[1][1], 15.33)

    def test_below_word_annotation_participates_in_page_fit(self):
        flow = FlowProbe()
        flow.y = 766.0
        flow.paragraph('{{注|本文}}')
        self.assertEqual(flow.drawn[0][0], 2)
        self.assertGreater(row_ink_height([Atom('文', annotation='（注）')], 11.3), 19)

    def test_quote_leading_character_does_not_guess_editorial_indent(self):
        flow = FlowProbe()
        ordinary = {'type': 'paragraph', 'text': '「言葉」という意味。'}
        dialogue = dict(ordinary, rule_style='dialogue')
        self.assertEqual(flow.paragraph_indent(ordinary, False, 'left', 400), 11.31)
        self.assertEqual(flow.paragraph_indent(dialogue, False, 'left', 400), 0)
        self.assertEqual(flow.paragraph_indent(dict(dialogue, indent=20), False, 'left', 400), 20)
        continuation = dict(ordinary, rule_style='continuation')
        self.assertEqual(flow.paragraph_indent(continuation, False, 'left', 400), 0)

    def test_parenthesized_instruction_reference_is_a_single_cell(self):
        flow = FlowProbe()
        atoms = flow.written_instruction_atoms('（１）と(4)を読む。')
        references = [atom for atom in atoms if isinstance(atom, CompactReference)]
        self.assertEqual([atom.number for atom in references], ['1', '4'])
        self.assertTrue(all(abs(atom.width - 11.31017) < 1e-8 for atom in references))
        self.assertTrue(all(flow.tracking_units(atom) == 1 for atom in references))
        flow.section = 'G'
        self.assertFalse(any(isinstance(atom, CompactReference)
                             for atom in flow.written_instruction_atoms('（１）')))

    def test_instruction_justification_is_bounded_without_changing_body_policy(self):
        flow = FlowProbe()
        rows = []
        flow.line_gaps = lambda atoms, x, top, size, gaps: rows.append(gaps)
        atoms = [Atom(char, width=11.31017) for char in '本文' * 17]
        flow.written_instruction(atoms, 0, 0, 401.53, False)
        self.assertEqual(rows, [])
        self.assertEqual(len(flow.drawn), 1)
        self.assertGreater(max(justified_gaps(atoms, 401.53, 11.3)), 2 * .0159 * 11.3)
        flow.written_instruction(atoms, 0, 0, 388, False)
        self.assertTrue(rows)
        self.assertLessEqual(max(rows[-1]), 2 * .0159 * 11.3)
        flow.gc['instruction_max_positive_tracking'] = 0
        rows.clear()
        flow.written_instruction(atoms, 0, 0, 388, False)
        self.assertEqual(rows, [])

    def test_paragraph_starting_with_cloze_frame_aligns_its_outer_stroke(self):
        flow = FlowProbe()
        flow.section, flow.group = 'G', {'kind': 'cloze'}
        flow._cloze_material_depth = 1
        block = {'type': 'paragraph', 'text': '〔12〕。続きの文章。'}
        self.assertAlmostEqual(flow.paragraph_indent(block, False, 'left', 400), 5.49)
        self.assertEqual(flow.paragraph_indent(dict(block, indent=12), False, 'left', 400), 12)

    def test_material_decorations_preserve_text_and_style(self):
        flow = FlowProbe()
        atoms = flow._material_atoms('説明：__――__続き', 11.3, False)
        self.assertEqual(''.join(atom.text for atom in atoms), '説明：――続き')
        self.assertIsInstance(atoms[2], MaterialColon)
        self.assertIsInstance(atoms[3], MaterialDash)
        self.assertEqual(atoms[3].text, '――')
        self.assertTrue(atoms[3].underline)

    def test_material_colon_measures_only_the_glyph_it_will_draw(self):
        class AsciiColonCatalog(MonoCatalog):
            def width(self, char, size, *args, **kwargs):
                if char == '：':
                    raise AssertionError('The subset need not contain an unused fullwidth colon')
                return super().width(char, size, *args, **kwargs)
        flow = FlowProbe()
        flow.catalog = AsciiColonCatalog()
        atoms = flow._material_atoms('受付時間：９：００', 11.3, True)
        self.assertIsInstance(atoms[4], MaterialColon)
        self.assertEqual(atoms[4].text, '：')
        self.assertAlmostEqual(atoms[4].width, 11.3 * 1.0298)
        self.assertEqual(atoms[-1].text, '９：００')

    def test_latin_japanese_space_does_not_change_english_word_space(self):
        flow = FlowProbe()
        atoms = flow._material_atoms('English Word 編集', 9.2, False, small=True)
        spaces = [atom.width for atom in atoms if atom.text == ' ']
        self.assertAlmostEqual(spaces[0], flow.catalog.width(' ', 9.2))
        self.assertAlmostEqual(spaces[1], 2.3)

    def test_long_citation_wraps_at_bibliographic_units(self):
        text = '（編集者『書名』出版社による）'
        self.assertEqual(citation_parts(text), ['（編集者', '『書名』', '出版社による）'])
        self.assertEqual(citation_parts('指定した\n改行'), ['指定した', '改行'])
        self.assertEqual(citation_parts('一般的な説明'), ['一般的な説明'])
        self.assertEqual(citation_parts('（SITE NAME ＜https://example.test/path＞による）'),
                         ['（SITE NAME', '＜https://example.test/path＞による）'])

    def test_measurement_and_rendering_share_semantic_citation_breaks(self):
        flow = FlowProbe()
        text = '（' + '編者' * 10 + '『' + '題名' * 10 + '』出版社による）'
        block = {'type': 'paragraph', 'text': text, 'style': 'small', 'align': 'right'}
        estimated = flow.estimate_block(block)
        start = flow.y
        flow.block(block)
        self.assertAlmostEqual(flow.y - start, estimated)
        self.assertEqual(len(flow.drawn), 3)
        self.assertTrue(flow.drawn[1][3].startswith('『'))

    def test_cloze_frame_preserves_body_measure_at_any_width(self):
        frame = cloze_frame({})
        for body_width in (300, 452.41, 510):
            outer = body_width + frame.outset_left + frame.outset_right
            self.assertAlmostEqual(outer - frame.inset_left - frame.inset_right, body_width)
        custom = cloze_frame({'material_box_outset': 15, 'material_box_padding': 10})
        self.assertEqual((custom.outset_left, custom.outset_right), (15, 15))
        self.assertEqual((custom.inset_left, custom.inset_right), (10, 10))
        for value in (True, float('nan'), float('inf'), -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cloze_frame({'material_box_padding': value})

    def test_cloze_citation_tracks_frame_edge_not_page_coordinate(self):
        flow = FlowProbe()
        flow.section, flow.group = 'G', {'kind': 'cloze'}
        citation = {'type': 'paragraph', 'style': 'small', 'align': 'right'}
        flow._last_material_kind = 'box'
        x, width = flow._material_geometry(citation, 100, 350)
        self.assertEqual(x, 100)
        self.assertAlmostEqual(width, 350 + 11.30 + 1.71 * .75)
        flow._last_material_kind = 'paragraph'
        self.assertEqual(flow._material_geometry(citation, 100, 350), (100, 350))

    def test_whole_cloze_frame_keeps_relative_origin_on_next_parity_page(self):
        flow = FlowProbe()
        flow.section, flow.group = 'G', {'kind': 'cloze'}
        flow.y = 770
        flow.reading_box({'type': 'box', 'blocks': [{'type': 'paragraph', 'text': '本文'}]},
                         0, flow.width)
        self.assertEqual(len(flow.pages), 2)
        self.assertAlmostEqual(flow.drawn[0][1], 15.33 + 11.31)
        self.assertAlmostEqual(flow.decorations[-1][2], -11.91)

    def test_notice_footer_estimate_and_draw_share_derived_indentation(self):
        flow = FlowProbe()
        flow._rule_material_style = 'notice'
        flow._contact_detail_inset = 99.0
        blocks = [
            {'type': 'paragraph', 'rule_style': 'contact', 'text': '問合せ：〒１１１'},
            {'type': 'paragraph', 'rule_style': 'contact_detail', 'text': '連絡先の詳しい説明' * 3},
        ]
        estimated = flow.reading_sequence_height(blocks, 200)
        self.assertEqual(flow._contact_detail_inset, 99.0)
        start = flow.y
        flow.blocks(blocks, 0, 200)
        self.assertAlmostEqual(flow.y - start, estimated)
        self.assertGreater(len(flow.drawn), 2)
        self.assertGreater(flow.drawn[-1][1], 20)

    def test_notice_does_not_inherit_contact_alignment_from_previous_box(self):
        flow = FlowProbe()
        flow._contact_detail_inset = 99.0
        block = {'type': 'box', 'rule_style': 'notice', 'blocks': [
            {'type': 'paragraph', 'rule_style': 'contact_detail', 'text': '別の案内'}]}
        estimated = flow.estimate_block(block, 300)
        self.assertEqual(flow._contact_detail_inset, 99.0)
        start = flow.y
        flow.reading_box(block, 0, 300)
        self.assertAlmostEqual(flow.y - start, estimated)
        self.assertAlmostEqual(flow.drawn[0][1], 23.17 - .55)
        self.assertEqual(flow._contact_detail_inset, 99.0)

    def test_wrapped_contact_uses_postal_marks_actual_row_column(self):
        flow = FlowProbe()
        flow._rule_material_style = 'notice'
        block = {'type': 'paragraph', 'rule_style': 'contact', 'text': '案内' * 12 + '〒１１１'}
        flow.block(block, 0, 200)
        self.assertGreater(len(flow.drawn), 1)
        self.assertGreaterEqual(flow._contact_detail_inset, 0)
        self.assertLess(flow._contact_detail_inset, 150)

    def test_wrapped_notice_title_adds_after_title_space_only_once(self):
        flow = FlowProbe()
        flow._rule_material_style = 'notice'
        block = {'type': 'heading', 'text': '長いお知らせの見出し' * 3}
        estimated = flow.estimate_block(block, 220)
        start = flow.y
        flow.block(block, 0, 220)
        self.assertAlmostEqual(flow.y - start, estimated)
        self.assertGreater(len(flow.drawn), 1)
        self.assertAlmostEqual(flow.drawn[1][2] - flow.drawn[0][2], flow.leading)

    def test_notice_title_underline_follows_new_page_origin(self):
        flow = FlowProbe()
        flow._rule_material_style = 'notice'
        flow.y = 774
        flow.block({'type': 'heading', 'text': 'お知らせ'}, 0, 300)
        self.assertEqual(len(flow.pages), 2)
        self.assertAlmostEqual(flow.decorations[-1][0], flow.left - 23.17)
        self.assertAlmostEqual(flow.decorations[-1][1], flow.drawn[-1][2] + 5.7371)


if __name__ == '__main__':
    unittest.main()
