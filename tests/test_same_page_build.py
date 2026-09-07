"""Public blueprint orchestration uses current-page parity for continuations."""
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'engine'))

import build
from rule_layout import RuleLayout
from test_written_rules import Catalog


class SamePageBuildTests(unittest.TestCase):
    def compose(self, second):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        reference = SimpleNamespace(profile=ROOT / 'profiles/n1-original', resolved={}, ledger=[])
        blueprint = {'page': {'body_bottom': 783}, 'sidebar': False,
                     'groups': [{'id': 'V1'}, {'id': 'V2', **second}]}
        groups = {
            identifier: {'id': identifier, 'kind': 'choice', 'title': '問題１',
                         'instruction': '正しいものを選びなさい。',
                         'items': [{'id': identifier + '-question',
                                    'prompt': 'これは問題です。',
                                    'options': ['日本', '学校', '電車', '会社']}]}
            for identifier in ('V1', 'V2')
        }
        layout = RuleLayout(Catalog(), blueprint, ROOT / 'resources', directory.name, reference)
        build.compose_groups(
            blueprint=blueprint, groups=groups, component_defaults={}, layout=layout,
            metadata=build.load(ROOT / 'content/common/metadata.yaml'),
            booklet='written')
        return layout

    def test_continuation_on_current_right_page_does_not_insert_blank_pages(self):
        layout = self.compose({'new_page': False, 'start_on': 'right'})
        self.assertEqual(len(layout.pages), 1)
        self.assertEqual(layout.pages[0]['group_ids'], ['V1', 'V2'])
        self.assertEqual([record['pages'] for record in layout.item_records], [[1], [1]])

    def test_continuation_requiring_left_page_moves_once(self):
        layout = self.compose({'new_page': False, 'start_on': 'left'})
        self.assertEqual(len(layout.pages), 2)
        self.assertEqual([record['pages'] for record in layout.item_records], [[1], [2]])
        self.assertEqual(layout.pages[0]['group_ids'], ['V1'])
        self.assertEqual(layout.pages[1]['group_ids'], ['V2'])

    def test_new_page_defaults_keep_existing_next_page_parity_contract(self):
        for settings, expected in (({}, 2), ({'start_on': 'left'}, 2),
                                   ({'start_on': 'right'}, 3),
                                   ({'new_page': True, 'start_on': 'right'}, 3)):
            with self.subTest(settings=settings):
                layout = self.compose(settings)
                self.assertEqual(len(layout.pages), expected)
                self.assertEqual(layout.item_records[-1]['pages'], [expected])
                self.assertEqual(layout.pages[0]['group_ids'], ['V1'])


if __name__ == '__main__':
    unittest.main()
