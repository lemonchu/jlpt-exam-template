"""Default rules never reactivate legacy body-calibration methods."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from component_layout import ComponentLayout
from rule_layout import RuleLayout


class RuleModeTests(unittest.TestCase):
    def config_for(self, kind, config):
        layout = object.__new__(RuleLayout)
        layout.component_audit = []
        captured = []

        def capture(instance, group, actual):
            captured.append(actual)
            instance.component_audit.append({})

        with patch.object(ComponentLayout, 'render_group', capture):
            layout.render_group({'id': 'G6', 'kind': kind, 'items': []}, config)
        return captured[0]

    def test_all_group_kinds_force_legacy_reuse_off_even_when_explicitly_requested(self):
        flags = dict(use_measured=True, _use_measured_heading=True, _use_measured_example=True)
        for kind in ('choice', 'word_order', 'cloze', 'reading', 'listening_choice',
                     'listening_compound', 'listening_memo'):
            for supplied in ({}, flags, dict(flags, heading_size=30, instruction_font_size=20)):
                with self.subTest(kind=kind, config=supplied):
                    config = self.config_for(kind, supplied)
                    for flag in flags:
                        self.assertFalse(config[flag])


if __name__ == '__main__':
    unittest.main()
