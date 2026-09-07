"""Regression tests for the experiment's independently computed PDF diagnostics."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import fitz

from compare_rule_layout import compare


class CompareRuleLayoutTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def pdf(self, name, texts, *, width=300):
        path = self.root / name
        with fitz.open() as document:
            for text in texts:
                page = document.new_page(width=width, height=400)
                page.insert_text((60, 80), text, fontsize=12)
            document.save(path)
        return path

    def test_identical_render_has_no_changed_ink(self):
        source = self.pdf('source.pdf', ['Sample text'])
        result = compare(source, source)
        self.assertEqual(result['changed_pixels'], 0)
        self.assertGreater(result['golden_ink_pixels'], 0)
        self.assertEqual(result['pages'][0]['within_0_1bp'], 10)

    def test_excluded_pages_are_reported_but_not_aggregated(self):
        source = self.pdf('source.pdf', ['One', 'Two', 'Three'])
        changed = self.pdf('changed.pdf', ['First', 'Second', 'Third'])
        result = compare(source, changed, skip_leading=1, excluded_pages=[3])
        self.assertEqual([page['included'] for page in result['pages']], [False, True, False])
        self.assertEqual(result['changed_pixels'], result['pages'][1]['changed_pixels'])
        self.assertGreater(result['pages'][2]['changed_pixels'], 0)

    def test_page_count_difference_is_explicit(self):
        source = self.pdf('source.pdf', ['One', 'Two'])
        changed = self.pdf('changed.pdf', ['One'])
        self.assertFalse(compare(source, changed)['same_page_count'])

    def test_page_size_difference_is_not_silently_zipped(self):
        source = self.pdf('source.pdf', ['One'])
        changed = self.pdf('changed.pdf', ['One'], width=310)
        with self.assertRaisesRegex(ValueError, 'different dimensions'):
            compare(source, changed)

    def test_invalid_raster_settings_are_rejected(self):
        for settings in ({'scale': float('nan')}, {'scale': float('inf')},
                         {'scale': 0}, {'threshold': 256}, {'skip_leading': -1},
                         {'excluded_pages': [0]}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                compare('unused', 'unused', **settings)


if __name__ == '__main__':
    unittest.main()
