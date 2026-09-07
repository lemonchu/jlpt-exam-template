"""Fast boundary tests for build input validation and asset planning."""
from contextlib import redirect_stdout
from io import StringIO
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
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.resources = self.root / "resources"
        self.output = self.root / "output"
        self.resources.mkdir()
        self.output.mkdir()
        self.layout = SimpleNamespace(assets=set())
        root_patch = patch.object(build, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def resolve(self, bindings, metadata=None, content_files=None, *, slots):
        pages = [{"commands": [{"type": "image", "asset": slot} for slot in slots]}]
        return build.resolve_assets(bindings, metadata or {}, content_files or {},
                                    self.layout, self.output, pages)

    def test_metadata_content_and_generated_assets_are_resolved(self):
        (self.resources / "front.pdf").write_bytes(b"front")
        (self.resources / "question.png").write_bytes(b"question")
        for asset in ("generated", "layout-only"):
            (self.output / asset).write_bytes(b"generated")
        bindings = {
            "front": {"metadata_pointer": "/assets/front"},
            "question": {"file": "R.yaml", "pointer": "/groups/0/asset"},
            "missing-file": {"file": "missing.yaml", "pointer": "/asset"},
            "missing-key": {"file": "R.yaml", "pointer": "/groups/0/missing"},
            "absent-resource": {"metadata_pointer": "/assets/absent"},
            "unsafe": {"metadata_pointer": "/assets/unsafe"},
            "generated": {"metadata_pointer": "/assets/missing"},
        }
        metadata = {"assets": {"front": "front.pdf", "absent": "not-there.pdf",
                               "unsafe": "../secret.pdf"}}
        content_files = {"R.yaml": {"groups": [{"asset": "question.png"}]}}
        self.layout.assets = {"generated", "layout-only", "unreferenced-missing"}

        assets = self.resolve(bindings, metadata, content_files,
                              slots=("front", "question", "generated", "layout-only", "front"))

        self.assertEqual(assets, {
            "front": str((self.resources / "front.pdf").resolve()),
            "question": str((self.resources / "question.png").resolve()),
            "generated": str((self.output / "generated").resolve()),
            "layout-only": str((self.output / "layout-only").resolve()),
        })

    def test_asset_paths_cannot_escape_resources(self):
        for unsafe_name in ("../secret.pdf", "/tmp/secret.pdf"):
            with self.subTest(unsafe_name=unsafe_name):
                with self.assertRaisesRegex(ValueError, "Unsafe asset path"):
                    self.resolve({"unsafe": {"metadata_pointer": "/assets/file"}},
                                 {"assets": {"file": unsafe_name}}, slots=("unsafe",))

    def test_referenced_missing_bindings_and_files_fail_clearly(self):
        cases = (
            ({}, {}, {}, ValueError, "Missing asset binding"),
            ({"metadata_pointer": "/missing"}, {}, {}, ValueError, "Cannot resolve asset binding"),
            ({"file": "missing.yaml", "pointer": "/asset"}, {}, {},
             ValueError, "Cannot resolve asset binding"),
            ({"file": "R.yaml", "pointer": "/missing"}, {}, {"R.yaml": {}},
             ValueError, "Cannot resolve asset binding"),
            ({"metadata_pointer": "/asset"}, {"asset": "absent.png"}, {},
             FileNotFoundError, "Current image asset is missing"),
        )
        for binding, metadata, documents, error, message in cases:
            with self.subTest(binding=binding), self.assertRaisesRegex(error, message):
                self.resolve({"current": binding} if binding else {}, metadata, documents,
                             slots=("current",))

    def test_generated_assets_must_exist_inside_the_output_directory(self):
        for asset, error, message in (
            ("missing.png", FileNotFoundError, "Current image asset is missing"),
            ("../secret.pdf", ValueError, "Unsafe generated asset path"),
            ("/tmp/secret.pdf", ValueError, "Unsafe generated asset path"),
        ):
            with self.subTest(asset=asset), self.assertRaisesRegex(error, message):
                self.layout.assets = {asset}
                self.resolve({}, slots=(asset,))


class _FakeCoverTemplates:
    def __init__(self, profile, metadata_path):
        self.pages = {}
        self.resolved = {}
        self.ledger = []
        self.metadata_audit = {}
        self.fonts = None
        self.asset_bindings = {}

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
        args = SimpleNamespace(
            paper="paper-test",
            booklet="written",
            blueprint=blueprint_path,
            metadata=metadata_path,
            fonts=None,
            no_compile=True,
        )
        _FakeLayout.instances.clear()
        with (
            patch.object(build, "ROOT", root),
            patch.object(build, "parse_args", return_value=args),
            patch("cover_templates.CoverTemplates", _FakeCoverTemplates),
            patch("rule_typography.RuleFonts", _FakeFonts),
            patch("rule_layout.RuleLayout", _FakeLayout),
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
