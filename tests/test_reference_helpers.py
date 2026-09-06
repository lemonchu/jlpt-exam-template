"""Small contracts shared by measured component placement."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

import reference_components
from reference_components import _body_left, _integer_at_least


class ReferenceHelperTests(unittest.TestCase):
    def test_body_margins_follow_section_and_page_parity(self):
        self.assertEqual((_body_left('V', 1), _body_left('R', 2)), (78.96, 63.63))
        self.assertEqual((_body_left('L', 1), _body_left('L', 2)), (63.45, 45.21))

    def test_integer_contract_rejects_bool(self):
        self.assertTrue(_integer_at_least(0, 0))
        self.assertTrue(_integer_at_least(1, 1))
        for value in (True, False, 1.0, '1', None):
            with self.subTest(value=value):
                self.assertFalse(_integer_at_least(value, 0))

    def test_metadata_is_loaded_once_per_body_page_count(self):
        reference=object.__new__(reference_components.ReferenceComponents)
        reference.metadata_path=Path('metadata.yaml')
        reference.metadata_bindings={'fields':{},'runs':{}}
        reference.bindings={'runs':{}}
        reference._metadata_cache={None:{'cached':True}}
        with patch.object(reference_components,'load_metadata',return_value={'loaded':True}) as loader:
            self.assertEqual(reference.meta([],body_pages=31),{})
            self.assertEqual(reference.meta([],body_pages=31),{})
        loader.assert_called_once_with(reference.metadata_path,reference.metadata_bindings,31)


if __name__ == '__main__':
    unittest.main()
