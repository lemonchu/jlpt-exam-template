"""Small contracts shared by measured component placement."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

import reference_components
from reference_components import _integer_at_least
from geometry import body_grid


class ReferenceHelperTests(unittest.TestCase):
    def test_body_margins_follow_section_and_page_parity(self):
        self.assertEqual((body_grid('V').left(1), body_grid('R').left(2)), (78.96, 63.63))
        self.assertEqual((body_grid('L').left(1), body_grid('L').left(2)), (63.45, 45.21))

    def test_integer_contract_rejects_bool(self):
        self.assertTrue(_integer_at_least(0, 0))
        self.assertTrue(_integer_at_least(1, 1))
        for value in (True, False, 1.0, '1', None):
            with self.subTest(value=value):
                self.assertFalse(_integer_at_least(value, 0))

    def test_meta_uses_current_metadata_without_reloading_or_resolving_body_runs(self):
        reference=object.__new__(reference_components.ReferenceComponents)
        reference.metadata_path=Path('metadata.yaml')
        reference.metadata_bindings={
            'fields':{'label':{'file':'metadata.yaml','pointer':'/label','glyph_slots':1}},
            'runs':{'meta':{'glyphs':[{'field':'label','char_indices':[0]}]}},
        }
        reference.bindings={'runs':{'body':{}}}
        commands=[{'type':'run','run_id':'body'}, {'type':'run','run_id':'meta'}, {'type':'vector'}]
        with patch.object(Path,'read_text',side_effect=AssertionError('Metadata must not be reloaded')):
            for label in ('A','B'):
                reference.metadata={'label':label}
                self.assertEqual(reference.meta(commands),{'meta':{'glyphs':[label]}})


if __name__ == '__main__':
    unittest.main()
