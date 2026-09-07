"""Guard the shared grid and anchors across page boundaries."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from component_layout import ComponentLayout
from geometry import CHOICE, PAPER_HEIGHT, WRITTEN, metric
from inline import measure, parse


class FixedCatalog:
    compress_ruby = True

    def width(self, char, size, bold=False, section='', role=None):
        return size


def flow_layout():
    blueprint = {'page': {'margin_top': 10, 'body_bottom': 100,
                          'left_odd': 80, 'left_even': 60, 'body_width': 200},
                 'sidebar': False}
    layout = ComponentLayout(FixedCatalog(), blueprint, ROOT / 'resources', ROOT / 'tmp',
                             SimpleNamespace(resolved={}))
    layout.section = 'V'
    layout.group = {'id': 'V1', 'kind': 'choice'}
    layout.new_page()
    layout.drawn = []
    layout.glyph = lambda char, size, x, baseline, *args, **kwargs: layout.drawn.append(
        (char, size, x, baseline))
    return layout


class BodyGridTests(unittest.TestCase):
    def test_vector_blank_does_not_require_unused_delimiter_glyphs(self):
        class NoGlyphCatalog:
            compress_ruby = True

            def width(self, *args, **kwargs):
                raise AssertionError('A vector blank has intrinsic geometry')

        atom = measure(parse('〔41-A〕'), NoGlyphCatalog(), 11.3, 'G')[0]
        self.assertAlmostEqual(atom.width, 33.75 + 11.31 + 2 * 5.655)

    def test_dimension_validation_rejects_nonfinite_values_and_booleans(self):
        for value in (True, None, 'bad', float('nan'), float('inf'), -1):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'gap must be'):
                metric({'gap': value}, 'gap', 10, allow_zero=True)
        self.assertEqual(metric({'gap': 0}, 'gap', 10, allow_zero=True), 0)
        self.assertEqual(metric({'gap': '12.5'}, 'gap', 10), 12.5)
        with self.assertRaises(ValueError):
            metric({'gap': 0}, 'gap', 10)

    def test_choice_columns_share_the_calibrated_answer_grid(self):
        self.assertEqual(CHOICE.starts(4), [16.95, 118.74, 220.53, 322.32])
        self.assertEqual(CHOICE.starts(2), [16.95, 220.53])
        self.assertEqual(CHOICE.starts(1), [16.95])
        for columns in (1, 2, 4):
            starts, widths = CHOICE.geometry(columns, WRITTEN.width)
            for i, (start, (first, rest)) in enumerate(zip(starts, widths)):
                edge = starts[i + 1] - CHOICE.em if i + 1 < columns else WRITTEN.width
                self.assertAlmostEqual(start + CHOICE.answer_inset(0) + first,
                                       edge + CHOICE.fit_allowance)
                self.assertAlmostEqual(start + CHOICE.answer_inset(1) + rest,
                                       edge + CHOICE.fit_allowance)

    def test_choice_grid_rejects_columns_that_cannot_fit(self):
        for columns, width in ((3, 400), (4, 100), (1, 0), (1, True)):
            with self.subTest(columns=columns, width=width), self.assertRaises(ValueError):
                CHOICE.geometry(columns, width)


class FlowAnchorTests(unittest.TestCase):
    def test_image_follows_mirrored_margin_after_page_break(self):
        layout = flow_layout()
        layout.y = 99
        layout.image_geometry = lambda block, width: ('diagram', 100, 20)
        layout.image({}, layout.left + 8, 180)
        self.assertEqual(layout.n(), 2)
        command = layout.page['commands'][-1]
        self.assertEqual(command['type'], 'image')
        self.assertEqual(command['x'], 108)  # even margin 60 + inset 8 + centering 40
        self.assertEqual(command['y'], PAPER_HEIGHT - 10 - 20)

    def test_table_follows_mirrored_margin_after_page_break(self):
        layout = flow_layout()
        layout.y = 99
        layout.table({'rows': [['字']], 'borders': False}, layout.left + 8, 180)
        self.assertEqual(layout.n(), 2)
        self.assertEqual(layout.drawn[0][2], 73)  # even margin 60 + inset 8 + padding 5

    def test_multipage_frame_uses_each_pages_body_origin(self):
        layout = flow_layout()
        layout.new_page()
        layout.y = 55
        rectangles = []
        layout.rect = lambda x, y, w, h, **kwargs: rectangles.append((x, y, w, h))
        current = layout.page
        layout.frame_segments(0, 70, 8, 180)
        self.assertEqual(rectangles, [(88, 70, 180, 30), (68, 10, 180, 45)])
        self.assertIs(layout.page, current)

    def test_note_and_underline_keep_their_offsets_from_the_base_text(self):
        layout = flow_layout()
        rules = []
        layout.rule = lambda *args: rules.append(args)
        atoms = measure(parse('{{注１|__語句__}}'), layout.catalog, 11.3)
        layout.line(atoms, 90, 20, 11.3)
        base = next(g for g in layout.drawn if g[0] == '語')
        note_start = next(g for g in layout.drawn if g[0] == '（')
        self.assertEqual(note_start[2], base[2])
        self.assertAlmostEqual(note_start[3] - base[3], 6.98)
        self.assertAlmostEqual(rules[0][1] - base[3], 3)


if __name__ == '__main__':
    unittest.main()
