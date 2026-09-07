"""Rules and shared composition cannot reactivate legacy body reuse."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from component_layout import ComponentLayout
from rule_layout import RuleLayout
from test_written_rules import Catalog, NoMeasuredBodies


class RuleModeTests(unittest.TestCase):
    def render(self, layout_type, group, flags):
        reference = NoMeasuredBodies()
        reference.profile = ROOT / 'profiles/n1-original'
        reference.ledger = []
        with tempfile.TemporaryDirectory() as directory:
            layout = layout_type(Catalog(), {'sidebar': False}, ROOT / 'resources', directory, reference)
            config = dict(flags, sidebar=False)
            before = deepcopy(config)
            layout.render_group(group, config)
            self.assertEqual(config, before)
            return layout.pages, layout.resolved, layout.item_records, layout.component_audit

    def test_all_rule_kinds_ignore_legacy_flags_without_touching_calibration(self):
        question = {'id': 'q', 'prompt': 'これは問題です。',
                    'options': ['日本', '学校', '電車', '会社']}
        for kind, section in (('choice', 'V'), ('word_order', 'G'), ('cloze', 'G'),
                              ('reading', 'R'), ('listening_choice', 'L'),
                              ('listening_compound', 'L'), ('listening_memo', 'L')):
            item = (deepcopy(question) if kind in ('choice', 'word_order', 'listening_choice')
                    else {'id': 'material', 'stimulus': [{'type': 'paragraph', 'text': '新しい文章です。'}]})
            group = {'id': section + '1', 'kind': kind, 'title': '問題１',
                     'instruction': '正しいものを選びなさい。', 'items': [item]}
            expected = self.render(RuleLayout, group, {})
            for enabled in (True, False):
                with self.subTest(kind=kind, enabled=enabled):
                    flags = dict(use_measured=enabled, _use_measured_heading=enabled,
                                 _use_measured_example=enabled)
                    self.assertEqual(self.render(RuleLayout, group, flags), expected)

    def test_common_engine_itself_has_no_body_reuse_path(self):
        group = {'id': 'V1', 'kind': 'choice', 'title': '問題１', 'items': [
            {'id': 'q', 'prompt': 'これは問題です。', 'options': ['日本', '学校', '電車', '会社']}]}
        expected = self.render(ComponentLayout, group, {})
        self.assertEqual(self.render(ComponentLayout, group, dict(
            use_measured=True, _use_measured_heading=True, _use_measured_example=True)), expected)

    def test_facing_material_ignores_old_page_reuse_switch(self):
        group = {'id': 'R13', 'kind': 'reading', 'title': '問題１３', 'items': [
            {'id': 'spread', 'stimulus': [{'type': 'paragraph', 'text': '参考資料です。'}],
             'questions': [{'id': 'q', 'prompt': '正しいものを選びなさい。',
                            'options': ['日本', '学校', '電車', '会社']}]}]}
        for layout_type in (ComponentLayout, RuleLayout):
            with self.subTest(layout=layout_type.__name__):
                expected = self.render(layout_type, group, {'layout': 'facing_pages'})
                self.assertEqual(len(expected[0]), 2)
                self.assertEqual(self.render(layout_type, group, dict(
                    layout='facing_pages', use_measured=True, _use_measured_heading=True)), expected)


if __name__ == '__main__':
    unittest.main()
