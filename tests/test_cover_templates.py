"""Dedicated cover templates preserve appearance without body calibration reads."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))

from component_fonts import ComponentFonts
from cover_templates import CoverTemplates
from metadata_components import MetadataCapacityError, _regions, resolve_metadata_components
from reference_components import ReferenceComponents

PROFILE = ROOT / 'profiles/n1-original'
METADATA = ROOT / 'content/common/metadata.yaml'
BODY_FILES = {'layout.json', 'body-bindings.json', 'components.json',
              'composition-contracts.json', 'glyph-capacities.json', 'metadata-bindings.json',
              'asset-bindings.json'}


@contextmanager
def without_body_reads():
    read_text = Path.read_text

    def guarded(path, *args, **kwargs):
        if path.name in BODY_FILES:
            raise AssertionError(f'Cover read a legacy calibration file: {path.name}')
        return read_text(path, *args, **kwargs)

    with patch.object(Path, 'read_text', guarded):
        yield


@contextmanager
def changed_metadata(change):
    metadata = yaml.safe_load(METADATA.read_text())
    change(metadata)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'metadata.yaml'
        path.write_text(yaml.safe_dump(metadata, allow_unicode=True), encoding='utf-8')
        yield path


class CoverTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fonts = ComponentFonts(PROFILE, None, ROOT)

    def test_template_contains_only_cover_geometry_and_referenced_metadata(self):
        template = json.loads((PROFILE / 'cover-template.json').read_text())
        layout = json.loads((PROFILE / 'layout.json').read_text())
        bindings = json.loads((PROFILE / 'metadata-bindings.json').read_text())
        self.assertEqual(set(template['sections']), {'V', 'L'})
        run_ids = set()
        for section, data in template['sections'].items():
            self.assertEqual(data['pages'], layout['sections'][section]['pages'][:2])
            run_ids.update(command['run_id'] for page in data['pages']
                           for command in page['commands'] if command['type'] == 'run')
        self.assertEqual(set(template['bindings']['runs']), run_ids)
        fields = {glyph['field'] for run in template['bindings']['runs'].values()
                  for glyph in run['glyphs']}
        self.assertEqual(set(template['bindings']['fields']), fields)
        for name in fields:
            self.assertEqual(template['bindings']['fields'][name], bindings['fields'][name])
        for run_id in run_ids:
            self.assertEqual(template['bindings']['runs'][run_id], bindings['runs'][run_id])
        self.assertEqual(template['regions'], {key: list(value)
                         for key, value in _regions(layout, bindings).items()})
        assets = {command['asset'] for data in template['sections'].values()
                  for page in data['pages'] for command in page['commands']
                  if command['type'] == 'image'}
        self.assertEqual(set(template['assets']), assets)
        self.assertTrue(all('metadata_pointer' in binding for binding in template['assets'].values()))

    def test_normal_cover_runtime_never_reads_body_calibration(self):
        with without_body_reads():
            cover = CoverTemplates(PROFILE, METADATA)
            cover.fonts = self.fonts
            for section, body_pages in [('V', 31), ('L', 13)]:
                pages = cover.cover(section, body_pages)
                self.assertEqual(len(pages), 2)
                self.assertEqual(pages, cover.cover_template['sections'][section]['pages'])
            self.assertEqual(cover.ledger, [])
            self.assertEqual(set(cover.layout), {'paper'})
            self.assertEqual(len(cover.metadata_audit), 4)
            self.assertTrue(all(not audit['changed_fields'] for audit in cover.metadata_audit))

    def test_current_notice_text_reflows_without_legacy_regions_or_bindings(self):
        text = 'この問題用紙を開けないでください。'
        change = lambda metadata: metadata['booklets']['written']['notices'][0].update(text=text)
        with changed_metadata(change) as path, without_body_reads():
            cover = CoverTemplates(PROFILE, path)
            cover.fonts = self.fonts
            cover.cover('V', 31)
            changes = [field for audit in cover.metadata_audit for field in audit['changed_fields']]
            self.assertEqual([field['field'] for field in changes], ['written.notice.0.ja'])
            field = changes[0]
            actual = ''.join(char for run_id in field['new_runs']
                             for char in cover.resolved[run_id]['glyphs'])
            self.assertEqual(actual, '１．' + text)
            self.assertLessEqual(field['max_advance_right'], field['region']['right'])

    def test_oversized_notices_fail_instead_of_silently_clipping(self):
        change = lambda metadata: metadata['booklets']['written']['notices'][0].update(text='問題' * 100)
        with changed_metadata(change) as path, without_body_reads():
            cover = CoverTemplates(PROFILE, path)
            cover.fonts = self.fonts
            with self.assertRaisesRegex(MetadataCapacityError, 'does not fit'):
                cover.cover('V', 31)

    def test_cover_notice_count_remains_an_explicit_template_constraint(self):
        change = lambda metadata: metadata['booklets']['written']['notices'].pop()
        with changed_metadata(change) as path, without_body_reads():
            cover = CoverTemplates(PROFILE, path)
            cover.fonts = self.fonts
            with self.assertRaisesRegex(MetadataCapacityError, 'notice blocks'):
                cover.cover('V', 31)

    def test_pages_are_copied_and_body_page_count_is_current(self):
        with without_body_reads():
            cover = CoverTemplates(PROFILE, METADATA)
            first = cover.cover('V', 31)
            old_runs = copy.deepcopy(cover.resolved)
            first[0]['commands'].clear()
            second = cover.cover('V', 33)
            self.assertTrue(second[0]['commands'])
            self.assertNotEqual(old_runs, cover.resolved)
            self.assertEqual(second, cover.cover_template['sections']['V']['pages'])

    def test_optional_marks_keep_current_metadata_and_optical_positions(self):
        cover = CoverTemplates(PROFILE, METADATA)
        cover.metadata['booklets']['written'].update(session_label='（２０１４－２）', form_symbol='A')
        with self.assertRaisesRegex(ValueError, 'configured component font resolver'):
            cover._cover_marks('written')
        widths = {ord(char): 1000 for char in '（２０１４－２）A'}
        cover.fonts = SimpleNamespace(
            configured=lambda role: role,
            resolver=SimpleNamespace(resolve=lambda font, char, form: (font, ord(char))),
            faces={role: SimpleNamespace(widths=widths, upm=1000)
                   for role in ('cover_session', 'cover_symbol')},
        )
        commands, runs = cover._cover_marks('written')
        self.assertEqual(len(commands), 3)
        self.assertEqual(runs['cover-written-session-label']['glyphs'], list('（２０１４－２）'))
        self.assertEqual(commands[-1]['y'], 807.25)
        self.assertAlmostEqual(commands[-1]['x'] + 23.6 / 2, 42.36)

    def test_legacy_uses_the_same_cover_methods(self):
        self.assertIs(ReferenceComponents.cover, CoverTemplates.cover)
        self.assertIs(ReferenceComponents._cover_marks, CoverTemplates._cover_marks)

    def test_preloaded_cover_fit_matches_legacy_metadata_resolution(self):
        layout = json.loads((PROFILE / 'layout.json').read_text())
        for section, body_pages in [('V', 31), ('L', 13)]:
            cover = CoverTemplates(PROFILE, METADATA)
            cover.fonts = self.fonts
            actual = cover.cover(section, body_pages)
            resolved, audits = {}, []
            expected = copy.deepcopy(layout['sections'][section]['pages'][:2])
            for page in expected:
                page['commands'], runs, audit = resolve_metadata_components(
                    PROFILE, METADATA, page['commands'], self.fonts, body_pages)
                resolved.update(runs)
                audits.append(audit)
            self.assertEqual(actual, expected)
            self.assertEqual(cover.resolved, resolved)
            self.assertEqual(cover.metadata_audit, audits)


if __name__ == '__main__':
    unittest.main()
