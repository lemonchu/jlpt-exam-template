"""Focused tests for shared metadata loading and formatter helpers."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from metadata_bindings import format_field, format_pointer_template, load_metadata, resolve, resolve_loaded


class MetadataLoadingTests(unittest.TestCase):
    def test_page_plan_and_body_pages_have_one_shared_loader(self):
        bindings = {'page_plan': {'sections': {'V': {'page_count': 4}}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'metadata.yaml'
            path.write_text('sections:\n  V:\n    title: Vocabulary\n')
            metadata = load_metadata(path, bindings, body_pages=7)
        self.assertEqual(metadata['sections']['V'], {'title': 'Vocabulary', 'page_count': 4})
        self.assertEqual(metadata['_body_pages'], 7)

    def test_body_pages_rejects_bool_and_negative_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'metadata.yaml'
            path.write_text('{}\n')
            for value in (True, -1, 1.5):
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'nonnegative integer'):
                    load_metadata(path, {}, body_pages=value)

    def test_prepend_template_uses_declared_variables(self):
        metadata = {'notice': '{page}: ', 'sections': {'V': {'first_content_page': 2,
                                                              'first_printed_page': 3}}}
        transform = {'pointer': '/notice', 'variables': {
            'page': {'calc': 'section_page', 'section': 'V', 'page': 5,
                     'digits': 'fullwidth'}}}
        self.assertEqual(format_pointer_template(transform, metadata), '６: ')

    def test_format_and_prepend_share_template_variable_rules(self):
        metadata = {'label': '{value}', 'prefix': '[{value}]', 'value': 12}
        field = {
            'pointer': '/label',
            'formatter': [
                {'op': 'format', 'variables': {
                    'value': {'pointer': '/value', 'digits': 'fullwidth'},
                }},
                {'op': 'prepend', 'pointer': '/prefix', 'variables': {
                    'value': {'pointer': '/value', 'digits': 'halfwidth'},
                }},
            ],
        }
        self.assertEqual(format_field(field, metadata), list('[12]１２'))

    def test_resolve_uses_the_same_body_page_validation(self):
        bindings = {'fields': {}, 'runs': {}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / 'metadata.yaml'
            binding_file = root / 'bindings.json'
            metadata.write_text('{}\n')
            binding_file.write_text(json.dumps(bindings))
            with self.assertRaisesRegex(ValueError, 'nonnegative integer'):
                resolve(metadata, binding_file, body_pages=True)

    def test_sections_and_run_ids_share_one_run_filter(self):
        bindings = {
            'fields': {
                'v': {'file': 'metadata.yaml', 'pointer': '/values/v', 'glyph_slots': 1},
                'l': {'file': 'metadata.yaml', 'pointer': '/values/l', 'glyph_slots': 1},
            },
            'runs': {
                'V-run': {'glyphs': [{'field': 'v', 'char_indices': [0]}]},
                'L-run': {'glyphs': [{'field': 'l', 'char_indices': [0]}]},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = root / 'metadata.yaml'
            binding_file = root / 'bindings.json'
            metadata.write_text('values:\n  v: V\n  l: L\n')
            binding_file.write_text(json.dumps(bindings))
            self.assertEqual(set(resolve(metadata, binding_file, sections='V')['runs']), {'V-run'})
            self.assertEqual(set(resolve(metadata, binding_file, run_ids={'L-run'})['runs']), {'L-run'})

    def test_loaded_metadata_can_be_resolved_without_reading_it_again(self):
        bindings = {
            'fields': {
                'label': {'file': 'custom.yaml', 'pointer': '/label', 'glyph_slots': 2},
            },
            'runs': {
                'V-run': {'glyphs': [{'field': 'label', 'char_indices': [1, 0]}]},
            },
        }
        result = resolve_loaded({'label': 'AB'}, bindings, 'custom.yaml')
        self.assertEqual(result, {'runs': {'V-run': {'glyphs': ['BA']}}})


if __name__ == '__main__':
    unittest.main()
