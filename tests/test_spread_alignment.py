"""Public reading-spread pagination preserves content and mirrored geometry."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'engine'), str(ROOT / 'tests')]

import build
from rule_layout import RuleLayout
from test_written_rules import Catalog


class SpreadAlignmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.resources = self.root / 'resources'
        assets = self.resources / 'assets'
        assets.mkdir(parents=True)
        # Use the real image primitive and an actual local PDF asset; no TeX
        # process or original font files are needed for scene-level assertions.
        document = fitz.open()
        page = document.new_page(width=100, height=100)
        page.draw_line((0, 0), (100, 100))
        page.draw_line((0, 100), (100, 0))
        document.save(assets / 'interleaf.pdf')
        document.close()
        self.serial = 0

    @staticmethod
    def article(identifier, rows=1, *, label=None, marked=False, boxed=False):
        text = '\n'.join('本文行' + chr(0x4E00 + index) for index in range(rows))
        if marked:
            text = text.replace('本文行一', '{{注1|｜本文《ほんぶん》}}行一', 1)
        block = {'type': 'paragraph', 'text': text}
        stimulus = [{'type': 'box', 'blocks': [block]}] if boxed else [block]
        item = {'id': identifier, 'stimulus': stimulus, 'questions': [
            {'id': identifier + '-q', 'prompt': '答える内容。',
             'options': ['甲', '乙', '丙', '丁']}]}
        if label is not None:
            item['label'] = label
        return item

    @staticmethod
    def group(*items, kind='reading', identifier='R10'):
        return {'id': identifier, 'kind': kind, 'title': '試験見出し',
                'instruction': '文章を読み、答えを選びなさい。', 'items': list(items)}

    def compose(self, group, *, start=1, asset=True, config=None,
                preceding=None, body_bottom=783):
        self.serial += 1
        out = self.root / ('out-' + str(self.serial))
        out.mkdir()
        blueprint = {'page': {'body_bottom': body_bottom}, 'page_number_start': start,
                     'sidebar': False, 'header': False, 'footer': False,
                     'groups': [{'id': group['id'], **(config or {})}]}
        reference = SimpleNamespace(profile=ROOT / 'profiles/n1-original',
                                    resolved={}, ledger=[])
        layout = RuleLayout(Catalog(), blueprint, self.resources, out, reference)
        metadata = {'assets': {'reading_interleaf': 'interleaf.pdf'} if asset else {},
                    'sections': {'R': {'sidebar_label': '読解'},
                                 'G': {'sidebar_label': '文法'},
                                 'V': {'sidebar_label': '文字・語彙'}}}
        groups = {group['id']: group}
        if preceding is not None:
            blueprint['groups'].insert(0, {'id': preceding['id'], 'questions_new_page': False})
            groups[preceding['id']] = preceding
        before = deepcopy(groups)
        build.compose_groups(blueprint=blueprint, groups=groups,
                             component_defaults={}, layout=layout,
                             metadata=metadata, booklet='written')
        self.assertEqual(groups, before, 'Pagination must not mutate authored content')
        return layout

    @staticmethod
    def printed_page(layout, page_ref):
        return next(index + layout.start_page for index, page in enumerate(layout.pages)
                    if id(page) == page_ref)

    def text_pages(self, layout, character):
        return {self.printed_page(layout, glyph['page_ref'])
                for glyph in layout.semantic_glyphs if glyph['char'] == character}

    @staticmethod
    def interleaves(layout):
        return [(index + layout.start_page, command)
                for index, page in enumerate(layout.pages)
                for command in page['commands']
                if command.get('type') == 'image'
                and command.get('asset') == 'assets/interleaf.pdf']

    def assert_clean_state(self, layout, question_ids):
        page_refs = {id(page) for page in layout.pages}
        self.assertTrue(all(glyph['page_ref'] in page_refs for glyph in layout.semantic_glyphs))
        runs = [command['run_id'] for page in layout.pages for command in page['commands']
                if command.get('type') == 'run']
        self.assertEqual(len(runs), len(set(runs)), 'No preview run may be emitted twice')
        self.assertEqual(set(runs), set(layout.resolved), 'No discarded preview runs may remain')
        self.assertEqual([record['id'] for record in layout.item_records], question_ids)
        self.assertEqual([record['label'] for record in layout.item_records],
                         [str(index + 1) for index in range(len(question_ids))])
        self.assertEqual(layout.number, len(question_ids) + 1)
        self.assertEqual(''.join(glyph['char'] for glyph in layout.semantic_glyphs)
                         .count('試験見出し'), 1)

    def test_multi_page_right_start_inserts_one_real_pattern_before_heading(self):
        for kind, rows, question_page in [('reading', 30, False),
                                         ('reading', 1, True), ('cloze', 1, True)]:
            with self.subTest(kind=kind, rows=rows, question_page=question_page):
                group = self.group(self.article('a', rows, boxed=kind == 'cloze'),
                                   kind=kind, identifier='G7' if kind == 'cloze' else 'R10')
                layout = self.compose(group, config={'questions_new_page': question_page})
                leaves = self.interleaves(layout)
                self.assertEqual([page for page, _ in leaves], [1])
                self.assertEqual(len(layout.pages), 3)
                self.assertAlmostEqual(leaves[0][1]['width'], 452.41)
                self.assertAlmostEqual(leaves[0][1]['height'], 708.96)
                self.assertEqual(self.text_pages(layout, '試'), {2})
                self.assertEqual(min(self.text_pages(layout, '本')), 2)
                self.assertFalse(any(glyph['page_ref'] == id(layout.pages[0])
                                     for glyph in layout.semantic_glyphs))
                self.assertEqual(layout.item_records[0]['pages'], [3])
                audit = layout.material_spread_audit
                self.assertEqual(len(audit), 1)
                self.assertEqual({key: audit[0][key] for key in
                                  ('group', 'item', 'start_page', 'end_page', 'pattern_page')},
                                 {'group': group['id'], 'item': 'a', 'start_page': 2,
                                  'end_page': 3, 'pattern_page': 1})
                self.assert_clean_state(layout, ['a-q'])

    def test_multi_page_left_start_uses_printed_parity_without_padding(self):
        layout = self.compose(self.group(self.article('a', 30)), start=2,
                              config={'questions_new_page': False})
        self.assertEqual(self.interleaves(layout), [])
        self.assertEqual(len(layout.pages), 2)
        self.assertEqual(self.text_pages(layout, '試'), {2})
        self.assertEqual(self.text_pages(layout, '本'), {2, 3})
        self.assertEqual(layout.item_records[0]['pages'], [2])  # body index, not printed page
        self.assert_clean_state(layout, ['a-q'])

    def test_single_page_right_start_stays_on_right(self):
        layout = self.compose(self.group(self.article('a')), config={'questions_new_page': False})
        self.assertEqual(self.interleaves(layout), [])
        self.assertEqual(len(layout.pages), 1)
        self.assertEqual(self.text_pages(layout, '試'), {1})
        self.assertEqual(self.text_pages(layout, '本'), {1})
        self.assertEqual(layout.item_records[0]['pages'], [1])
        self.assert_clean_state(layout, ['a-q'])

    def test_second_item_realigns_after_three_page_item_without_repeating_heading(self):
        for start, pattern_pages in [(2, [5]), (1, [1, 5])]:
            with self.subTest(start=start):
                group = self.group(self.article('a', 60, label='(1)'),
                                   self.article('b', 30, label='(2)'))
                layout = self.compose(group, start=start, config={'questions_new_page': False})
                self.assertEqual([page for page, _ in self.interleaves(layout)], pattern_pages)
                audit = layout.material_spread_audit
                self.assertEqual([(row['item'], row['start_page'], row['end_page']) for row in audit],
                                 [('a', 2, 4), ('b', 6, 7)])
                self.assertEqual(self.text_pages(layout, '試'), {2})
                label_pages = {self.printed_page(layout, glyph['page_ref'])
                               for glyph in layout.semantic_glyphs
                               if glyph['char'] == '２' and glyph['size'] == 10.6}
                self.assertEqual(label_pages, {6})
                self.assertEqual({self.printed_page(layout, glyph['page_ref'])
                                  for glyph in layout.semantic_glyphs
                                  if glyph['role'] == 'subitem-parentheses'}, {2, 6})
                self.assertEqual([record['pages'] for record in layout.item_records],
                                 [[4 - start + 1], [7 - start + 1]])
                self.assert_clean_state(layout, ['a-q', 'b-q'])

    def test_same_page_group_preserves_prior_ink_without_covering_it_with_pattern(self):
        preceding = self.group(self.article('prior'), identifier='R8')
        preceding['title'] = '先行見出し'
        group = self.group(self.article('a', 30))
        layout = self.compose(group, preceding=preceding,
                              config={'new_page': False, 'questions_new_page': False})
        self.assertEqual(self.interleaves(layout), [])
        self.assertEqual(self.text_pages(layout, '先'), {1})
        self.assertEqual(self.text_pages(layout, '試'), {2})
        self.assertEqual(layout.item_records[0]['pages'], [1])
        self.assertEqual(layout.item_records[1]['pages'], [3])
        self.assertNotIn('R10', layout.pages[0]['group_ids'])
        self.assert_clean_state(layout, ['prior-q', 'a-q'])

    def test_continuing_item_that_naturally_jumps_to_right_starts_on_next_left(self):
        second = self.article('b', 30)
        second['stimulus'][0]['text'] = second['stimulus'][0]['text'].replace('本文行一', '後続本文', 1)
        group = self.group(self.article('a', 24), second)
        layout = self.compose(group, start=2,
                              config={'questions_new_page': False, 'passages_new_page': False})
        # Inspect the actual first ink, not a planned start-page value: the
        # remaining left-page space cannot hold the next material's first line.
        self.assertEqual(self.text_pages(layout, '後'), {4})
        self.assertEqual([page for page, _ in self.interleaves(layout)], [3])
        self.assertEqual(layout.item_records[0]['pages'], [1])
        self.assertEqual(layout.item_records[1]['pages'], [4])
        self.assertEqual(self.text_pages(layout, '試'), {2})
        self.assert_clean_state(layout, ['a-q', 'b-q'])

    def test_pattern_fits_a_valid_shorter_body_without_touching_prior_or_next_page(self):
        layout = self.compose(self.group(self.article('a', 30)), body_bottom=400,
                              config={'questions_new_page': False})
        leaves = self.interleaves(layout)
        self.assertEqual([page for page, _ in leaves], [1])
        image = leaves[0][1]
        image_top = layout.H - image['y'] - image['height']
        self.assertGreaterEqual(image_top, layout.top - 1e-4)
        self.assertLessEqual(image_top + image['height'] + 4, layout.bottom + 1e-4)
        self.assertGreater(image['height'], 0)
        self.assertEqual(self.text_pages(layout, '試'), {2})
        self.assert_clean_state(layout, ['a-q'])

    def test_inserted_spread_matches_direct_left_start_including_ruby_and_notes(self):
        group = self.group(self.article('a', 30, marked=True))
        shifted = self.compose(group, config={'questions_new_page': False, 'body_start_adjust': 8})
        direct = self.compose(group, start=2,
                              config={'questions_new_page': False, 'body_start_adjust': 8})
        self.assertEqual([page for page, _ in self.interleaves(shifted)], [1])
        self.assertEqual(self.interleaves(direct), [])
        def geometry(layout):
            return [(self.printed_page(layout, glyph['page_ref']), glyph['char'], glyph['size'],
                     glyph['x'], glyph['y'], glyph['role']) for glyph in layout.semantic_glyphs]
        self.assertEqual(geometry(shifted), geometry(direct))
        first_body = next(g for g in shifted.semantic_glyphs if g['char'] == '本')
        self.assertAlmostEqual(first_body['x'], 63.63 + 11.31017, places=3)
        self.assert_clean_state(shifted, ['a-q'])
        self.assert_clean_state(direct, ['a-q'])

    def test_ordinary_multi_page_choice_group_keeps_right_start_without_pattern(self):
        group = self.group(*[{'id': f'q{index}', 'prompt': '普通の選択問題です。',
                              'options': ['日本', '学校', '電車', '会社']} for index in range(18)],
                           kind='choice', identifier='V1')
        layout = self.compose(group)
        self.assertGreater(len(layout.pages), 1)
        self.assertEqual(self.interleaves(layout), [])
        self.assertEqual(self.text_pages(layout, '試'), {1})
        self.assertEqual(layout.item_records[0]['pages'], [1])
        self.assert_clean_state(layout, [f'q{index}' for index in range(18)])

    def test_missing_pattern_asset_preserves_existing_multi_page_layout(self):
        layout = self.compose(self.group(self.article('a', 30)), asset=False,
                              config={'questions_new_page': False})
        self.assertEqual(len(layout.pages), 2)
        self.assertEqual(self.text_pages(layout, '試'), {1})
        self.assertEqual(self.interleaves(layout), [])
        self.assert_clean_state(layout, ['a-q'])

    def test_existing_facing_layout_does_not_get_a_second_pattern(self):
        layout = self.compose(self.group(self.article('a')), config={'layout': 'facing_pages'})
        self.assertEqual([page for page, _ in self.interleaves(layout)], [1])
        self.assertEqual(len(layout.pages), 3)
        self.assertEqual(layout.item_records[0]['pages'], [2])
        self.assertEqual(self.text_pages(layout, '本'), {3})
        self.assert_clean_state(layout, ['a-q'])


if __name__ == '__main__':
    unittest.main()
