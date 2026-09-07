"""Page boundaries for cloze articles and their explanatory notes."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_reading_rules import FlowProbe
from component_layout import ComponentLayout


class NoteFlowTests(unittest.TestCase):
    def flow(self):
        flow = FlowProbe()
        flow.section, flow.group = 'G', {'kind': 'cloze'}
        return flow

    @staticmethod
    def note(text='本文', number=1):
        return {'type': 'paragraph', 'style': 'small', 'text': f'（注{number}）{text}'}

    def test_last_note_fits_by_ink_without_reserving_empty_leading(self):
        flow = self.flow()
        flow.y = flow.bottom - 20.96 - 11.3 * 1.25 - .1
        flow.blocks([self.note()])
        self.assertEqual(len(flow.pages), 1)
        self.assertLess(flow.drawn[-1][2] + 11.3 * .25, flow.bottom)

    def test_notes_fill_current_page_then_rebase_on_the_next_page(self):
        flow = self.flow()
        flow.y = flow.bottom - 40
        notes = [self.note(number=i) for i in range(1, 4)]
        flow.blocks(notes, x=9)
        self.assertEqual([row[0] for row in flow.drawn], [1, 2, 2])
        self.assertEqual([row[3] for row in flow.drawn], [n['text'] for n in notes])
        self.assertAlmostEqual(flow.drawn[0][1], 9)
        self.assertAlmostEqual(flow.drawn[1][1], 9 + 15.33)

    def test_one_wrapped_note_stays_whole_when_it_fits_a_fresh_page(self):
        flow = self.flow()
        flow.y = flow.bottom - 45
        note = self.note('本文' * 12)
        flow.blocks([note], x=7, width=120)
        self.assertGreater(len(flow.drawn), 1)
        self.assertEqual({row[0] for row in flow.drawn}, {2})
        self.assertEqual(''.join(row[3] for row in flow.drawn), note['text'])
        self.assertTrue(flow._last_note_wrapped)
        self.assertAlmostEqual(flow.drawn[0][1], 7 + 15.33)

    def test_note_longer_than_a_page_flows_without_losing_text(self):
        flow = self.flow()
        flow.bottom = 120
        note = self.note('本文' * 100)
        flow.blocks([note], width=120)
        self.assertGreater(len(flow.pages), 2)
        self.assertEqual(''.join(row[3] for row in flow.drawn), note['text'])
        self.assertTrue(all(row[2] + 11.3 * .25 <= flow.bottom for row in flow.drawn))

    def test_below_word_annotation_is_included_in_note_fit(self):
        flow = self.flow()
        flow.y = flow.bottom - 20.96 - 16
        flow.blocks([self.note('{{注|本文}}')])
        self.assertEqual({row[0] for row in flow.drawn}, {2})

    def test_note_measurement_plan_is_reused_and_does_not_leak(self):
        flow = self.flow()
        with patch.object(flow, '_reading_rows', wraps=flow._reading_rows) as measure:
            flow.blocks([self.note('本文' * 12)], width=120)
        self.assertEqual(measure.call_count, 1)
        self.assertIsNone(flow._pending_note_rows)

    def test_other_reading_notes_keep_the_existing_group_policy(self):
        flow = FlowProbe()
        flow.y = flow.bottom - 50
        flow.blocks([self.note(number=i) for i in range(1, 4)])
        self.assertEqual({row[0] for row in flow.drawn}, {2})

    def test_legacy_note_policy_still_keeps_the_whole_list(self):
        flow = self.flow()
        flow.y = flow.bottom - 40
        flow.reading_notes = lambda notes, x, width: ComponentLayout.reading_notes(flow, notes, x, width)
        flow.blocks([self.note(number=i) for i in range(1, 4)])
        self.assertEqual({row[0] for row in flow.drawn}, {2})


class MaterialQuestionFlowTests(unittest.TestCase):
    def flow(self, kind='cloze'):
        flow = FlowProbe()
        flow.section = 'G' if kind == 'cloze' else 'R'
        flow.group = {'kind': kind}
        flow.bottom = 160
        flow._first_group_item = True
        flow.question_pages = []

        def choice(question):
            flow.ensure(30)
            flow.question_pages.append(len(flow.pages))
            flow.y += 30

        flow.choice = choice
        return flow

    @staticmethod
    def passage(rows):
        return {'stimulus': [{'type': 'paragraph', 'text': '\n'.join(['本文'] * rows)}],
                'questions': [{'id': 'q1', 'prompt': '', 'options': ['甲', '乙', '丙', '丁']}]}

    def test_single_page_cloze_preserves_separate_answer_page(self):
        flow = self.flow()
        flow.passage(self.passage(1))
        self.assertEqual(flow.question_pages, [2])

    def test_overflowing_cloze_answers_follow_material_on_second_page(self):
        for config in ({}, {'questions_new_page': True}):
            with self.subTest(config=config):
                flow = self.flow()
                flow.gc = config
                flow.passage(self.passage(5))
                self.assertEqual(flow.drawn[-1][0], 2)
                self.assertEqual(flow.question_pages, [2])

    def test_continuing_answers_still_move_when_remaining_space_is_too_small(self):
        flow = self.flow()
        flow.passage(self.passage(6))
        self.assertEqual(flow.drawn[-1][0], 2)
        self.assertEqual(flow.question_pages, [3])

    def test_explicit_reading_page_break_survives_material_overflow(self):
        flow = self.flow('reading')
        flow.gc['questions_new_page'] = True
        flow.passage(self.passage(5))
        self.assertEqual(flow.question_pages, [3])

    def test_false_allows_answers_after_a_short_cloze(self):
        flow = self.flow()
        flow.gc['questions_new_page'] = False
        flow.passage(self.passage(1))
        self.assertEqual(flow.question_pages, [1])

    def test_overflow_state_does_not_affect_the_next_passage(self):
        flow = self.flow()
        flow.passage(self.passage(5))
        flow._first_group_item = False
        flow.passage(self.passage(1))
        self.assertEqual(flow.question_pages, [2, 4])

    def test_legacy_cloze_keeps_its_forced_answer_page(self):
        flow = self.flow()
        flow.break_before_questions = lambda page: ComponentLayout.break_before_questions(flow, page)
        flow.passage(self.passage(5))
        self.assertEqual(flow.question_pages, [3])


if __name__ == '__main__':
    unittest.main()