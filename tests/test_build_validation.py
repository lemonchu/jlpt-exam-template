"""Fast boundary tests for build input validation and asset planning."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engine"))

import build


def write_yaml(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


class LoadTests(unittest.TestCase):
    def test_load_requires_a_yaml_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "value.yaml"
            for value in (None, [], "text"):
                with self.subTest(value=value):
                    write_yaml(path, value)
                    with self.assertRaisesRegex(ValueError, "expected YAML mapping"):
                        build.load(path)

    def test_schema_version_is_exactly_one(self):
        path = "document.yaml"
        self.assertEqual(build.require_schema_v1({"schema_version": 1}, path), {"schema_version": 1})
        for value in (None, False, True, 0, 1.0, 2, "1"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "schema_version must be integer 1"):
                    build.require_schema_v1({"schema_version": value}, path)


class ContentLoadingTests(unittest.TestCase):
    def test_load_content_collects_present_sections_and_skips_absent_ones(self):
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory)
            write_yaml(content / "V.yaml", {
                "schema_version": 1,
                "section": "V",
                "groups": [{"id": "V1", "kind": "choice", "items": []}],
            })
            write_yaml(content / "R.yaml", {
                "schema_version": 1,
                "section": "R",
                "groups": [{"id": "R8", "kind": "reading", "items": []}],
            })

            groups, documents = build.load_content(content)

        self.assertEqual(list(groups), ["V1", "R8"])
        self.assertEqual(set(documents), {"V.yaml", "R.yaml"})
        self.assertIs(groups["V1"], documents["V.yaml"]["groups"][0])

    def test_load_content_rejects_malformed_section_documents(self):
        cases = (
            ({"schema_version": 2, "section": "V", "groups": []}, "schema_version must be integer 1"),
            ({"schema_version": 1, "section": "G", "groups": []}, "section must be V"),
            ({"schema_version": 1, "section": "V", "groups": {}}, "groups must be a list"),
            ({"schema_version": 1, "section": "V", "groups": [None]}, "group id must begin with V"),
            ({"schema_version": 1, "section": "V", "groups": [{"id": "G1"}]}, "group id must begin with V"),
        )
        for document, message in cases:
            with self.subTest(document=document):
                with tempfile.TemporaryDirectory() as directory:
                    content = Path(directory)
                    write_yaml(content / "V.yaml", document)
                    with self.assertRaisesRegex(ValueError, message):
                        build.load_content(content)

    def test_load_content_rejects_duplicate_group_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            content = Path(directory)
            write_yaml(content / "V.yaml", {
                "schema_version": 1,
                "section": "V",
                "groups": [{"id": "V1"}, {"id": "V1"}],
            })
            with self.assertRaisesRegex(ValueError, "Duplicate group id: V1"):
                build.load_content(content)


class BlueprintValidationTests(unittest.TestCase):
    def test_default_and_numeric_string_a4_dimensions_are_accepted(self):
        self.assertEqual(build.validate_blueprint({"groups": []}, "bp.yaml"), {"groups": []})
        blueprint = {
            "groups": [],
            "page": {"width": "595", "height": "842"},
            "numbering": {"mode": "source"},
        }
        self.assertIs(build.validate_blueprint(blueprint, "bp.yaml"), blueprint)

    def test_a4_tolerance_has_a_strict_boundary(self):
        accepted = {"groups": [], "page": {"width": 595 + 1e-6, "height": 842 - 1e-6}}
        self.assertIs(build.validate_blueprint(accepted, "bp.yaml"), accepted)
        rejected = {"groups": [], "page": {"width": 595 + 1.1e-6, "height": 842}}
        with self.assertRaisesRegex(ValueError, "supports only 595 x 842"):
            build.validate_blueprint(rejected, "bp.yaml")

    def test_blueprint_structure_and_numbering_errors_are_specific(self):
        cases = (
            ({}, "groups must be a list"),
            ({"groups": [], "page": []}, "page must be a mapping"),
            ({"groups": [], "page": {"width": "wide"}}, "width and height must be numbers"),
            ({"groups": [], "page": {"width": True}}, "width and height must be numbers"),
            ({"groups": [], "numbering": []}, "numbering must be a mapping"),
            ({"groups": [], "numbering": {"mode": "random"}}, "unknown numbering mode"),
            ({"groups": [], "numbering": {"start": 0}}, "numbering.start must be a positive integer"),
            ({"groups": [], "numbering": {"start": True}}, "numbering.start must be a positive integer"),
            ({"groups": [], "page_number_start": 0}, "page_number_start must be a positive integer"),
            ({"groups": [], "cover": "yes"}, "cover must be true or false"),
        )
        for blueprint, message in cases:
            with self.subTest(blueprint=blueprint):
                with self.assertRaisesRegex(ValueError, message):
                    build.validate_blueprint(blueprint, "bp.yaml")


class AssetResolutionTests(unittest.TestCase):
    def test_metadata_content_and_generated_assets_are_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = root / "resources"
            profile = root / "profile"
            output = root / "output"
            resources.mkdir()
            profile.mkdir()
            (resources / "front.pdf").write_bytes(b"front")
            (resources / "question.png").write_bytes(b"question")
            bindings = {
                "front": {"metadata_pointer": "/assets/front"},
                "question": {"file": "R.yaml", "pointer": "/groups/0/asset"},
                "missing-file": {"file": "missing.yaml", "pointer": "/asset"},
                "missing-key": {"file": "R.yaml", "pointer": "/groups/0/missing"},
                "absent-resource": {"metadata_pointer": "/assets/absent"},
                "generated": {"metadata_pointer": "/assets/front"},
            }
            (profile / "asset-bindings.json").write_text(json.dumps(bindings), encoding="utf-8")
            metadata = {"assets": {"front": "front.pdf", "absent": "not-there.pdf"}}
            content_files = {"R.yaml": {"groups": [{"asset": "question.png"}]}}
            layout = SimpleNamespace(assets={"generated", "layout-only"})

            with patch.object(build, "ROOT", root):
                assets = build.resolve_assets(profile, metadata, content_files, layout, output)

            self.assertEqual(assets["front"], str((resources / "front.pdf").resolve()))
            self.assertEqual(assets["question"], str((resources / "question.png").resolve()))
            self.assertNotIn("missing-file", assets)
            self.assertNotIn("missing-key", assets)
            self.assertNotIn("absent-resource", assets)
            self.assertEqual(assets["generated"], str(output / "generated"))
            self.assertEqual(assets["layout-only"], str(output / "layout-only"))

    def test_asset_paths_cannot_escape_resources(self):
        for unsafe_name in ("../secret.pdf", "/tmp/secret.pdf"):
            with self.subTest(unsafe_name=unsafe_name):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    profile = root / "profile"
                    (root / "resources").mkdir()
                    profile.mkdir()
                    (profile / "asset-bindings.json").write_text(json.dumps({
                        "unsafe": {"metadata_pointer": "/assets/file"},
                    }), encoding="utf-8")
                    with patch.object(build, "ROOT", root):
                        with self.assertRaisesRegex(ValueError, "Unsafe asset path"):
                            build.resolve_assets(
                                profile,
                                {"assets": {"file": unsafe_name}},
                                {},
                                SimpleNamespace(assets=set()),
                                root / "output",
                            )


class _FakeReferenceComponents:
    def __init__(self, profile, metadata_path):
        self.contracts = json.loads((Path(profile) / "composition-contracts.json").read_text())
        self.pages = {}
        self.resolved = {}
        self.ledger = []
        self.metadata_audit = {}
        self.fonts = None

    def cover(self, section, body_pages):
        return []


class _FakeFonts:
    def __init__(self, profile, font_config, root):
        self.resolver = SimpleNamespace(resolved_codes={})
        self.font_config_report = {"config": str(font_config)} if font_config else {}


class _FakeLayout:
    instances = []

    def __init__(self, fonts, blueprint, resources, output, reference):
        self.start_page = int(blueprint.get("page_number_start", 1))
        self.pages = []
        self.number = 1
        self.assets = set()
        self.component_audit = {}
        self.item_records = []
        self.events = []
        self.__class__.instances.append(self)

    def new_page(self):
        self.events.append("padding")
        self.pages.append({"commands": [], "bands": []})

    def render_group(self, group, config):
        self.events.append(("group", group["id"]))
        self.pages.append({"commands": [], "bands": []})

    def decorate(self):
        pass


class StartOnTests(unittest.TestCase):
    def _run_build(self, start_on):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        content = root / "content" / "paper-test"
        profile = root / "profiles" / "n1-original"
        blueprint_path = root / "blueprint.yaml"
        metadata_path = root / "metadata.yaml"
        profile.mkdir(parents=True)
        write_yaml(content / "V.yaml", {
            "schema_version": 1,
            "section": "V",
            "groups": [{"id": "V1", "kind": "choice", "items": []}],
        })
        blueprint = {
            "schema_version": 1,
            "page": {"width": 595, "height": 842},
            "numbering": {"mode": "continuous"},
            "cover": False,
            "sidebar": False,
            "groups": [{"id": "V1", "start_on": start_on}],
        }
        write_yaml(blueprint_path, blueprint)
        write_yaml(metadata_path, {
            "schema_version": 1,
            "schema_kind": "exam_metadata",
            "booklets": {"written": {"subject_ja": "言語知識・読解"}},
            "sections": {"V": {"sidebar_label": "文字・語彙"}},
            "assets": {},
        })
        contracts = {
            "blueprints": {"written": blueprint},
            "components": {"written": None},
        }
        (profile / "composition-contracts.json").write_text(json.dumps(contracts), encoding="utf-8")
        (profile / "asset-bindings.json").write_text("{}", encoding="utf-8")
        args = SimpleNamespace(
            paper="paper-test",
            booklet="written",
            blueprint=blueprint_path,
            metadata=metadata_path,
            fonts=None,
            no_compile=True,
            recompose=True,
        )
        _FakeLayout.instances.clear()
        with (
            patch.object(build, "ROOT", root),
            patch.object(build, "parse_args", return_value=args),
            patch.object(build, "ReferenceComponents", _FakeReferenceComponents),
            patch.object(build, "ComponentFonts", _FakeFonts),
            patch.object(build, "ComponentLayout", _FakeLayout),
            patch.object(build, "render"),
            redirect_stdout(StringIO()),
        ):
            build.main()
        return _FakeLayout.instances[-1]

    def test_start_on_inserts_only_the_needed_parity_page(self):
        left_layout = self._run_build("left")
        self.assertEqual(left_layout.events, ["padding", ("group", "V1")])

        right_layout = self._run_build("right")
        self.assertEqual(right_layout.events, [("group", "V1")])

    def test_invalid_start_on_is_rejected_before_rendering_group(self):
        with self.assertRaisesRegex(ValueError, "start_on must be left or right"):
            self._run_build("verso")
        self.assertEqual(_FakeLayout.instances[-1].events, [])


if __name__ == "__main__":
    unittest.main()
