"""Independent source-row diagnostics preserve text and reject stale lengths."""
import json
from pathlib import Path
import unittest

from check_rule_a_rows import source_rows, EXPECTED_COUNTS
from build import load_content

ROOT = Path(__file__).resolve().parents[1]


class SourceRowBaselineTests(unittest.TestCase):
    def test_fixture_covers_all_original_choice_fields(self):
        baseline = json.loads((ROOT/'tests/fixtures/a-choice-rows.json').read_text(encoding='utf-8'))
        groups, _ = load_content(ROOT/'content/paper-a')
        counts = dict.fromkeys(EXPECTED_COUNTS, 0)
        for group, fields in baseline['groups'].items():
            self.assertIn(group, groups)
            rows = source_rows(fields, groups[group])
            for field in rows:
                counts['prompts' if field.endswith('/prompt') else 'options'] += 1
        self.assertEqual(counts, EXPECTED_COUNTS)

    def test_rows_use_current_text_and_normalize_optical_whitespace(self):
        fields = {'/prompt': [2, 3]}
        self.assertEqual(source_rows(fields, {'prompt': '__甲乙__　:丙丁'}),
                         {'/prompt': ['甲乙', '：丙丁']})
        self.assertEqual(source_rows(fields, {'prompt': '日本語本文'}),
                         {'/prompt': ['日本', '語本文']})

    def test_changed_field_length_fails_clearly(self):
        with self.assertRaisesRegex(ValueError, 'baseline no longer fits /prompt'):
            source_rows({'/prompt': [2]}, {'prompt': '本文追加'})

    def test_invalid_lengths_are_not_silently_accepted(self):
        for lengths in ([], [0], [-1, 3], [True, 1], [1.0, 1]):
            with self.subTest(lengths=lengths), self.assertRaisesRegex(ValueError, 'Invalid source row lengths'):
                source_rows({'/prompt': lengths}, {'prompt': '本文'})


if __name__ == '__main__':
    unittest.main()
