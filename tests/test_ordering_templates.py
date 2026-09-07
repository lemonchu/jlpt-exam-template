"""Independent fixed furniture: local content, relative placement, safe fallback."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import sys
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from ordering_templates import load_ordering_template, local_content
from rule_layout import RuleLayout


class TemplateLayout(RuleLayout):
    """A body-free provider and scene sink; no legacy method can be consulted."""
    def __init__(self, config=None, *, left=63.63, top=62.4928):
        self.reference = SimpleNamespace(profile=ROOT / 'profiles/n1-original',
                                         resolved={}, ledger=[])
        self.resolved = self.reference.resolved
        self.gc = config or {}
        self.group = {'id': 'G99', 'kind': 'word_order'}
        self.fs = self.gc.get('font_size', 11.3)
        self.leading = self.gc.get('line_height', 24.05996)
        self.width = self.gc.get('body_width', 452.41)
        self.left, self.top, self.y = left, top, top
        self.H, self.bottom = 842, 783
        self.page = {'commands': []}
        self.pages = [self.page]
        self.component_audit = [{}]
        self._pending_heading = None
        self.section = 'G'

    @property
    def usable(self):
        return self.bottom - self.top

    def configured_columns(self, item):
        value = self.gc.get('options_columns_by_item', {}).get(
            item.get('id'), self.gc.get('options_columns', 'auto'))
        return value if value == 'auto' else int(value)

    def new_page(self):
        self.page = {'commands': []}
        self.pages.append(self.page)
        self.left = 78.96 if self.left == 63.63 else 63.63
        self.y = self.top


class OrderingTemplateTests(unittest.TestCase):
    def setUp(self):
        self.asset = load_ordering_template(ROOT / 'profiles/n1-original')
        self.example = deepcopy(self.asset['example']['content'])
        self.example['id'] = 'custom-worked-example'
        self.group = dict(self.asset['heading']['content'], id='G99', kind='word_order',
                          items=[self.example])

    def render(self, layout):
        layout.group = self.group
        layout.group_heading(self.group, layout.gc)
        self.assertTrue(layout.component_audit[0]['ordering_heading_template'])
        self.assertTrue(layout.template_example(self.example))
        return [command for command in layout.page['commands'] if command['type'] == 'run']

    def test_all_three_authored_examples_match_without_surrounding_questions(self):
        for paper in ('paper-a', 'paper-b', 'paper-2014-12'):
            with self.subTest(paper=paper):
                content = yaml.safe_load((ROOT / 'content' / paper / 'G.yaml').read_text())
                group = next(group for group in content['groups'] if group['kind'] == 'word_order')
                example = next(item for item in group['items'] if item.get('is_example'))
                self.assertEqual(local_content(example), local_content(self.example))

    def test_new_ids_and_arbitrary_following_items_do_not_disable_template(self):
        self.group['items'] += [{'id': 'new-question', 'prompt': 'Entirely new prose.'}] * 7
        layout = TemplateLayout({'items': ['custom-worked-example', 'new-question'],
                                 'options_columns_by_item': {'new-question': 1}})
        runs = self.render(layout)
        self.assertEqual(len(runs), 33)
        self.assertAlmostEqual(layout.y, 484.2628)
        self.assertEqual(len(layout.reference.ledger), sum(run['slot_count'] for run in runs))
        self.assertTrue(layout.component_audit[0]['ordering_example_template'])

    def test_same_length_new_example_text_uses_rule_fallback(self):
        self.example['options'][0] = 'ラジオ'
        layout = TemplateLayout()
        self.assertFalse(layout.template_example(self.example))
        self.assertFalse(layout.resolved)
        self.assertFalse(layout.page['commands'])

    def test_changed_nested_example_style_uses_rule_fallback(self):
        self.example['stimulus'][-1]['width'] = 160
        self.assertFalse(TemplateLayout().template_example(self.example))

    def test_unsupported_heading_styles_disable_fixed_furniture(self):
        for config in ({'heading_layout': 'inline'}, {'heading_size': 30},
                       {'instruction_font_size': 20}, {'instruction_line_height': 30},
                       {'instruction_width': 400}, {'font_size': 12},
                       {'line_height': 28}, {'body_width': 420}):
            with self.subTest(config=config):
                layout = TemplateLayout(config)
                self.assertIsNone(layout.ordering_heading_plan(self.group, config))
                self.assertIsNone(layout.ordering_example_plan(self.example))
                self.assertFalse(layout.template_example(self.example))

    def test_unsupported_example_styles_fall_back_without_affecting_heading(self):
        for config in ({'question_gap': 24}, {'body_start_adjust': 3},
                       {'options_columns': 2},
                       {'options_columns_by_item': {'custom-worked-example': 1}},
                       {'table_column_widths': {6: [1]*6}}, {'table_cell_padding_x': 10},
                       {'table_font_size': 14}, {'table_column_alignments': {6: ['center']*6}},
                       {'choice_prompt_max_negative_tracking': 0},
                       {'choice_option_max_negative_tracking': 0},
                       {'word_order_blank_max_negative_tracking': 0}):
            with self.subTest(config=config):
                layout = TemplateLayout(config)
                self.assertIsNotNone(layout.ordering_heading_plan(self.group, config))
                self.assertIsNone(layout.ordering_example_plan(self.example))
                layout.group_heading(self.group, config)
                self.assertTrue(layout.component_audit[0]['ordering_heading_template'])
                self.assertFalse(layout.template_example(self.example))

    def test_origin_moves_every_glyph_and_flow_by_the_same_offset(self):
        original, moved = TemplateLayout(), TemplateLayout(left=80, top=90)
        before, after = self.render(original), self.render(moved)
        for a, b in zip(before, after):
            self.assertAlmostEqual(b['x'] - a['x'], 80 - 63.63)
            self.assertAlmostEqual(b['y'] - a['y'], 62.4928 - 90)
            self.assertEqual(original.resolved[a['run_id']], moved.resolved[b['run_id']])
        self.assertAlmostEqual(moved.y - original.y, 90 - 62.4928)

    def test_plans_are_side_effect_free_even_when_current_page_is_full(self):
        layout = TemplateLayout()
        layout.y = 780
        before = deepcopy(layout.__dict__)
        heading = layout.ordering_heading_plan(self.group, layout.gc)
        example = layout.ordering_example_plan(self.example)
        self.assertEqual(layout.__dict__, before)
        self.assertAlmostEqual(heading['advance'], 63.1081)
        self.assertEqual(heading['overhang'], 0)
        self.assertAlmostEqual(example['advance'], 358.6619)
        self.assertAlmostEqual(example['overhang'], 10.9849)
        self.assertAlmostEqual(example['minimum_height'], 369.6468)

    def test_heading_uses_current_cursor_without_resetting_to_page_top(self):
        original, continued = TemplateLayout(), TemplateLayout()
        continued.y = 300
        before, after = self.render(original), self.render(continued)
        offset = 300 - continued.top
        self.assertEqual(len(continued.pages), 1)
        for first, second in zip(before, after):
            self.assertAlmostEqual(first['y'] - second['y'], offset)
        self.assertAlmostEqual(continued.y - original.y, offset)

    def test_heading_and_example_draw_exactly_the_planned_advance(self):
        layout = TemplateLayout()
        layout.y = 250
        heading = layout.ordering_heading_plan(self.group, layout.gc)
        example = layout.ordering_example_plan(self.example)
        initial = layout.y
        self.render(layout)
        self.assertAlmostEqual(layout.y - initial, heading['advance'] + example['advance'])
        self.assertEqual(len(layout.pages), 1)

    def test_heading_plan_honors_explicit_config_argument(self):
        layout = TemplateLayout()
        self.assertIsNone(layout.ordering_heading_plan(self.group, {'heading_size': 30}))
        self.assertIsNotNone(layout.ordering_heading_plan(self.group, {}))

    def test_heading_only_draw_moves_to_fresh_page_when_advance_will_not_fit(self):
        layout = TemplateLayout()
        layout.y = 770
        layout.group_heading(self.group, {})
        self.assertEqual(len(layout.pages), 2)
        self.assertAlmostEqual(layout.y, layout.top + self.asset['heading']['advance'])

    def test_page_break_recalculates_mirrored_left_and_reserves_separator(self):
        layout = TemplateLayout()
        layout.y = 700
        self.assertTrue(layout.template_example(self.example))
        self.assertEqual(len(layout.pages), 2)
        runs = [command for command in layout.page['commands'] if command['type'] == 'run']
        self.assertAlmostEqual(runs[0]['x'], 78.96)
        top = layout.H - runs[0]['y'] - self.asset['example']['runs'][0]['y']
        min_line = min(line[index] for line in self.asset['example']['lines'] for index in (1, 3))
        self.assertGreaterEqual(top + min_line - self.asset['stroke']/2, layout.top - 1e-9)

    def test_small_page_falls_back_instead_of_replaying_an_oversize_asset(self):
        layout = TemplateLayout()
        layout.bottom = 300
        self.assertIsNone(layout.ordering_example_plan(self.example))
        self.assertFalse(layout.template_example(self.example))

    def test_asset_contains_no_body_ids_or_clipped_page_vectors(self):
        self.assertNotIn('G-p03', json.dumps(self.asset))
        for part in ('heading', 'example'):
            self.assertNotIn('pdf', self.asset[part])
            self.assertTrue(all(not field['pointer'].startswith('/groups/')
                                for field in self.asset[part]['fields'].values()))

    def test_unknown_asset_schema_is_rejected(self):
        load_ordering_template.cache_clear()
        try:
            with patch.object(Path, 'read_text', return_value='{"schema_version": 2}'):
                with self.assertRaisesRegex(ValueError, 'schema_version'):
                    load_ordering_template(Path('/unused-ordering-profile'))
        finally:
            load_ordering_template.cache_clear()


if __name__ == '__main__':
    unittest.main()
