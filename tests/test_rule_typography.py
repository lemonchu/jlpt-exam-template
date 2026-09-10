"""Semantic ruby partitions and the relative rule typography contract."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from inline import parse, measure
from component_layout import ComponentLayout
from rule_typography import mono_ruby, ruby_layout, material_number_atoms, RuleFonts, TypographyRules, _CJK_ADVANCES


class RubyRuleTests(unittest.TestCase):
    def test_partitions_preserve_reading_and_record_character_boundaries(self):
        old = '｜商品《しょうひん》を選ぶ'
        new = '｜商品《しょう|ひん》を選ぶ'
        self.assertEqual(parse(old)[0].text, parse(new)[0].text)
        self.assertEqual(parse(old)[0].ruby, parse(new)[0].ruby)
        self.assertEqual(parse(new)[0].ruby, 'しょうひん')
        self.assertEqual(parse(new)[0].ruby_parts, ('しょう', 'ひん'))

    def test_rejects_missing_or_extra_reading_parts(self):
        for text in ('｜商品《しょう|》', '｜商品《|ひん》', '｜商品《し|よ|う》'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse(text)

    def test_three_kana_condense_without_widening_base(self):
        glyphs = mono_ruby('しょう', _CJK_ADVANCES[14.2], 14.2)
        self.assertEqual([glyph.hscale for glyph in glyphs], [.67] * 3)
        self.assertAlmostEqual(glyphs[-1].x, 9.4797496)
        self.assertLess(glyphs[-1].x + glyphs[-1].size * glyphs[-1].hscale, 14.25)

    def test_each_reading_follows_its_kanji_when_tracking_changes(self):
        atom = parse('｜商品《しょう|ひん》')[0]
        ordinary = ruby_layout(atom, [14.19006] * 2, 14.2)
        tracked = ruby_layout(atom, [14.19006] * 2, 14.2, tracking=-.2)
        self.assertEqual(ordinary[:3], tracked[:3])
        for before, after in zip(ordinary[3:], tracked[3:]):
            self.assertAlmostEqual(after.x, before.x - .2)
        self.assertEqual([glyph.hscale for glyph in ordinary], [.67, .67, .67, 1, 1])

    def test_group_ruby_is_centered_without_inventing_a_partition(self):
        atom = parse('｜昨日《きのう》')[0]
        glyphs = ruby_layout(atom, [14.19006] * 2, 14.2)
        self.assertAlmostEqual(glyphs[0].x, 1.18002)
        self.assertAlmostEqual(glyphs[1].x - glyphs[0].x, 9.46004)
        self.assertEqual([glyph.hscale for glyph in glyphs], [1] * 3)

    def test_large_reading_and_nonstandard_size_remain_bounded(self):
        for count in range(1, 9):
            glyphs = mono_ruby('あ' * count, 16, 16)
            self.assertGreater(glyphs[0].hscale, 0)
            self.assertLessEqual(glyphs[-1].x + glyphs[-1].size * glyphs[-1].hscale, 16.32)

    def test_narrow_base_ruby_uses_the_base_cell_center(self):
        wide = mono_ruby('えー', 11.31017, 11.3)
        narrow = mono_ruby('えー', 5.65, 11.3, available_width=11.31017)
        for full, half in zip(wide, narrow):
            self.assertAlmostEqual(half.x - full.x, (5.65 - 11.31017) / 2)

    def test_four_kana_stay_readable_in_an_expanded_cell(self):
        glyphs = mono_ruby('こころよ', 14.19006, 14.2, available_width=21.27018)
        self.assertEqual([glyph.hscale for glyph in glyphs], [.67] * 4)
        self.assertLess(glyphs[0].x, 0)
        self.assertLess(abs(glyphs[0].x - -2.33172), .07)
        self.assertLess(glyphs[-1].x + glyphs[-1].size * glyphs[-1].hscale, 14.19006 * 7 / 6 + .1)

    def test_material_numbers_keep_singles_and_join_numeric_separators(self):
        source = parse('２０１６年１１月１日、００２‐３８３３')
        atoms = material_number_atoms(source, UniformCatalog(), 11.3, 'R')
        self.assertEqual([atom.text for atom in atoms], ['２０１６', '年', '１１', '月', '１', '日', '、', '００２‐３８３３'])
        self.assertAlmostEqual(atoms[0].width, 4 * 5.63983)
        small = material_number_atoms(parse('２０１６'), UniformCatalog(), 9.2, 'R')
        self.assertAlmostEqual(small[0].width, 4 * 4.58988)

    def test_numeric_normalization_keeps_semantic_boundaries(self):
        source = parse('１**２**３｜４《よん》{{注|５}}６')
        atoms = material_number_atoms(source, UniformCatalog(), 11.3, 'R')
        self.assertEqual([atom.text for atom in atoms], list('１２３４５６'))
        self.assertEqual(atoms[3].ruby, 'よん')
        self.assertEqual(atoms[4].annotation, '（注）')


class UniformCatalog:
    compress_ruby = True

    def width(self, char, size, bold=False, section='', role=None):
        return size


class RuleCatalog(RuleFonts):
    def __init__(self):
        self.compress_ruby = True

    def width(self, char, size, bold=False, section='', role=None):
        return {11.3: 11.31017, 14.2: 14.19006}.get(size, size)


class TypographyDouble(TypographyRules, ComponentLayout):
    def __init__(self):
        self.catalog = UniformCatalog()
        self.section = 'R'
        self.glyphs = []
        self.rules = []

    def glyph(self, char, size, x, baseline, bold=False, color='', **kwargs):
        self.glyphs.append(dict(char=char, size=size, x=x, baseline=baseline, **kwargs))

    def rule(self, *args):
        self.rules.append(args)


class TypographyIntegrationTests(unittest.TestCase):
    def test_compact_numbers_keep_fullwidth_shapes_and_half_em_pitch(self):
        layout = TypographyDouble()
        atoms = material_number_atoms(measure(parse('年９０歳'), layout.catalog, 11.3, 'R'),
                                      layout.catalog, 11.3, 'R')
        layout.line(atoms, 100, 20, 11.3)
        self.assertEqual([glyph['char'] for glyph in layout.glyphs], list('年９０歳'))
        self.assertAlmostEqual(layout.glyphs[1]['x'], 100 + 11.3 - 11.3 / 4)
        self.assertAlmostEqual(layout.glyphs[2]['x'] - layout.glyphs[1]['x'], 5.63983)
        self.assertAlmostEqual(layout.glyphs[3]['x'] - layout.glyphs[2]['x'], 8.46483)

    def test_note_origin_tracks_base_without_shifting_body(self):
        layout = TypographyDouble()
        atoms = measure(parse('文{{注１|言葉}}末'), layout.catalog, 11.3, 'R')
        layout.line(atoms, 100, 200, 11.3)
        body = [glyph for glyph in layout.glyphs if glyph['size'] == 11.3]
        notes = [glyph for glyph in layout.glyphs if glyph['size'] == 6.4]
        self.assertEqual(''.join(glyph['char'] for glyph in body), '文言葉末')
        self.assertEqual(''.join(glyph['char'] for glyph in notes), '（注１）')
        self.assertAlmostEqual(notes[0]['x'], body[1]['x'] - 3.17)
        self.assertAlmostEqual(notes[0]['baseline'], body[1]['baseline'] + 6.9804)

    def test_partitioned_ruby_preserves_each_base_origin(self):
        layout = TypographyDouble()
        atoms = measure(parse('｜商品《しょう|ひん》'), layout.catalog, 14.2, 'L')
        layout.line(atoms, 100, 200, 14.2)
        body = [glyph for glyph in layout.glyphs if glyph['size'] == 14.2]
        ruby = [glyph for glyph in layout.glyphs if glyph['size'] == 7.1]
        self.assertEqual([glyph['x'] for glyph in body], [100, 114.2])
        self.assertAlmostEqual(ruby[3]['x'], body[1]['x'] + (14.2 - _CJK_ADVANCES[14.2]) / 2)
        self.assertEqual([glyph.get('hscale') for glyph in ruby], [.67, .67, .67, 1, 1])

    def test_long_ruby_reserves_space_and_moves_following_text(self):
        layout = TypographyDouble()
        layout.catalog = RuleCatalog()
        atoms = measure(parse('を｜快《こころよ》く'), layout.catalog, 14.2, 'L')
        self.assertAlmostEqual(atoms[1].width, 21.27018)
        layout.line(atoms, 100, 200, 14.2)
        body = [glyph for glyph in layout.glyphs if glyph['size'] == 14.2]
        ruby = [glyph for glyph in layout.glyphs if glyph['size'] == 7.1]
        self.assertAlmostEqual(body[1]['x'] - body[0]['x'], 17.73012)
        self.assertAlmostEqual(body[2]['x'] - body[1]['x'], 17.73012)
        self.assertEqual([glyph['hscale'] for glyph in ruby], [.67] * 4)

    def test_measured_partition_preserves_underlines_and_note_span(self):
        atoms = measure(parse('{{注|__｜商品《しょう|ひん》__}}'), RuleCatalog(), 14.2, 'L')
        self.assertEqual([atom.text for atom in atoms], ['商', '品'])
        self.assertEqual([atom.ruby for atom in atoms], ['しょう', 'ひん'])
        self.assertEqual([atom.underline for atom in atoms], [True, True])
        self.assertEqual([atom.annotation for atom in atoms], ['（注）', ''])
        self.assertEqual([atom.annotation_span for atom in atoms], [2, 0])
        self.assertAlmostEqual(sum(atom.width for atom in atoms), 28.38012)

    def test_variable_gaps_keep_note_attached_and_underline_connected(self):
        layout = TypographyDouble()
        atoms = measure(parse('__文章__{{注|言葉}}'), layout.catalog, 11.3, 'R')
        layout.line_gaps(atoms, 100, 200, 11.3, [1, 2, 0])
        body = [glyph for glyph in layout.glyphs if glyph['size'] == 11.3]
        notes = [glyph for glyph in layout.glyphs if glyph['size'] == 6.4]
        self.assertAlmostEqual(body[1]['x'], 112.3)
        self.assertAlmostEqual(body[2]['x'], 125.6)
        self.assertAlmostEqual(notes[0]['x'], body[2]['x'] - 3.17)
        self.assertIn((111.3, 214.3, 112.3, 214.3, .33), layout.rules)

    def test_variable_gaps_keep_internal_tracking_and_ruby_in_the_same_plan(self):
        layout = TypographyDouble()
        atoms = measure(parse('｜漢字《かんじ》末'), layout.catalog, 11.3, 'R')
        layout.line_gaps(atoms, 100, 200, 11.3, [-.3], tracking=-.3)
        body = [glyph for glyph in layout.glyphs if glyph['size'] == 11.3]
        self.assertAlmostEqual(body[1]['x'] - body[0]['x'], 11.0)
        self.assertAlmostEqual(body[2]['x'] - body[1]['x'], 11.0)


if __name__ == '__main__':
    unittest.main()
