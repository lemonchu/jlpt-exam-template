"""Shared choice fit decisions must agree with their rendered spacing."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from choice_rules import ChoiceRules, ChoiceRow, DialogueLabel, choice_gaps, choice_rows
from component_layout import ComponentLayout
from geometry import CHOICE
from inline import Atom


def atoms(text, size=10):
    return [Atom(char, width=size) for char in text]


class CellCatalog:
    compress_ruby = True

    def width(self, char, size, *args, **kwargs):
        return size


class ChoiceProbe(ChoiceRules, ComponentLayout):
    def __init__(self):
        self.catalog = CellCatalog()
        self.section = 'G'
        self.group = {'kind': 'choice'}
        self.gc = {'options_columns': 1}
        self.fs, self.leading = 11.3, 24.06
        self.width = 452.41


class ChoiceRuleTests(unittest.TestCase):
    def test_adjacent_punctuation_uses_shared_half_cell(self):
        row = atoms('文）、次')
        gaps = choice_gaps(row, 45, 10)
        self.assertIsNotNone(gaps)
        self.assertLess(gaps[1], -4.9)

    def test_only_eligible_gaps_receive_tightening(self):
        row = atoms('本文、本文')
        gaps = choice_gaps(row, 49.4, 10, maximum=.4)
        self.assertAlmostEqual(sum(gaps), -.6)
        self.assertEqual(gaps[1:3], [0, 0])

    def test_measurement_rejects_a_row_beyond_its_shrink_budget(self):
        self.assertIsNone(choice_gaps(atoms('本文本文'), 38, 10, maximum=.4))

    def test_kana_priority_never_changes_the_existing_row_fit_budget(self):
        for text in ('考えを認め合える', '本文、話を聞く。', '漢字本文', '「かなの言葉」、本文'):
            row = atoms(text)
            for maximum in (0, .18, .45):
                for width in range(max(1, len(row) * 10 - 20), len(row) * 10 + 10):
                    with self.subTest(text=text, maximum=maximum, width=width):
                        previous = choice_gaps(row, width, 10, maximum=maximum, bearings=True)
                        proposed = choice_gaps(row, width, 10, maximum=maximum, bearings=True, kana=True)
                        self.assertEqual(previous is None, proposed is None)

    def test_kana_priority_is_only_automatic_for_reading_answers(self):
        layout = ChoiceProbe()
        text = '考えを認め合える'
        width = len(text) * 10 - .3
        for reading, option, explicit in [(False, True, False), (True, False, False),
                                           (True, True, True), (True, True, False)]:
            layout.gc = {'choice_option_max_negative_tracking': .18} if explicit else {}
            with patch('choice_rules.kana_compressed_gaps', return_value=None) as helper:
                layout._choice_paragraph(text, width, width, 10, reading=reading, option=option)
                self.assertEqual(helper.called, reading and option and not explicit)

    def test_overflowing_punctuation_can_hang_at_the_right_edge(self):
        self.assertEqual(choice_gaps(atoms('本文。'), 20, 10), [0, 0])

    def test_wrapping_keeps_closing_punctuation_with_content(self):
        rows = choice_rows(atoms('本文「内容」。'), 40, 40, 10)
        self.assertTrue(all(row[0].text not in '」。' for row in rows))
        self.assertEqual(''.join(atom.text for row in rows for atom in row), '本文「内容」。')

    def test_ruby_cluster_remains_indivisible(self):
        rows = choice_rows(atoms('あい') + [Atom('漢字', ruby='かんじ', width=20)], 30, 30, 10)
        self.assertEqual([''.join(atom.text for atom in row) for row in rows], ['あい', '漢字'])

    def test_explicit_paragraphs_reset_the_first_line_indent(self):
        layout = ChoiceProbe()
        plan = layout.choice_metrics({'prompt': '説明文\n本文', 'options': ['甲', '乙', '丙', '丁']})
        self.assertEqual(plan['prompt_insets'], [CHOICE.prompt_inset(0)] * 2)

    def test_explicit_option_newlines_are_preserved_even_when_the_text_fits(self):
        layout = ChoiceProbe()
        plan = layout.choice_metrics({'prompt': '本文', 'options': ['甲乙\n丙', '丙', '丁', '戊']})
        self.assertEqual([''.join(atom.text for atom in row) for row in plan['oplines'][0]],
                         ['甲乙', '丙'])
        self.assertEqual(sum(plan['oplines'][0][0].gaps), 0)
        self.assertEqual(plan['row_counts'], [2, 1, 1, 1])

    def test_auto_columns_use_the_final_numeric_atom_widths(self):
        layout = ChoiceProbe()
        layout.gc['options_columns'] = 'auto'
        plan = layout.choice_metrics({'prompt': '説明', 'options': ['２０２３年１２月'] * 4})
        self.assertEqual(plan['cols'], 4)
        self.assertTrue(all(len(rows) == 1 for rows in plan['oplines']))

    def test_rule_fields_do_not_build_a_discarded_legacy_plan(self):
        layout = ChoiceProbe()
        item = {'prompt': '説明', 'options': ['甲', '乙', '丙', '丁']}
        with patch.object(ComponentLayout, 'choice_prompt_plan', side_effect=AssertionError('legacy prompt')):
            with patch.object(ComponentLayout, 'choice_option_plan', side_effect=AssertionError('legacy options')):
                with patch.object(layout, 'choice_option_atoms', wraps=layout.choice_option_atoms) as measured:
                    layout.choice_metrics(item)
                    self.assertEqual(measured.call_count, 4)

    def test_zero_shrink_budget_does_not_divide_by_zero(self):
        self.assertIsNone(choice_gaps(atoms('本文'), 19.9, 10, maximum=0))

    def test_impossible_punctuation_chain_reports_the_width_problem(self):
        with self.assertRaisesRegex(ValueError, 'kinsoku cluster exceeds choice width'):
            choice_rows(atoms('本文説明！？！）'), 40, 40, 10)

    def test_dialogue_names_share_a_field_without_a_name_dictionary(self):
        layout = ChoiceProbe()
        paragraphs = layout._prompt_paragraphs('長谷川「本文」\n森「返事」', 10)
        self.assertEqual([width for _, width in paragraphs], [30, 30])
        self.assertTrue(all(isinstance(row[0], DialogueLabel) for row, _ in paragraphs))
        self.assertEqual([''.join(part.text for part in row[0].parts) for row, _ in paragraphs],
                         ['長谷川', '森'])

    def test_a_single_quoted_sentence_is_not_guessed_to_be_dialogue(self):
        layout = ChoiceProbe()
        paragraphs = layout._prompt_paragraphs('友人は「本文」と言った。', 10)
        self.assertEqual(paragraphs[0][1], 0)

    def test_reading_answer_set_shares_the_single_row_fit_policy(self):
        layout = ChoiceProbe()
        layout.section = 'R'
        width = [(39.4, 39.4)]
        short = [atoms('甲乙丙丁') for _ in range(4)]
        self.assertEqual(layout._option_single_limit(short, width, 1, 10), .45)
        mixed = short[:3] + [atoms('甲乙丙丁戊')]
        self.assertEqual(layout._option_single_limit(mixed, width, 1, 10), .18)

    def test_compact_columns_leave_extra_clearance_before_the_next_label(self):
        layout = ChoiceProbe()
        row = ChoiceRow(atoms('本文説明文書'), [0] * 5)
        result = layout._compact_option([row], 60, 4, 0, 10)[0]
        self.assertAlmostEqual(result.uniform_tracking, -.505)
        self.assertLessEqual(sum(atom.width for atom in result)
                             + result.uniform_tracking * layout.tracking_gaps(result), 57.5)

    def test_compact_tracking_needs_a_next_neighbour_and_a_near_full_cell(self):
        layout = ChoiceProbe()
        row = ChoiceRow(atoms('本文説明文書'), [0] * 5)
        for width, columns, column in [(60, 4, 3), (60, 2, 0), (80, 4, 0)]:
            with self.subTest(width=width, columns=columns, column=column):
                self.assertEqual(layout._compact_option([row], width, columns, column, 10)[0].uniform_tracking, 0)

    def test_compact_tracking_honours_an_explicit_no_shrink_setting(self):
        layout = ChoiceProbe()
        layout.gc['choice_option_max_negative_tracking'] = 0
        row = ChoiceRow(atoms('本文説明文書'), [0] * 5)
        self.assertEqual(layout._compact_option([row], 60, 4, 0, 10)[0].uniform_tracking, 0)

    def test_ordering_slots_and_separators_share_the_body_cell_grid(self):
        layout = ChoiceProbe()
        row = layout.ordering_atoms('前 __  ★  __     __　　　　__ 後', 10)
        slots = [atom for atom in row if atom.underline]
        self.assertEqual([atom.width for atom in slots], [30, 30])
        self.assertEqual([atom.width for atom in row if atom.text == '　' and not atom.underline],
                         [10, 10, 10])

    def test_ordering_contraction_does_not_change_slot_width(self):
        layout = ChoiceProbe()
        layout.width = CHOICE.prompt_inset(0) + 99
        layout.gc['word_order_blank_max_negative_tracking'] = .5
        rows = layout._ordering_rows('本文本文 __★__ 後文', 10)
        self.assertLess(rows[0].rigid_tracking, 0)
        self.assertEqual([atom.width for atom in rows[0] if atom.underline], [30])

    def test_ordering_row_ending_in_a_slot_remains_ragged(self):
        layout = ChoiceProbe()
        layout.width = CHOICE.prompt_inset(0) + 105
        rows = layout._ordering_rows('本文本文 __　　　__ __★__ 後文', 10)
        self.assertGreater(len(rows), 1)
        self.assertTrue(rows[0][-1].underline or rows[0][-1].text.isspace())
        self.assertEqual(sum(rows[0].gaps), 0)

    def test_ordering_prose_ending_row_justifies_around_rigid_slots(self):
        layout = ChoiceProbe()
        layout.width = CHOICE.prompt_inset(0) + 107
        rows = layout._ordering_rows('本文 __★__ 後文長文章文章', 10)
        self.assertGreater(len(rows), 1)
        self.assertGreater(sum(rows[0].gaps), 0)
        for index, (left, right) in enumerate(zip(rows[0], rows[0][1:])):
            if left.underline or right.underline or left.text.isspace() or right.text.isspace():
                self.assertEqual(rows[0].gaps[index], 0)


if __name__ == '__main__':
    unittest.main()
