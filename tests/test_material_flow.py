"""Page boundaries for reading/cloze articles and their explanatory notes."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_reading_rules import FlowProbe


class NoteFlowTests(unittest.TestCase):
    def flow(self):
        flow = FlowProbe()
        flow.section, flow.group = 'G', {'kind': 'cloze'}
        return flow

    @staticmethod
    def note(text='本文', number=1):
        label=str(number).translate(str.maketrans('0123456789', '０１２３４５６７８９'))
        return {'type': 'paragraph', 'style': 'small', 'text': f'（注{label}）{text}'}

    def test_imported_note_labels_match_reference_wrapping_and_page_fit(self):
        class MixedWidthCatalog:
            compress_ruby = True

            def width(self, char, size, *args, **kwargs):
                return size * (.5 if char.isascii() else 1)

        # At this width the old halfwidth label fits one line, but the reference
        # fullwidth label wraps. The measurement and drawing must agree.
        for section in ('G', 'R'):
            for label in ('（注1）', '(注1)', '（注 1）', '（注１）'):
                with self.subTest(section=section, label=label):
                    actual, reference = self.flow(), self.flow()
                    actual.section = reference.section = section
                    actual.catalog = reference.catalog = MixedWidthCatalog()
                    actual.y = reference.y = actual.bottom - 45
                    source = dict(self.note(), text=label+'本文')
                    before = dict(source)
                    wanted = self.note()
                    self.assertEqual(actual.estimate_block(source, 65),
                                     reference.estimate_block(wanted, 65))
                    actual.blocks([source], width=65)
                    reference.blocks([wanted], width=65)
                    self.assertEqual(actual.drawn, reference.drawn)
                    self.assertEqual(len(actual.drawn), 2)
                    self.assertEqual(source, before)

    def test_note_label_does_not_change_definition_numbers_or_inline_annotations(self):
        flow = self.flow()
        source = self.note('20世紀、2000年、{{注1|本文}}')
        source['text'] = source['text'].replace('注１', '注1', 1)
        self.assertEqual(flow.paragraph_body_text(source),
                         '（注１）20世紀、2000年、{{注1|本文}}')
        for text in ('本文（注1）', '（注）本文', '注1を参照', '（注A）本文'):
            self.assertEqual(flow.paragraph_body_text(dict(source, text=text)), text)
        self.assertEqual(flow.paragraph_body_text({'type': 'paragraph', 'text': '（注1）本文'}),
                         '（注1）本文')
        self.assertEqual(flow.paragraph_body_text(dict(source,text='(注)説明')), '（注）説明')

    def test_body_starting_with_a_note_reference_is_not_a_definition(self):
        flow=FlowProbe()
        body={'type':'paragraph','text':'（注1）ネット社会についての本文。'}
        self.assertFalse(flow._is_note(body))
        self.assertEqual(flow.reading_paragraph_gap(body),0)
        self.assertTrue(flow._is_note(dict(body,style='small')))

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

    def test_article_tail_source_and_glossary_do_not_leave_a_notes_only_page(self):
        flow=FlowProbe()
        flow.y=flow.bottom-130
        body={'type':'paragraph','text':'本文の末尾です。'*7}
        citation={'type':'paragraph','style':'small','align':'right','text':'（著者による）'}
        flow.blocks([body,citation]+[self.note(number=i) for i in range(1,5)],width=120)
        note_pages={r[0] for r in flow.drawn if '（注' in r[3]}
        self.assertEqual(len(note_pages),1)
        final_page=note_pages.pop()
        self.assertGreater(final_page,1)
        self.assertTrue(any(r[0]==final_page and '本文' in r[3] for r in flow.drawn))
        self.assertTrue(any(r[0]==final_page and '著者' in r[3] for r in flow.drawn))

    def test_glossary_can_start_next_page_without_dragging_article_tail(self):
        flow=FlowProbe();flow.bottom=340;flow.y=238
        flow.blocks([{'type':'paragraph','text':'本文'*8},
                     {'type':'paragraph','style':'small','align':'right','text':'（出典）'},
                     self.note('説明')],width=120)
        self.assertEqual([row[0] for row in flow.drawn], [1, 1, 1, 2])
        self.assertEqual(flow.drawn[2][3], '（出典）')
        self.assertEqual(flow.drawn[-1][3], '（注１）説明')

    def test_citation_still_stays_with_article_when_both_cannot_fit(self):
        flow=FlowProbe();flow.bottom=340;flow.y=284
        flow.blocks([{'type':'paragraph','text':'本文'*8},
                     {'type':'paragraph','style':'small','align':'right','text':'（出典）'}],width=120)
        self.assertEqual({row[0] for row in flow.drawn}, {2})
        self.assertEqual(''.join(row[3] for row in flow.drawn), '本文'*8+'（出典）')

    def test_citation_tail_keeps_the_enclosing_frame_bottom_reserve(self):
        flow=FlowProbe();flow.bottom=340;flow.y=250
        flow.blocks([{'type':'paragraph','text':'本文'*8},
                     {'type':'paragraph','style':'small','align':'right','text':'（出典）'}],
                    width=120,tail_reserve=40)
        self.assertEqual({row[0] for row in flow.drawn}, {2})
        self.assertLessEqual(flow.drawn[-1][2] + 40, flow.bottom)

    def test_cloze_frame_excludes_notes_and_keeps_its_tail_on_their_page(self):
        flow=self.flow();flow.y=flow.bottom-155
        body={'type':'box','blocks':[{'type':'paragraph','text':'本文の末尾です。'*7}]}
        flow.blocks([body,self.note()],width=140)
        note=next(r for r in flow.drawn if '（注' in r[3])
        self.assertTrue(any(r[0]==note[0] and '本文' in r[3] for r in flow.drawn))
        self.assertEqual(flow._last_material_kind,'note')

    def test_following_glossary_does_not_push_whole_frame_away_from_heading(self):
        flow=self.flow()
        body={'type':'box','blocks':[{'type':'paragraph','text':'本文の末尾です。'*10}]}
        estimated=flow.estimate_block(body,140)
        flow.y=flow.bottom-estimated-1
        flow.blocks([body]+[self.note(number=i) for i in range(1,4)],width=140)
        self.assertEqual(flow.drawn[0][0],1)
        note_pages={r[0] for r in flow.drawn if '（注' in r[3]}
        self.assertEqual(len(note_pages),1)
        self.assertTrue(any(r[0] in note_pages and '本文' in r[3] for r in flow.drawn))

    def test_continued_cloze_frame_preserves_top_margin_for_ruby(self):
        flow=self.flow();flow.bottom=210
        body={'type':'box','blocks':[{'type':'paragraph','text':'本文の末尾です。'*10}]}
        flow.blocks([body],width=140)
        for page in range(2,len(flow.pages)+1):
            first=next(row for row in flow.drawn if row[0]==page)
            self.assertGreaterEqual(first[2]-flow.fs,flow.top+24.15)
        self.assertEqual(flow._flow_frame_top_padding,0)

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
        for kind in ('cloze', 'reading'):
            with self.subTest(kind=kind):
                flow = self.flow(kind)
                flow.gc['questions_new_page'] = True
                flow.passage(self.passage(6))
                self.assertEqual(flow.drawn[-1][0], 2)
                self.assertEqual(flow.question_pages, [3])

    def test_continued_reading_body_and_question_share_second_page(self):
        flow = self.flow('reading')
        flow.gc['questions_new_page'] = True
        flow.passage(self.passage(5))
        self.assertEqual(flow.drawn[-1][0], 2)
        self.assertEqual(flow.question_pages, [2])

    def test_one_page_reading_article_keeps_configured_question_page(self):
        flow = self.flow('reading')
        flow.gc['questions_new_page'] = True
        flow.passage(self.passage(1))
        self.assertEqual(flow.drawn[-1][0], 1)
        self.assertEqual(flow.question_pages, [2])

    def test_reading_questions_share_the_page_of_continued_glossary(self):
        flow = self.flow('reading')
        flow.bottom, flow.y = 220, 140
        flow.gc['questions_new_page'] = True
        item = self.passage(2)
        item['stimulus'] += [NoteFlowTests.note(number=n) for n in (1, 2)]
        flow.passage(item)
        body = [r for r in flow.drawn if not r[3].startswith('（注')]
        notes = [r for r in flow.drawn if r[3].startswith('（注')]
        self.assertEqual({r[0] for r in body}, {1})
        self.assertEqual({r[0] for r in notes}, {2})
        self.assertEqual(flow.question_pages, [2])

    def test_glossary_continuation_state_is_reset_for_the_next_passage(self):
        flow = self.flow('reading')
        flow.gc['questions_new_page'] = True
        flow._glossary_only_page = flow.page
        flow.passage(self.passage(1))
        self.assertEqual(flow.question_pages, [2])

    def test_new_body_after_an_intermediate_glossary_restores_reading_page_break(self):
        flow = self.flow('reading')
        flow.gc['questions_new_page'] = True
        flow._glossary_only_page = flow.page
        flow._last_material_kind = 'note'
        flow.block({'type': 'paragraph', 'text': 'さらに本文が続く。'})
        self.assertIsNone(flow._glossary_only_page)
        self.assertTrue(flow.break_before_questions(flow.page))

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

if __name__ == '__main__':
    unittest.main()
