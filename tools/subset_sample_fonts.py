#!/usr/bin/env python3
"""Package only sample glyphs from matching local full fonts, using build reports.

For maintainers: build all four booklets with the corresponding full fonts,
then pass their output directory. Ordinary users do not need to run this tool.
No fonts are downloaded, and each output is checked against its source outlines
and horizontal metrics. Source attribution and the exact Unicode scope are
recorded in sample-fonts.json.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from fontTools import subset
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def outline(font, glyph):
    glyphs = font.getGlyphSet()
    pen = DecomposingRecordingPen(glyphs)
    glyphs[glyph].draw(pen)
    return pen.value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--builds', type=Path, default=ROOT / 'output')
    parser.add_argument('--profile', type=Path, default=ROOT / 'profiles/n1-original')
    args = parser.parse_args()
    usage = defaultdict(set)
    rendered_usage = defaultdict(set)
    sources = {}
    inputs = {}
    for paper in ('paper-a', 'paper-b'):
        for booklet in ('written', 'listening'):
            name = f'{paper}-{booklet}'
            directory = args.builds / name
            report = json.loads((directory / 'render-report.json').read_text())
            registered = {font['id']: font for font in report['font_policy']['registered_fonts']}
            inputs[name] = {p.name: sha256(p) for p in sorted((directory / 'inputs').glob('*.yaml'))
                            if p.name != 'fonts.yaml'}
            for item in report['fallback_glyphs']:
                if item['font'] not in registered:
                    raise ValueError('Input must be a full-font build, not an already bundled subset build')
                font = registered[item['font']]
                face = font['source_face']
                if not face:
                    raise ValueError('Sample subsets require an exact source face mapping')
                if face in sources and sources[face]['sha256'] != font['sha256']:
                    raise ValueError(f'Conflicting source files for {face}')
                sources[face] = font
                usage[face].update(map(ord, item['text']))
                rendered_usage[face].update(map(ord, item['text']))
            composition = json.loads((directory / 'composition-font-usage.json').read_text())
            for fid, codepoints in composition['fonts'].items():
                if fid not in registered:
                    continue
                font = registered[fid]
                face = font['source_face']
                if not face:
                    raise ValueError('Composition subsets require an exact source face mapping')
                sources[face] = font
                usage[face].update(codepoints)
    records = {}
    provenance = {}
    for index, face in enumerate(sorted(usage), 1):
        fid = f'SF{index:03d}'
        source = Path(sources[face]['source'])
        if sha256(source) != sources[face]['sha256']:
            raise ValueError(f'Source font changed: {source.name}')
        rel = Path('fonts/samples') / f'{face}-sample.otf'
        target = args.profile / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with TTFont(source) as font:
            source_cmap = font.getBestCmap()
            wanted = usage[face] | {cp for cp in (0x20, 0x3000) if cp in source_cmap}
            if not wanted <= source_cmap.keys():
                raise ValueError(f'Missing requested source glyphs: {face}')
            options = subset.Options()
            options.recalc_timestamp = False
            options.layout_features = []
            # No automatic alternates: scope is the sample Unicode glyphs,
            # their dependencies, .notdef, and available space glyphs only.
            subsetter = subset.Subsetter(options=options)
            subsetter.populate(unicodes=wanted)
            subsetter.subset(font)
            font.save(target)
        with TTFont(source) as original, TTFont(target) as compact:
            oc = original.getBestCmap()
            cc = compact.getBestCmap()
            assert set(cc) == wanted
            assert original['head'].unitsPerEm == compact['head'].unitsPerEm
            for cp in sorted(wanted):
                assert original['hmtx'][oc[cp]] == compact['hmtx'][cc[cp]], (face, cp, 'metrics')
                assert outline(original, oc[cp]) == outline(compact, cc[cp]), (face, cp, 'outline')
            count = len(compact.getGlyphOrder())
            assert count < len(original.getGlyphOrder()) // 4, 'Refusing to package a near-full font'
            family, weight = sources[face]['role'].rsplit('_', 1)
            records[fid] = {
                'file': rel.as_posix(), 'name': sources[face]['font_name'],
                'source_face': face, 'family': 'fallback', 'fallback_family': family,
                'bold': weight == 'bold', 'section': '', 'priority': -50,
                'font_role': sources[face]['role'], 'bundled_sample': True,
                'user_supplied': False, 'sha256': sha256(target),
            }
            provenance[fid] = {
                'source_filename': source.name, 'source_sha256': sha256(source),
                'source_postscript_name': sources[face]['font_name'],
                'source_face': face, 'source_glyph_count': len(original.getGlyphOrder()),
                'sample_unicode_count': len(usage[face]), 'packaged_unicode_count': len(cc),
                'rendered_unicode_count': len(rendered_usage[face]),
                'measurement_only_unicode_codepoints': [f'U+{cp:04X}' for cp in sorted(usage[face] - rendered_usage[face])],
                'packaged_glyph_count': count, 'packaged_bytes': target.stat().st_size,
                'unicode_codepoints': [f'U+{cp:04X}' for cp in sorted(cc)],
                'sample_characters': ''.join(map(chr, sorted(usage[face]))),
                'outlines_and_horizontal_metrics_match_source': True,
                'source_is_historical_pdf_subset': False,
            }
    result = {'schema_version': 1, 'description': 'Only extra glyphs used by the shipped A/B samples. '
              'Derived from matching locally supplied modern full fonts; these are not historical PDF '
              'font programs and are not complete fonts. No alternate typeface is used.',
              'fonts': records, 'provenance': provenance, 'sample_input_sha256': inputs}
    (args.profile / 'sample-fonts.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'PASS', 'fonts': provenance}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
