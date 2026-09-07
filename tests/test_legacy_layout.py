"""Legacy-only policy and fallback boundaries; never required by RuleLayout."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'engine'))

from build import prepare_group
from component_layout import ComponentLayout
from legacy_layout import LegacyLayout, LegacyPolicy, canonicalize_config
from semantic_bindings import CalibrationMismatch
from test_written_rules import Catalog


class LegacyPolicyTests(unittest.TestCase):
    def setUp(self):
        self.blueprint = {'page': {'width': 595, 'height': 842}, 'sidebar': {'width': 20},
                          'group_defaults': {'heading_size': 12, 'instruction_width': 300},
                          'groups': ['V1']}
        self.components = {'components': {'choice': {'option_gap': 10, 'columns': {6: [1, 2]}}}}
        self.reference = SimpleNamespace(contracts=canonicalize_config({
            'blueprints': {'written': self.blueprint}, 'components': {'written': self.components}}),
            pages={('R', 18): {'commands': [{'type': 'ink', 'rgb': [0, 0, 0]}]}},
            resolved={}, meta=Mock(return_value={'r1': {'text': 'reference'}}))
        self.source = {'id': 'V1', 'kind': 'choice', 'items': [{'id': 'q1'}, {'id': 'q2'}]}

    def policy(self, *, recompose=False, **blueprint):
        return LegacyPolicy(self.reference, {**self.blueprint, **blueprint}, self.components,
                            'written', recompose=recompose)

    def config(self, policy, **entry):
        entry = {'id': 'V1', **entry}
        group, config = prepare_group(self.source, entry, blueprint=policy.blueprint,
                                     component_defaults=self.components['components'])
        policy.configure_group(group, entry, config)
        return config

    def test_pristine_config_normalizes_integer_keys_and_enables_reuse(self):
        policy = self.policy()
        self.assertTrue(policy.pristine)
        config = self.config(policy)
        for key in ('use_measured', '_use_measured_heading', '_use_measured_example'):
            self.assertTrue(config[key])
        self.assertFalse(config['_refresh_furniture'])

    def test_selected_items_keep_only_the_compatible_heading(self):
        config = self.config(self.policy(header='Custom'), items=['q2'], title='Custom')
        self.assertFalse(config['use_measured'])
        self.assertTrue(config['_use_measured_heading'])
        self.assertFalse(config['_use_measured_example'])
        self.assertTrue(config['_refresh_furniture'])

    def test_recompose_and_custom_heading_styles_disable_all_reuse(self):
        for policy, entry in ((self.policy(recompose=True), {}),
                              (self.policy(), {'heading_size': 30}),
                              (self.policy(), {'instruction_font_size': 20})):
            with self.subTest(entry=entry, recompose=policy.recompose):
                config = self.config(policy, **entry)
                for key in ('use_measured', '_use_measured_heading', '_use_measured_example'):
                    self.assertFalse(config[key])

    def test_default_header_injection_does_not_change_pristine_policy(self):
        policy = self.policy()
        policy.blueprint.setdefault('header', 'Default subject')
        self.assertTrue(policy.pristine)
        self.assertFalse(self.config(policy)['_refresh_furniture'])

    def test_reference_interleaf_requires_original_page_and_pristine_precise_mode(self):
        for policy, start, expected in ((self.policy(), 29, True),
                                         (self.policy(), 27, False),
                                         (self.policy(recompose=True), 29, False),
                                         (self.policy(header='Custom'), 29, False)):
            with self.subTest(start=start, pristine=policy.pristine, recompose=policy.recompose):
                layout = SimpleNamespace(pages=[], start_page=start)
                before = deepcopy(self.reference.pages)
                self.assertEqual(policy.insert_interleaf(layout, self.source), expected)
                self.assertEqual(len(layout.pages), int(expected))
                self.assertEqual(self.reference.pages, before)
                if expected:
                    self.assertTrue(layout.page['measured'])
                    self.assertEqual(layout.page['group_ids'], ['V1'])
                    self.assertIn('r1', self.reference.resolved)


class LegacyAdapterTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.reference = SimpleNamespace(resolved={}, components={})
        self.layout = LegacyLayout(Catalog(), {'sidebar': False}, ROOT / 'resources',
                                   directory.name, self.reference)
        self.group = {'id': 'V1', 'kind': 'choice', 'items': [
            {'id': 'q', 'options': ['日本', '学校', '電車', '会社']}]}

    def test_measured_group_replaces_placeholder_and_advances_number_once(self):
        pages = [{'commands': [], 'measured_body': True} for _ in range(2)]
        self.reference.take_group = Mock(return_value=pages)
        side = {'text': '文字'}
        with patch.object(ComponentLayout, 'compose_group') as fallback:
            self.layout.render_group(self.group, {'sidebar': side})
        fallback.assert_not_called()
        self.assertEqual(len(self.layout.pages), 2)
        self.assertEqual(self.layout.number, 2)
        self.assertEqual(self.layout.y, self.layout.bottom)
        self.assertEqual(self.layout.component_audit[0]['body_pages'], [1, 2])
        self.assertEqual(pages[0]['bands'], [side])
        self.assertIsNot(pages[0]['bands'][0], side)

    def test_calibration_mismatch_falls_back_but_unexpected_errors_propagate(self):
        for error in (CalibrationMismatch('changed content'), RuntimeError('broken source')):
            with self.subTest(error=type(error).__name__), patch.object(ComponentLayout, 'compose_group') as fallback:
                self.reference.take_group = Mock(side_effect=error)
                if isinstance(error, CalibrationMismatch):
                    self.layout.render_group(self.group, {})
                    fallback.assert_called_once_with(self.group, {}, reason='changed content')
                else:
                    with self.assertRaisesRegex(RuntimeError, 'broken source'):
                        self.layout.render_group(self.group, {})
                    fallback.assert_not_called()

    def test_legacy_flow_never_calls_measured_resolver(self):
        self.reference.take_group = Mock(side_effect=AssertionError('unexpected reuse'))
        self.layout.render_group(self.group, {'use_measured': False, '_use_measured_heading': False})
        self.reference.take_group.assert_not_called()
        self.assertEqual(self.layout.component_audit[0]['placement'], 'composed')
        self.assertEqual(self.layout.item_records[0]['id'], 'q')

    def test_listening_intro_skips_exactly_one_item_and_does_not_redraw_heading(self):
        self.group.update(id='L1', kind='listening_choice')
        example = {'id': 'example', 'is_example': True, 'options': ['一'] * 4}
        self.group['items'].insert(0, example)
        self.reference.components = {'L1': {'pages': [1]}}
        self.reference.take_group = Mock(side_effect=CalibrationMismatch('changed body'))
        self.reference.take_page = Mock(return_value={'commands': [], 'measured_body': True})
        with patch.object(self.layout, 'group_heading') as heading, \
                patch.object(self.layout, 'render_item') as item:
            self.layout.render_group(self.group, {})
        heading.assert_not_called()
        item.assert_called_once_with(self.group['items'][1], 1)
        self.assertEqual([record['id'] for record in self.layout.item_records], ['example'])
        self.assertTrue(self.layout.component_audit[0]['shared_intro_page'])

    def test_facing_reuse_and_mismatch_preserve_the_left_page(self):
        self.group.update(id='R13', kind='reading')
        self.reference.components = {'R13': {'pages': [17, 19]}}
        self.layout.group = self.group
        self.layout.section = 'R'
        self.layout.gc = {'use_measured': True, 'sidebar': {'text': '読解'}}
        self.layout.component_audit.append({})
        self.layout.new_page()
        self.layout.glyph_text('問題', 11.3, self.layout.left, self.layout.top + 11.3)
        left = deepcopy(self.layout.page)
        self.layout.new_page()
        material = [{'type': 'paragraph', 'text': '参考資料です。'}]
        page = {'commands': [], 'measured_body': True}
        self.reference.take_page = Mock(return_value=page)
        with patch.object(ComponentLayout, 'reference_material') as fallback:
            self.layout.reference_material(material)
            fallback.assert_not_called()
            self.assertIs(self.layout.page, page)
            self.assertEqual(page['bands'], [{'text': '読解'}])
            self.assertTrue(self.layout.component_audit[-1]['shared_reference_page'])
            self.reference.take_page.side_effect = CalibrationMismatch('changed material')
            self.layout.reference_material(material)
            fallback.assert_called_once_with(material)
        self.assertEqual(self.layout.pages[0], left)
        self.assertEqual(len(self.layout.pages), 2)


if __name__ == '__main__':
    unittest.main()
