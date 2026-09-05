#!/usr/bin/env python3
"""Validate public content and bundled subsets without installing full fonts."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import yaml
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
KINDS = {"choice", "word_order", "reading", "cloze", "listening_choice",
         "listening_compound", "listening_memo"}
FONT_EXTENSIONS = {".otf", ".ttf", ".ttc", ".otc", ".cff", ".pfa", ".pfb", ".woff", ".woff2"}
FONT_SIGNATURES = (b"OTTO", b"\x00\x01\x00\x00", b"ttcf", b"wOFF", b"wOF2", b"%!PS-AdobeFont")


def yaml_file(path):
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"YAML mapping required: {path}")
    return value


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def main():
    records = []
    for paper in ("paper-a", "paper-b"):
        groups = {}
        for section in "VGRL":
            content = yaml_file(ROOT / "content" / paper / f"{section}.yaml")
            assert content["schema_version"] == 1 and content["section"] == section
            identifiers = set()
            for group in content["groups"]:
                assert group["id"].startswith(section) and group["id"] not in groups
                assert group["kind"] in KINDS
                groups[group["id"]] = group
                for item in walk(group):
                    if "id" in item:
                        assert item["id"] not in identifiers, (paper, section, item["id"])
                        identifiers.add(item["id"])
                    if "options" in item:
                        assert len(item["options"]) == 4 and all(isinstance(v, str) for v in item["options"])
                    if item.get("type") == "image":
                        asset = Path(item["asset"])
                        assert not asset.is_absolute() and ".." not in asset.parts
                        assert (ROOT / "resources" / asset).is_file(), asset
        for booklet in ("written", "listening"):
            blueprint = yaml_file(ROOT / "blueprints" / f"{booklet}.yaml")
            selected = [entry if isinstance(entry, str) else entry["id"] for entry in blueprint["groups"]]
            assert len(selected) == len(set(selected)) and all(g in groups for g in selected)
            count = sum(1 for g in selected for node in walk(groups[g])
                        if "options" in node and not node.get("is_example"))
            records.append({"paper": paper, "booklet": booklet, "formal_printed_items": count})
    catalog = json.loads((ROOT / "profiles/n1-original/font-catalog.json").read_text())
    assert not catalog.get("fallback_fonts"), "Generic substitute fonts must not be registered"
    for font in catalog["fonts"].values():
        assert not re.search(r"noto|droid|sourcehan", font["name"], re.I)
    profile = ROOT / "profiles/n1-original"
    original = json.loads((profile / "font-reconstruction.json").read_text())["fonts"]
    sample = json.loads((profile / "sample-fonts.json").read_text())
    allowed_fonts = {}
    for fid, font in catalog["fonts"].items():
        allowed_fonts["profiles/n1-original/" + font["file"]] = original[fid]["file_sha256"]
    for fid, font in sample["fonts"].items():
        assert font["bundled_sample"] and not font["user_supplied"]
        assert font["source_face"] in {"Ryumin-regular", "FutoGoB101-Bold"}
        assert font["file"].startswith("fonts/samples/")
        allowed_fonts["profiles/n1-original/" + font["file"]] = font["sha256"]
        provenance = sample["provenance"][fid]
        with TTFont(profile / font["file"]) as tt:
            assert len(tt.getGlyphOrder()) == provenance["packaged_glyph_count"]
            assert len(tt.getGlyphOrder()) < provenance["source_glyph_count"] // 4
            assert sorted(f"U+{cp:04X}" for cp in tt.getBestCmap()) == sorted(provenance["unicode_codepoints"])
    for name, digest in allowed_fonts.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, f"Bundled font changed: {name}"
    config = yaml_file(ROOT / "fonts.yaml")
    assert set(config["faces"]) == {"Ryumin-regular", "FutoGoB101-Bold", "ShinGo-regular", "ShinGo-Bold", "GothicMB101-Bold"}
    tracked = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                             cwd=ROOT, capture_output=True, check=True).stdout
    found_fonts = set()
    for name in filter(None, tracked.decode().split("\0")):
        path = ROOT / name
        assert path.suffix.lower() not in {".zip", ".7z", ".tar", ".gz"}, f"Publish unpacked sources: {name}"
        assert not name.startswith(("output/", "input-pdfs/", "private/", "resources/user-fonts/",
                                    "profiles/n1-original/fonts/overrides/")), name
        assert not path.is_symlink(), f"Public files must be regular files: {name}"
        with path.open("rb") as stream:
            header = stream.read(32)
        if path.suffix.lower() in FONT_EXTENSIONS or header.startswith(FONT_SIGNATURES):
            assert name in allowed_fonts, f"Only declared original/sample subsets may be published: {name}"
            found_fonts.add(name)
    assert found_fonts == set(allowed_fonts), "Bundled font files must not be omitted or ignored"
    print(json.dumps({"status": "PASS", "bundled_original_fonts": len(catalog["fonts"]),
                      "bundled_sample_fonts": len(sample["fonts"]), "full_font_files": 0,
                      "generic_substitute_fonts": 0, "content": records}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
