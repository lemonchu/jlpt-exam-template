"""Scene compaction must preserve the renderer's exact numeric and TeX input."""
import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
sys.path.insert(0, str(ROOT))

import calibrated_renderer as renderer
import build


class DummyResolver:
    fonts = {'F': SimpleNamespace(record={'family': 'native'})}

    @staticmethod
    def use(font_id, text, form, run_id, index):
        return font_id, ord(text)


class SceneNumberTests(unittest.TestCase):
    def test_nested_json_preserves_strings_integer_ids_and_input(self):
        vector = 'q 0.999995 w 10.000000000001 20 m 30 40 l S Q'
        source = {
            'schema_version': 1,
            'large_id': 9007199254740993,
            'enabled': True,
            'empty': None,
            'label': '1.00000000000001 / 0.999995',
            'sections': [{'x': 78.96000000000001, 'y': 100.0,
                          'offsets': [0, 11.300000000000002],
                          'pdf': vector}],
        }
        before = json.dumps(source, ensure_ascii=False)
        compact = renderer.compact_scene_numbers(source)

        self.assertEqual(json.dumps(source, ensure_ascii=False), before)
        self.assertEqual(compact['sections'][0]['x'], 78.96)
        self.assertEqual(compact['sections'][0]['y'], 100)
        self.assertEqual(compact['sections'][0]['offsets'], [0, 11.3])
        self.assertEqual(compact['sections'][0]['pdf'], vector)
        self.assertEqual(compact['label'], source['label'])
        self.assertEqual(compact['large_id'], source['large_id'])
        self.assertIs(type(compact['large_id']), int)
        self.assertIs(compact['enabled'], True)
        self.assertIsNone(compact['empty'])

    def test_near_integer_and_optical_values_are_not_coarsely_rounded(self):
        values = [0.999995, 1.000001, 12.00001, 5.070304,
                  17.5501333333, 0.26796875, 0.36395161]
        compact = renderer.compact_scene_numbers(values)

        self.assertEqual(compact, values)
        self.assertNotEqual(compact[0], 1)
        self.assertEqual(format(values[0], '.5f'), '0.99999')
        for original, final in zip(values, compact):
            with self.subTest(value=original):
                self.assertEqual(renderer.number(original), renderer.number(final))

    def test_negative_zero_and_small_values_survive_json_round_trip(self):
        values = [-0.0, 0.0, -1e-20, 1e-20, 1.234567890123456e-20]
        result = json.loads(json.dumps(renderer.compact_scene_numbers(values)))

        self.assertEqual(math.copysign(1, result[0]), -1)
        self.assertEqual(renderer.number(result[0]), '-0')
        self.assertEqual(math.copysign(1, result[1]), 1)
        for original, final in zip(values, result):
            with self.subTest(value=original):
                self.assertEqual(renderer.number(original), renderer.number(final))

    def test_rejects_nonfinite_scene_numbers(self):
        for value in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                renderer.compact_scene_numbers({'pages': [{'x': value}]})

    def test_compaction_is_idempotent_and_matches_renderer_at_magnitudes(self):
        values = [1.234567890123456, -1.234567890123456,
                  999.9999999999999, 1000.00000000001,
                  0.000009999999999999999, 1.234567890123456e15,
                  1e20, 1.234567890123456e-200]
        once = renderer.compact_scene_numbers(values)
        twice = renderer.compact_scene_numbers(once)

        self.assertEqual(json.dumps(once), json.dumps(twice))
        for original, final in zip(values, once):
            with self.subTest(value=original):
                self.assertEqual(renderer.number(original), renderer.number(final))

    def test_compact_json_does_not_expand_large_exponential_numbers(self):
        source = {'coordinates': [1e100, 1e300, -1e100, -1e300,
                                  78.96000000000001, 100.0, -0.0]}
        compact = renderer.compact_scene_numbers(source)
        before = json.dumps(source, separators=(',', ':'))
        after = json.dumps(compact, separators=(',', ':'))

        self.assertLessEqual(len(after), len(before))
        for original, final in zip(source['coordinates'], compact['coordinates']):
            with self.subTest(value=original):
                self.assertEqual(renderer.number(original), renderer.number(final))
                self.assertLessEqual(len(json.dumps(final)), len(json.dumps(original)))

    def test_real_run_and_page_rendering_emit_exactly_the_same_tex(self):
        binding = {'text': 'AB'}
        base = {
            'type': 'run', 'run_id': 'r1', 'slot_count': 2, 'font': 'F',
            'offsets': [-0.0, 11.300000000000002],
            'sx': 12.00001, 'sy': 11.300000000000002,
            'x': 78.96000000000001, 'y': 0.999995,
            'shear': 0, 'role': 'body',
        }
        for transform in ({}, {'shear': .26796875}, {'rotation': 89.99999999999999}):
            with self.subTest(transform=transform):
                command = {**base, **transform}
                page = {'commands': [
                    {'type': 'vector', 'pdf': 'q 0.999995 w 1 2 m 3 4 l S Q'},
                    {'type': 'ink', 'rgb': [.13725000000000002, .12157, .12549]},
                    command,
                ]}
                compact = json.loads(json.dumps(renderer.compact_scene_numbers(page)))
                inputs = renderer._RenderInputs(
                    ROOT, ROOT, {}, {}, {'r1': binding}, ['booklet'])
                before_state, after_state = renderer._RenderState(), renderer._RenderState()

                before = renderer._render_page(page, 1, inputs, DummyResolver(), before_state)
                after = renderer._render_page(compact, 1, inputs, DummyResolver(), after_state)

                self.assertEqual(after, before)
                self.assertEqual(after_state, before_state)
                self.assertEqual(after[0], '\\NVector{\nq 0.999995 w 1 2 m 3 4 l S Q\n}')

    def test_build_compacts_only_written_scene_without_mutating_layout(self):
        pages = [{'commands': [{'type': 'image', 'asset': 'figure.pdf',
                               'x': 78.96000000000001, 'y': -0.0,
                               'width': 100.00000000000001, 'height': 200.0}]}]
        resolved = {'r1': {'glyphs': ['1.00000000001']}}
        original = copy.deepcopy(pages)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            build.write_scene_inputs(out, pages, resolved, {'figure.pdf': 'source.pdf'})
            scene = json.loads((out / 'scene.json').read_text())
            bindings = json.loads((out / 'resolved.json').read_text())

        command = scene['sections']['booklet']['pages'][0]['commands'][0]
        self.assertEqual(command['x'], 78.96)
        self.assertEqual(command['width'], 100)
        self.assertEqual(math.copysign(1, command['y']), -1)
        self.assertEqual(bindings['runs'], resolved)
        self.assertEqual(bindings['asset_files'], {'figure.pdf': 'source.pdf'})
        self.assertEqual(pages, original)


if __name__ == '__main__':
    unittest.main()
