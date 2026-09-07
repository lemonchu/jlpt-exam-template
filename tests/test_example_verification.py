"""Example snapshots follow the default rules; legacy comparisons are explicit."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

import verify_examples


class ExampleVerificationTests(unittest.TestCase):
    def test_default_and_explicit_directories(self):
        for args, expected, actual in (
            ([], verify_examples.ROOT / 'examples', verify_examples.ROOT / 'output/rules'),
            (['--expected-dir', 'baseline/precise', '--actual-dir', 'custom/precise'],
             Path('baseline/precise'), Path('custom/precise')),
        ):
            with self.subTest(args=args), patch.object(Path, 'is_file', return_value=True), \
                    patch.object(verify_examples, 'page_hashes', return_value=['page']) as hashes, \
                    redirect_stdout(StringIO()):
                self.assertEqual(verify_examples.main(args), 0)
                self.assertEqual([call.args[0] for call in hashes.call_args_list], [
                    directory / f'N1-{paper}.pdf'
                    for paper in verify_examples.PAPERS for directory in (actual, expected)])

    def test_pixel_changes_and_page_count_changes_fail(self):
        for actual in (['changed', 'second'], ['first'], ['first', 'second', 'extra']):
            with self.subTest(actual=actual), patch.object(Path, 'is_file', return_value=True), \
                    patch.object(verify_examples, 'page_hashes', side_effect=[actual, ['first', 'second']]), \
                    redirect_stderr(StringIO()) as stderr:
                self.assertEqual(verify_examples.main(['paper-a-written']), 1)
                self.assertIn('changed pages', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
