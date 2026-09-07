"""Opening keeps share existing plans without emitting pages or advancing IDs."""
from pathlib import Path
from types import SimpleNamespace
import copy
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from choice_rules import ChoiceRules
from component_layout import ComponentLayout
from group_flow import GroupFlow
from ordering_templates import OrderingTemplates, load_ordering_template
from reading_rules import ReadingRules, cloze_frame
from test_written_rules import Catalog
from written_rules import WrittenRules


class Probe(GroupFlow, OrderingTemplates, ReadingRules, WrittenRules, ChoiceRules, ComponentLayout):
    def __init__(self, kind='reading', section='R'):
        reference = SimpleNamespace(profile=ROOT / 'profiles/n1-original', resolved={}, ledger=[])
        super().__init__(Catalog(), {'page': {'body_bottom': 783}}, ROOT / 'resources',
                         ROOT / 'tmp', reference)
        self.section = section
        self.group = dict(id=section + '99', kind=kind)
        self.gc = {}
        self.geometry()

    def new_page(self):
        raise AssertionError('Measuring an opening must not create a page')

    def emit(self, command):
        raise AssertionError('Measuring an opening must not draw')


class GroupFlowTests(unittest.TestCase):
    def test_empty_group_needs_no_first_unit(self):
        flow = Probe()
        self.assertEqual(flow.first_item_keep(dict(flow.group, items=[]), {}),
                         dict(minimum=0, preferred=0, break_before=False))

    def test_choice_measurement_is_returned_for_drawing_once(self):
        flow = Probe('choice', 'V')
        item = dict(id='new', prompt='本文', options=['甲', '乙', '丙', '丁'])
        with patch.object(flow, 'choice_metrics', wraps=flow.choice_metrics) as measured:
            result = flow.first_item_keep(dict(flow.group, items=[item]), {})
        self.assertEqual(measured.call_count, 1)
        self.assertIs(result['choice_item'], item)
        self.assertEqual(result['preferred'], result['choice_plan']['total'])
        self.assertEqual(result['minimum'], flow.leading)
        self.assertFalse(flow.pages)
        self.assertEqual(flow.number, 1)

    def test_textual_example_label_keeps_the_first_prompt_row(self):
        flow = Probe('choice', 'V')
        item = dict(id='demo', is_example=True, prompt='本文', options=['甲'] * 4)
        result = flow.first_item_keep(dict(flow.group, items=[item]), {})
        self.assertEqual(result['minimum'], 2 * flow.leading)

    def test_fixed_ordering_example_uses_its_own_existing_plan(self):
        flow = Probe('word_order', 'G')
        item = copy.deepcopy(load_ordering_template(flow.reference.profile)['example']['content'])
        expected = flow.ordering_example_plan(item)['advance']
        with patch.object(flow, 'ordering_example_plan', wraps=flow.ordering_example_plan) as measured:
            result = flow.first_item_keep(dict(flow.group, items=[item]), {})
        measured.assert_called_once_with(item)
        self.assertEqual(result, dict(minimum=expected, preferred=expected, break_before=False))
        self.assertFalse(flow.resolved)

    def test_long_reading_opening_keeps_ink_not_the_whole_article(self):
        flow = Probe()
        paragraph = dict(type='paragraph', text='長い本文を読みます。' * 100)
        item = dict(stimulus=[paragraph], questions=[], label='（１）')
        flow._last_was_note = True
        flow._last_material_kind = 'box'
        flow._contact_detail_inset = 73
        flow._rule_material_style = 'notice'
        result = flow.first_item_keep(dict(flow.group, items=[item]), {})
        self.assertLess(result['minimum'], 50)
        self.assertGreater(result['minimum'], 24.06)
        self.assertEqual(flow._contact_detail_inset, 73)
        self.assertTrue(flow._last_was_note)
        self.assertEqual(flow._last_material_kind, 'box')
        self.assertEqual(flow._rule_material_style, 'notice')
        self.assertFalse(hasattr(flow, '_rule_reading_block'))

    def test_below_word_notes_increase_the_opening_ink_reserve(self):
        flow = Probe()
        ordinary = flow.opening_block_keep(dict(type='paragraph', text='本文'), flow.width)
        annotated = flow.opening_block_keep(dict(type='paragraph', text='{{注|本文}}'), flow.width)
        self.assertGreater(annotated['minimum'], ordinary['minimum'])

    def test_cloze_frame_has_distinct_local_split_and_prefixed_group_heights(self):
        flow = Probe('cloze', 'G')
        block = dict(type='box', blocks=[dict(type='paragraph', text='長い本文です。' * 40)])
        item = dict(label='（１）', stimulus=[block], questions=[])
        result = flow.first_item_keep(dict(flow.group, items=[item]), {})
        frame = cloze_frame(flow.gc)
        self.assertIs(result['split_block'], block)
        self.assertAlmostEqual(result['split_minimum'], frame.before + frame.top + 2 * flow.leading)
        self.assertAlmostEqual(result['minimum'], result['split_minimum'] + 24.06)
        self.assertGreater(result['preferred'], result['minimum'])

    def test_table_keeps_headers_and_first_data_row_not_all_rows(self):
        flow = Probe()
        block = dict(type='table', header_rows=1, rows=[['見出し'], ['本文'], ['続き']])
        _, inner = flow.table_geometry(block, 0, flow.width)
        heights = flow.table_rows(block, inner)[1]
        with patch.object(flow, 'table_rows', wraps=flow.table_rows) as measured:
            result = flow.opening_block_keep(block, flow.width)
        measured.assert_called_once_with(block, inner)
        self.assertEqual(result['minimum'], sum(heights[:2]))
        self.assertLess(result['minimum'], sum(heights))

    def test_caption_image_uses_the_existing_combined_plan(self):
        flow = Probe()
        blocks = [dict(type='paragraph', text='図', rule_style='figure_caption'),
                  dict(type='image', asset='ignored')]
        with patch.object(flow, 'figure_plan', return_value={'total': 123}) as measured:
            result = flow.opening_blocks_keep(blocks, flow.width)
        self.assertEqual(measured.call_count, 1)
        self.assertEqual(result['minimum'], 123)

    def test_facing_and_deliberate_listening_panels_request_a_page_break(self):
        flow = Probe()
        result = flow.first_item_keep(dict(flow.group, items=[{}]), {'layout': 'facing_pages'})
        self.assertTrue(result['break_before'])
        flow.group = dict(kind='listening_choice')
        result = flow.first_item_keep(dict(flow.group, items=[{}]), {})
        self.assertTrue(result['break_before'])

    def test_listening_example_reuses_shared_panel_measurement(self):
        flow = Probe('listening_choice', 'L')
        item = dict(is_example=True, options=['甲'] * 4)
        plan = {'ink_height': 120, 'advance': 145, 'option_lines': []}
        with patch.object(flow, 'listening_panel_metrics', return_value=plan, create=True):
            result = flow.first_item_keep(dict(flow.group, items=[item]), {})
        self.assertIs(result['listening_plan'], plan)
        self.assertEqual(result['minimum'], 145)

    def test_split_frame_matching_survives_shallow_material_copies(self):
        flow = Probe('cloze', 'G')
        children = []
        original = dict(type='box', blocks=children)
        flow._split_group_opening = True
        flow._opening_split_block = original
        flow._opening_split_minimum = 73.59
        flow.pages = [dict(commands=[])]
        flow.page = flow.pages[0]
        with patch.object(flow, 'ensure') as ensured, patch.object(flow, 'frame_segments'), \
             patch.object(flow, 'blocks'), patch.object(flow, 'estimate_block', return_value=500):
            flow.reading_box(dict(original), flow.left, flow.width)
        self.assertEqual(ensured.call_args.args, (73.59,))
        self.assertIsNone(flow._opening_split_block)


if __name__ == '__main__':
    unittest.main()
