"""Unit tests for metadata cover-layout helpers."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from metadata_components import _clip_decorations, _parenthetical_characters


class MetadataComponentHelperTests(unittest.TestCase):
    def test_parenthetical_state_includes_delimiters_and_nesting(self):
        states = list(_parenthetical_characters('A（B(C)D）E'))
        self.assertEqual(states, [
            ('A', False), ('（', True), ('B', True), ('(', True), ('C', True),
            (')', True), ('D', True), ('）', True), ('E', False),
        ])

    def test_decoration_clipping_copies_only_when_it_changes_a_vector(self):
        command = {'type': 'vector', 'pdf': '0 0 m 1 1 l S'}
        self.assertIs(_clip_decorations(command, [], None), command)

        clipped = _clip_decorations(
            command, [(1.0, 2.0, 3.0, 4.0)], {'width': 100, 'height': 200})
        self.assertIsNot(clipped, command)
        self.assertEqual(command['pdf'], '0 0 m 1 1 l S')
        self.assertIn('W* n', clipped['pdf'])


if __name__ == '__main__':
    unittest.main()
