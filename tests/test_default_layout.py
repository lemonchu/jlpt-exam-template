"""The public default must work without the deprecated body calibration data."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build


class DefaultBuildTests(unittest.TestCase):
    def test_real_default_build_does_not_read_legacy_body_profiles(self):
        """Exercise templates, actual fonts, page flow and scene rendering, not a mock layout."""
        forbidden = {
            'layout.json', 'body-bindings.json', 'components.json',
            'composition-contracts.json', 'glyph-capacities.json',
            'asset-bindings.json',
        }
        original_read = Path.read_text
        reads = set()

        def read_text(path, *args, **kwargs):
            if path.parent == ROOT / 'profiles/n1-original':
                self.assertNotIn(path.name, forbidden,
                                 f'Default rules unexpectedly loaded legacy body data: {path}')
                reads.add(path.name)
            return original_read(path, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            blueprint = build.load(ROOT / 'blueprints/written.yaml')
            # Use real IDs from the current authored corpus, without assuming
            # how those IDs were named or copying any source coordinate fixture.
            groups, documents = build.load_content(ROOT / 'content/paper-a')
            # Unselected source images must not be resolved through old R slots.
            unselected_images = [block for group in documents['R.yaml']['groups']
                                 for item in build.iter_questions(group['items'])
                                 for block in item.get('stimulus', [])
                                 if block['type'] == 'image']
            self.assertTrue(unselected_images)
            for block in unselected_images:
                block['asset'] = '../not-selected.pdf'
            blueprint['groups'] = [{'id': 'G6', 'items': [
                item['id'] for item in groups['G6']['items'][:2]
            ]}]
            blueprint['components_file'] = str(ROOT / 'blueprints/components.yaml')
            blueprint_path = temporary / 'blueprint.yaml'
            blueprint_path.write_text(yaml.safe_dump(blueprint), encoding='utf-8')
            args = build.parse_args([
                '--blueprint', str(blueprint_path), '--no-compile',
                '--output-dir', str(temporary / 'out'),
            ])
            stdout, stderr = StringIO(), StringIO()
            with patch.object(build, 'parse_args', return_value=args), \
                    patch.object(build, 'load_content', return_value=(groups, documents)), \
                    patch.object(Path, 'read_text', read_text), \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                build.main()
            project = temporary / 'out/paper-a-written'
            report = json.loads((project / 'build-report.json').read_text())
            self.assertEqual(report['layout_mode'], 'rules')
            self.assertFalse(report['deprecated_layout'])
            self.assertFalse(report['compiled'])
            self.assertEqual(report['page_count'], 3)
            self.assertTrue(all(group['mode'] == 'rules' for group in report['components']))
            self.assertTrue(report['components'][0]['ordering_heading_template'])
            self.assertTrue(report['components'][0]['ordering_example_template'])
            self.assertTrue((project / 'main.tex').is_file())
            self.assertNotIn('deprecated', stderr.getvalue())
            self.assertIn('cover-template.json', reads)

            # A preview build must not present an existing public PDF as new.
            previous_pdf = temporary / 'out/N1-paper-a-written.pdf'
            previous_pdf.write_bytes(b'previous PDF fixture')
            stderr = StringIO()
            with patch.object(build, 'parse_args', return_value=args), \
                    patch.object(build, 'load_content', return_value=(groups, documents)), \
                    patch.object(Path, 'read_text', read_text), \
                    redirect_stdout(StringIO()), redirect_stderr(stderr):
                build.main()
            self.assertEqual(previous_pdf.read_bytes(), b'previous PDF fixture')
            self.assertIn('will not update the existing PDF', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
