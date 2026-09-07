"""Content-independent listening rule geometry and wrapping contracts."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from component_layout import ComponentLayout
from inline import Atom
from listening_rules import ListeningRules, ListeningStyle, instruction_chunks
from rule_typography import RuleFonts, TypographyRules


class CellCatalog:
    compress_ruby = True

    def width(self, char, size, bold=False, section='', role=None):
        if char == ' ':
            return size / 2
        return size


class RuleDouble(ListeningRules, ComponentLayout):
    def __init__(self):
        self.catalog = CellCatalog()
        self.section = 'L'
        self.left = 50
        self.width = 513.6
        self.top, self.bottom = 61.4489, 800
        self.page = {}
        self.y = 100
        self.rows = []
        self.glyphs = []

    def ensure(self, height):
        pass

    def line(self, atoms, x, top, size, *args, **kwargs):
        self.rows.append((''.join(atom.text for atom in atoms), x, top, size))

    def glyph(self, char, size, x, baseline, *args, **kwargs):
        self.glyphs.append((char, size, x, baseline, kwargs))


class PartitionCatalog(CellCatalog):
    prepare_atoms = RuleFonts.prepare_atoms


class PagedHeadingDouble(RuleDouble):
    def __init__(self):
        super().__init__()
        self.page_number = 1

    def ensure(self, height):
        if height > self.bottom - self.top:
            raise ValueError('Heading chunk exceeds usable page height')
        if self.y + height > self.bottom:
            self.y = self.top
            self.left += 20
            self.page_number += 1


class RubyInstructionDouble(ListeningRules, TypographyRules, ComponentLayout):
    def __init__(self):
        self.catalog = PartitionCatalog()
        self.section = 'L'
        self.left, self.width, self.y = 50, 120, 100
        self.glyphs = []

    def ensure(self, height):
        pass

    def glyph(self, char, size, x, baseline, *args, **kwargs):
        self.glyphs.append((char, size, x, baseline, kwargs))

    def rule(self, *args, **kwargs):
        pass


class ListeningRuleTests(unittest.TestCase):
    heading_group = {'kind': 'listening_choice', 'title': '｜問題《もんだい》１',
                     'instruction': '日本語の文章です。\n説明です。'}

    def test_heading_plan_is_pure_and_includes_all_instruction_rows(self):
        layout = RuleDouble()
        before = layout.y
        plan = layout.listening_heading_plan(self.heading_group, {})
        self.assertEqual(layout.y, before)
        self.assertEqual(layout.rows, [])
        self.assertEqual(layout.glyphs, [])
        self.assertEqual(len(plan['rows']), 2)
        self.assertAlmostEqual(plan['height'], 51.204 + 2 * 25.47 + 21.606)
        self.assertAlmostEqual(plan['first_chunk_height'], 51.204 + 25.47)

    def test_same_page_heading_uses_current_cursor_not_page_top(self):
        first, second = RuleDouble(), RuleDouble()
        first.y, second.y = first.top, first.top + 200
        first._listening_heading(self.heading_group, {})
        second._listening_heading(self.heading_group, {})
        self.assertEqual([row[0] for row in first.rows], [row[0] for row in second.rows])
        for a, b in zip(first.rows, second.rows):
            self.assertAlmostEqual(b[2] - a[2], 200)
        for a, b in zip(first.glyphs, second.glyphs):
            self.assertAlmostEqual(b[3] - a[3], 200)
        self.assertAlmostEqual(second.y - first.y, 200)

    def test_heading_top_overhang_tracks_actual_planned_ruby_and_size(self):
        layout = RuleDouble()
        default = layout.listening_heading_plan(self.heading_group, {})
        large = layout.listening_heading_plan(self.heading_group, {'heading_size': 72})
        plain = layout.listening_heading_plan({**self.heading_group, 'title': '問題１'}, {})
        empty = layout.listening_heading_plan({**self.heading_group, 'title': ''}, {})
        self.assertAlmostEqual(default['top_overhang'], 18 - .2312)
        self.assertAlmostEqual(large['top_overhang'], 2 * default['top_overhang'])
        self.assertAlmostEqual(plain['top_overhang'], 36 - 34.0712)
        self.assertEqual(empty['top_overhang'], 0)

    def test_heading_draw_uses_the_plan_without_remeasuring_text(self):
        layout = RuleDouble()
        plan = layout.listening_heading_plan(self.heading_group, {})
        layout.catalog = None
        layout.draw_listening_heading(plan)
        self.assertEqual([row[0] for row in layout.rows], ['日本語の文章です。', '説明です。'])

    def test_heading_moves_title_and_first_row_together_at_page_end(self):
        layout = PagedHeadingDouble()
        layout.y = layout.bottom - 40
        plan = layout.listening_heading_plan(self.heading_group, {})
        layout.draw_listening_heading(plan)
        self.assertEqual(layout.page_number, 2)
        self.assertEqual(layout.glyphs[0][2], 70)
        self.assertAlmostEqual(layout.glyphs[0][3], layout.top + 34.0712)
        self.assertAlmostEqual(layout.rows[0][2], layout.top + 51.204)

    def test_long_heading_instructions_paginate_without_losing_rows(self):
        layout = PagedHeadingDouble()
        layout.bottom = layout.top + 160
        layout.y = layout.top
        group = {**self.heading_group, 'instruction': '\n'.join(['日本語です。'] * 20)}
        layout._listening_heading(group, {})
        self.assertEqual([row[0] for row in layout.rows], ['日本語です。'] * 20)
        self.assertGreater(layout.page_number, 1)
        self.assertTrue(all(row[2] + 25.47 <= layout.bottom + 1e-6 for row in layout.rows))
        self.assertEqual(sum(glyph[0] == '問' for glyph in layout.glyphs), 1)

    def test_unbreakable_title_and_first_row_must_fit_before_drawing(self):
        layout = PagedHeadingDouble()
        layout.bottom = layout.top + 60
        with self.assertRaisesRegex(ValueError, 'usable page height'):
            layout._listening_heading(self.heading_group, {})
        self.assertEqual(layout.glyphs, [])
        self.assertEqual(layout.rows, [])

    def test_memo_heading_has_no_answer_panel_gap(self):
        layout = RuleDouble()
        group = {**self.heading_group, 'kind': 'listening_memo'}
        plan = layout.listening_heading_plan(group, {})
        self.assertEqual(plan['after'], 0)
        before = layout.y
        layout.draw_listening_heading(plan)
        self.assertAlmostEqual(layout.y - before, plan['height'])

    def test_oversized_custom_title_fails_before_drawing(self):
        layout = RuleDouble()
        with self.assertRaisesRegex(ValueError, 'title must fit'):
            layout._listening_heading({**self.heading_group, 'title': '問題' * 20}, {})
        self.assertEqual(layout.glyphs, [])

    def test_first_line_indent_preserves_the_text_measure(self):
        layout = RuleDouble()
        rows = layout._listening_instruction_plan('あいうえおかきくけこ', 40, 10, 10)
        layout._draw_listening_instruction_rows(rows, 10, 20)
        self.assertEqual([row[0] for row in layout.rows], ['あいうえ', 'おかきく', 'けこ'])
        self.assertEqual([row[1] for row in layout.rows], [60, 50, 50])
        self.assertEqual([row[2] for row in layout.rows], [100, 120, 140])

    def test_each_semantic_paragraph_gets_its_own_indent(self):
        layout = RuleDouble()
        rows = layout._listening_instruction_plan('あい\n\nうえ', 40, 10, 10)
        layout._draw_listening_instruction_rows(rows, 10, 20)
        self.assertEqual([(row[0], row[1]) for row in layout.rows], [('あい', 60), ('うえ', 60)])

    def test_ruby_cluster_is_not_broken_by_the_instruction_measure(self):
        layout = RuleDouble()
        rows = layout._listening_instruction_plan('あいう｜漢字《かんじ》え', 40, 10, 10)
        layout._draw_listening_instruction_rows(rows, 10, 20)
        self.assertEqual([row[0] for row in layout.rows], ['あいう', '漢字え'])

    def test_measure_scales_and_respects_custom_body_width(self):
        style = ListeningStyle()
        self.assertEqual(style.instruction_measure('listening_choice', 10, 600, 10), 430)
        self.assertEqual(style.instruction_measure('listening_memo', 10, 600, 10), 410)
        self.assertEqual(style.instruction_measure('listening_choice', 10, 300, 10), 290)
        self.assertEqual(style.instruction_measure('listening_choice', 10, 600, 10, 30), 300)

    def test_label_number_and_ruby_follow_the_component_anchor(self):
        layout = RuleDouble()
        layout.listen_label('1｜番《ばん》', 80, x=100)
        self.assertEqual([(g[0], g[2]) for g in layout.glyphs],
                         [('1', 100), ('番', 118), ('ば', 118), ('ん', 128)])
        self.assertAlmostEqual(layout.glyphs[2][3], 80 - 18.8077)

    def test_kana_word_after_a_particle_stays_together(self):
        atoms = [Atom('質問', ruby='しつもん', width=20)]
        atoms += [Atom(char, width=10) for char in 'とせんたくしを']
        chunks = instruction_chunks(atoms, 100)
        self.assertEqual([atom.text for atom in chunks], ['質問', 'と', 'せんたくしを'])
        self.assertEqual(sum(atom.width for atom in chunks), sum(atom.width for atom in atoms))

    def test_kana_word_at_paragraph_start_keeps_its_first_character(self):
        atoms = [Atom(char, width=10) for char in 'はさみ']
        self.assertEqual([atom.text for atom in instruction_chunks(atoms, 100)], ['はさみ'])

    def test_long_kana_run_can_still_reflow_in_a_narrow_body(self):
        atoms = [Atom(char, width=10) for char in 'あいうえお']
        self.assertEqual(instruction_chunks(atoms, 40), atoms)

    def test_memo_center_follows_a_narrow_custom_field(self):
        layout = RuleDouble()
        layout.width = 200
        layout.top = 0
        layout.bottom = 800
        layout.gc = {}
        original_config = layout.gc
        layout._listening_memo({'label': '－メモ－', 'height': 100})
        left = layout.glyphs[0][2]
        right = layout.glyphs[-1][2] + layout.glyphs[-1][1]
        self.assertAlmostEqual((left + right) / 2, layout.left + layout.width / 2)
        self.assertIs(layout.gc, original_config)

    def test_custom_title_uses_its_own_reading(self):
        layout = RuleDouble()
        glyphs, _ = layout._listening_title_glyphs('｜練習《れんしゅう》１', 36)
        layout._draw_listening_title(glyphs, 100, 66)
        self.assertEqual(''.join(g[0] for g in layout.glyphs), '練習れんしゅう１')
        ruby = [g for g in layout.glyphs if g[4]['role'] == 'ruby-heading']
        self.assertEqual(ruby[0][2], layout.left)
        self.assertAlmostEqual(ruby[0][4]['hscale'], .8)

    def test_title_without_ruby_does_not_invent_a_reading(self):
        layout = RuleDouble()
        glyphs, _ = layout._listening_title_glyphs('練習１', 36)
        layout._draw_listening_title(glyphs, 100, 66)
        self.assertEqual(''.join(g[0] for g in layout.glyphs), '練習１')

    def test_tracked_instruction_does_not_compress_internal_ruby_spacing(self):
        layout = RubyInstructionDouble()
        layout._listening_instruction('｜問題《もん|だい》です。', 120, tracking=-.27)
        body = [glyph for glyph in layout.glyphs if glyph[1] == 11.3]
        ruby = [glyph for glyph in layout.glyphs if glyph[1] == 5.6]
        self.assertAlmostEqual(body[1][2] - body[0][2], 11.3 - .27)
        self.assertAlmostEqual(ruby[1][2] - ruby[0][2], 5.57984)
        self.assertAlmostEqual(ruby[2][2] - body[1][2], .06 + (11.3 - 11.31017) / 2)

    def test_tracking_applies_only_to_the_first_instruction_row(self):
        layout = RubyInstructionDouble()
        layout._listening_instruction('日本語の文章です。日本語の文章です。', 70, tracking=-.3)
        rows = {}
        for glyph in layout.glyphs:
            rows.setdefault(glyph[3], []).append(glyph)
        first, rest = list(rows.values())[:2]
        self.assertAlmostEqual(first[1][2] - first[0][2], 11.0)
        self.assertAlmostEqual(rest[1][2] - rest[0][2], 11.3)
        for row in rows.values():
            self.assertLessEqual(row[-1][2] + 11.3, layout.left + 70)

    def test_instruction_dimensions_and_signed_tracking_must_be_finite(self):
        for key in ('width', 'size', 'leading', 'tracking'):
            for value in (float('inf'), -float('inf'), float('nan'), True, 'invalid', None):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    options = {'width': 70, key: value}
                    RubyInstructionDouble()._listening_instruction('日本語です。', **options)

if __name__ == '__main__':
    unittest.main()
