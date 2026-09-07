"""Rules reject unsupported editorial roles before any partial page is drawn."""
from pathlib import Path
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
from rule_validation import validate_rule_content, validate_rule_dimensions
from rule_layout import RuleLayout
from test_written_rules import Catalog, NoMeasuredBodies


class RuleValidationTests(unittest.TestCase):
    def group(self, blocks, section='R'):
        return {'id': section + '-new', 'items': [{'stimulus': blocks}]}

    def test_existing_corpora_satisfy_explicit_semantic_roles(self):
        for path in (ROOT / 'content').glob('paper-*/*.yaml'):
            for group in yaml.safe_load(path.read_text()).get('groups', []):
                with self.subTest(file=path, group=group['id']):
                    validate_rule_content(group)

    def test_notice_is_not_silently_approximated_in_vocabulary(self):
        block = {'type': 'box', 'rule_style': 'notice', 'blocks': []}
        with self.assertRaisesRegex(ValueError, 'top-level reading box'):
            validate_rule_content(self.group([block], 'V'))

    def test_contact_roles_require_notice_context(self):
        contact = {'type': 'paragraph', 'text': '住所', 'rule_style': 'contact'}
        with self.assertRaisesRegex(ValueError, 'directly inside a notice'):
            validate_rule_content(self.group([contact]))
        validate_rule_content(self.group([{'type': 'box', 'rule_style': 'notice',
                                          'blocks': [contact]}]))

    def test_unknown_or_misplaced_roles_fail(self):
        for block in ({'type': 'paragraph', 'rule_style': 'quotaton'},
                      {'type': 'table', 'rule_style': 'quotation'},
                      {'type': 'paragraph', 'rule_style': 'guide_title'}):
            with self.subTest(block=block), self.assertRaises(ValueError):
                validate_rule_content(self.group([block]))

    def test_caption_is_a_page_level_text_image_pair(self):
        pair = [{'type': 'paragraph', 'text': '図', 'rule_style': 'figure_caption'},
                {'type': 'image', 'asset': 'test.pdf'}]
        validate_rule_content(self.group(pair))
        for blocks in ([pair[0]], [dict(pair[0], type='table'), pair[1]],
                       [{'type': 'box', 'blocks': pair}]):
            with self.subTest(blocks=blocks), self.assertRaisesRegex(ValueError, 'figure_caption'):
                validate_rule_content(self.group(blocks))

    def test_vertical_and_guide_cannot_silently_drop_images(self):
        image = {'type': 'image', 'asset': 'test.pdf'}
        for block in ({'type': 'box', 'blocks': [{'type': 'vertical', 'text': '本文'}, image]},
                      {'type': 'box', 'rule_style': 'guide', 'blocks': [image]}):
            with self.subTest(block=block), self.assertRaises(ValueError):
                validate_rule_content(self.group([block]))

    def test_dimensions_reject_nonfinite_values_but_allow_signed_tracking(self):
        for key in ('font_size', 'line_height', 'body_width', 'reference_font_size',
                    'compound_intro_first_line_tracking', 'indent'):
            for value in (True, float('nan'), float('inf'), float('-inf')):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate_rule_dimensions({key: value})
        validate_rule_dimensions({'compound_intro_first_line_tracking': -.27, 'indent': 0})
        with self.assertRaises(ValueError):
            validate_rule_dimensions({'font_size': 0})

    def test_table_weights_must_be_finite_positive_numbers(self):
        with self.assertRaises(ValueError):
            validate_rule_content(self.group([{'type': 'table', 'rows': [['甲', '乙']],
                                               'column_widths': [1, float('nan')]}]))

    def test_invalid_group_fails_before_drawing_a_partial_page(self):
        with tempfile.TemporaryDirectory() as directory:
            layout = RuleLayout(Catalog(), {'page': {'body_bottom': 783}},
                                ROOT / 'resources', directory, NoMeasuredBodies())
            group = self.group([{'type': 'paragraph', 'rule_style': 'quotaton'}])
            group.update(kind='reading', title='問題', instruction='文章を読む。')
            with self.assertRaisesRegex(ValueError, 'unknown rule_style'):
                layout.render_group(group, {'sidebar': False})
            self.assertEqual(layout.pages, [])
            self.assertEqual(layout.resolved, {})

    def test_invalid_page_dimensions_fail_at_rules_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'body_width'):
                RuleLayout(Catalog(), {'page': {'body_width': float('nan')}},
                           ROOT / 'resources', directory, NoMeasuredBodies())


if __name__ == '__main__':
    unittest.main()
