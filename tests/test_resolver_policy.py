"""The renderer has one installed font-resolution policy."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from calibrated_renderer import Resolver
from font_overrides import install_overrides


class ResolverPolicyTests(unittest.TestCase):
    def test_resolution_requires_the_strict_policy(self):
        resolver = Resolver(ROOT / 'profiles/n1-original')
        with self.assertRaisesRegex(RuntimeError, 'Install the font policy'):
            resolver.resolve('V010', '日')
        install_overrides(resolver, project_root=ROOT)
        font_id, code = resolver.resolve('V010', '日')
        self.assertIn(font_id, resolver.fonts)
        self.assertIsInstance(code, int)

    def test_reinstalling_the_same_policy_is_idempotent(self):
        resolver = Resolver(ROOT / 'profiles/n1-original')
        first = install_overrides(resolver, project_root=ROOT)
        second = install_overrides(resolver, project_root=ROOT)
        self.assertIs(first, second)


if __name__ == '__main__':
    unittest.main()
