"""Authored line endings and contact addresses preserve natural spacing."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT / 'tests'))

from inline import NetworkAddress, parse
from reading_rules import justified_gaps
from test_reading_rules import FlowProbe, MonoCatalog


class AddressCatalog(MonoCatalog):
    def width(self, char, size, *args, **kwargs):
        return size * (.5 if char.isascii() else 1)


class SpacingProbe(FlowProbe):
    def __init__(self):
        super().__init__()
        self.catalog = AddressCatalog()
        self.spacing = []

    def line(self, atoms, x, top, size, *args, **kwargs):
        self.spacing.append((atoms, [0.0] * max(0, len(atoms) - 1)))
        super().line(atoms, x, top, size, *args, **kwargs)

    def line_gaps(self, atoms, x, top, size, gaps):
        self.spacing.append((atoms, gaps))
        FlowProbe.line(self, atoms, x, top, size)


class ReadingLinebreakTests(unittest.TestCase):
    def test_explicit_short_line_is_not_stretched_before_following_text(self):
        flow = SpacingProbe()
        flow.paragraph('ご担当者様\n次の文章です。', width=300, size=10, indent=0)
        self.assertEqual(len(flow.spacing), 2)
        self.assertFalse(any(flow.spacing[0][1]))
        self.assertEqual(flow.drawn[0][3], 'ご担当者様')

    def test_naturally_wrapped_rows_still_justify_before_an_explicit_end(self):
        flow = SpacingProbe()
        flow.paragraph('本文を自然に折り返す文章です\n後続文',
                       width=55, size=10, indent=0)
        self.assertTrue(any(gap > 0 for gap in flow.spacing[0][1]))
        before_break = next((atoms, gaps) for atoms, gaps in flow.spacing
                            if atoms.explicit_break)
        self.assertFalse(any(gap > 0 for gap in before_break[1]))

    def test_markup_and_empty_authored_rows_survive_the_line_plan(self):
        flow = SpacingProbe()
        rows = flow._reading_rows('**一行\n\n二行**\n', 200, 10, False, 'left', 0)
        self.assertEqual([''.join(atom.text for atom in row) for row in rows],
                         ['一行', '', '二行'])
        self.assertTrue(all(atom.bold for row in rows for atom in row))
        self.assertTrue(rows[0].explicit_break)

    def test_estimate_and_render_share_authored_lines_and_long_address_breaks(self):
        flow = SpacingProbe()
        block = {'type': 'paragraph', 'indent': 0,
                 'text': '連絡先\nhttps://example.test/' + 'long-path/' * 12 + '\n以上'}
        estimated = flow.estimate_block(block, 180)
        start = flow.y
        flow.block(block, 0, 180)
        self.assertAlmostEqual(flow.y - start, estimated)
        self.assertFalse(any(gap > 0 for atoms, gaps in flow.spacing
                             if atoms.explicit_break for gap in gaps))

    def test_complete_addresses_keep_markup_and_natural_internal_width(self):
        flow = SpacingProbe()
        for address in ('contact@example.test',
                        'http://www.example.test/guide/index.html',
                        'https://example.test/a_b?q=1&n=2'):
            with self.subTest(address=address):
                atoms = flow._material_atoms('__' + address + '__', 10, False)
                self.assertEqual(len(atoms), 1)
                self.assertIsInstance(atoms[0], NetworkAddress)
                self.assertTrue(atoms[0].underline)
                self.assertEqual(atoms[0].text, address)
                self.assertAlmostEqual(atoms[0].width, len(address) * 5)
                self.assertEqual(justified_gaps(atoms, 400, 10), [])

    def test_address_that_fits_a_line_moves_whole_after_a_label(self):
        flow = SpacingProbe()
        address = 'office@example.test'
        rows = flow._reading_rows('連絡先のメール：' + address, 130, 10, False, 'left', 0)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1][0].text, address)
        self.assertIsInstance(rows[-1][0], NetworkAddress)

    def test_oversize_url_prefers_delimiters_and_never_loses_characters(self):
        flow = SpacingProbe()
        address = 'https://example.test/first/second/third?q=value&next=other'
        rows = flow._reading_rows(address, 130, 10, False, 'left', 0)
        self.assertEqual(''.join(a.text for row in rows for a in row), address)
        self.assertEqual(rows[0][-1].text, 'https://example.test/')
        for row in rows:
            self.assertLessEqual(sum(a.width for a in row), 130.000001)
            self.assertTrue(all(isinstance(a, NetworkAddress) for a in row))
            self.assertFalse(any(justified_gaps(row, 130, 10)))

    def test_oversize_component_has_a_bounded_glyph_fallback(self):
        flow = SpacingProbe()
        address = 'https://example.test/' + 'x' * 100
        rows = flow._reading_rows(address, 100, 10, False, 'left', 0)
        self.assertEqual(''.join(a.text for row in rows for a in row), address)
        self.assertTrue(all(sum(a.width for a in row) <= 100.000001 for row in rows))

    def test_parentheses_cannot_carry_an_address_outside_the_line(self):
        flow = SpacingProbe()
        for text in ('本文（https://example.test/）終わり',
                     '（https://example.test/' + 'x' * 100 + '）'):
            for width in (90, 100, 110, 120):
                with self.subTest(text=text[:30], width=width):
                    rows = flow._reading_rows(text, width, 10, False, 'left', 0)
                    self.assertEqual(''.join(a.text for row in rows for a in row), text)
                    self.assertTrue(all(sum(a.width for a in row) <= width + .000001
                                        for row in rows))

    def test_address_recognition_is_opt_in_and_excludes_sentence_punctuation(self):
        text = 'https://example.test/path。'
        self.assertFalse(any(isinstance(atom, NetworkAddress) for atom in parse(text)))
        atoms = parse(text, preserve_addresses=True)
        self.assertEqual([a.text for a in atoms], ['https://example.test/path', '。'])


if __name__ == '__main__':
    unittest.main()
