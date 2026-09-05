#!/usr/bin/env python3
"""Check or repair the original font subsets; never fetch or substitute a face.

The repository bundles these subsets. To repair missing resources, supply a
previously prepared project or matching first-edition PDFs. Full fonts are
optional local additions and are never downloaded by this tool.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

import fitz
from fontTools.cffLib import CFFFontSet
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.psCharStrings import T2CharString
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont, newTable

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'profiles' / 'n1-original'


def outline_hash(font, record):
    glyph_set = font.getGlyphSet()
    payload = []
    for name in sorted(g['glyph'] for g in record['glyphs']):
        if name not in glyph_set:
            raise ValueError(f'Missing original glyph {name}')
        pen = DecomposingRecordingPen(glyph_set)
        glyph_set[name].draw(pen)
        payload.append([name, pen.value])
    return hashlib.sha256(json.dumps(payload, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def validate(path, record, spec):
    if not path.is_file():
        raise ValueError(f'Missing font: {path}')
    # Previously prepared resources can be checked without parsing any outlines.
    if hashlib.sha256(path.read_bytes()).hexdigest() == spec['file_sha256']:
        return
    with TTFont(path) as font:
        if font['head'].unitsPerEm != spec['units_per_em']:
            raise ValueError(f'{path.name}: units-per-em differ from the original')
        if font.getBestCmap() != {int(k): v for k, v in spec['cmap'].items()}:
            raise ValueError(f'{path.name}: character mappings differ from the original')
        if font['hmtx'].metrics != {k: tuple(v) for k, v in spec['hmetrics'].items()}:
            raise ValueError(f'{path.name}: advance widths or side bearings differ from the original')
        if outline_hash(font, record) != spec['outline_sha256']:
            raise ValueError(f'{path.name}: glyph outlines differ from the original; no substitute is accepted')


def original_name(name):
    name = re.sub(r'^[A-Z]{6}\+', '', name)
    return re.sub(r'-Identity-[HV]$', '', name)


def wrap_cff(raw, record, spec):
    """Add Unicode/OpenType tables around original CFF charstrings and subroutines.

    The only added glyph is an empty space used by the original prepared profile.
    Existing CFF glyph programs and hinting are retained, not redrawn or scaled.
    """
    builder = FontBuilder(spec['units_per_em'], isTTF=False)
    builder.setupGlyphOrder(spec['glyph_order'])
    cff = CFFFontSet()
    cff.decompile(io.BytesIO(raw), builder.font)
    if len(cff.fontNames) != 1:
        raise ValueError('Expected one embedded CFF font')
    top = cff.topDictIndex[0]
    existing = set(top.charset)
    expected = {g['glyph'] for g in record['glyphs']}
    if existing != expected:
        raise ValueError('Embedded glyph set does not match the measured profile')
    # Add the blank glyph required by the wrapper while retaining the complete
    # original indexed charstrings, FDArray, and local/global subroutines.
    for name in spec['glyph_order']:
        if name in existing:
            continue
        if name not in ('space', 'cid00001'):
            raise ValueError(f'Unexpected missing wrapper glyph: {name}')
        private = top.FDArray[0].Private if hasattr(top, 'FDArray') else top.Private
        width = spec['hmetrics'][name][0]
        charstring = T2CharString(program=[width - private.nominalWidthX, 'endchar'],
                                 private=private, globalSubrs=cff.GlobalSubrs)
        charstrings = top.CharStrings
        charstrings.charStrings[name] = len(charstrings.charStringsIndex)
        charstrings.charStringsIndex.append(charstring)
        top.charset.append(name)
        if hasattr(top, 'FDSelect'):
            top.FDSelect.gidArray.append(0)
    if top.charset != spec['glyph_order']:
        raise ValueError('Original glyph order differs from the profile')
    # Consistent unique wrapper names avoid font-cache collisions across papers.
    cff.fontNames = [spec['ps_name']]
    top.FullName = spec['ps_name']
    top.FamilyName = spec['family_name']
    builder.font['CFF '] = newTable('CFF ')
    builder.font['CFF '].cff = cff
    builder.setupCharacterMap({int(k): v for k, v in spec['cmap'].items()})
    builder.setupHorizontalMetrics({k: tuple(v) for k, v in spec['hmetrics'].items()})
    builder.setupHorizontalHeader(ascent=spec['ascent'], descent=spec['descent'])
    builder.setupNameTable({'familyName': spec['family_name'], 'styleName': 'Regular',
                           'uniqueFontIdentifier': spec['ps_name'], 'fullName': spec['ps_name'],
                           'psName': spec['ps_name'], 'version': 'Version 1.000'})
    builder.setupOS2(sTypoAscender=spec['ascent'], sTypoDescender=spec['descent'],
                    usWinAscent=max(0, spec['ascent']), usWinDescent=max(0, -spec['descent']),
                    usWeightClass=spec['weight'], fsType=spec['fs_type'])
    builder.setupPost()
    if outline_hash(builder.font, record) != spec['outline_sha256']:
        raise ValueError('Embedded outlines differ from the measured source PDF')
    return builder.font


def pdf_candidates(path):
    found = {}
    with fitz.open(path) as document:
        seen = set()
        for page in document:
            for info in page.get_fonts(full=True):
                xref = info[0]
                if xref in seen:
                    continue
                seen.add(xref)
                name, extension, _kind, raw = document.extract_font(xref)
                if extension not in ('cff', 'cid') or not raw:
                    continue
                found.setdefault(original_name(name), []).append(raw)
    return found


def source_profile(path):
    choices = [path / 'profiles' / 'n1-original', path]
    for candidate in choices:
        if (candidate / 'font-catalog.json').is_file():
            return candidate
    raise ValueError('--from-project must point to the old project root or its profiles/n1-original directory')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--from-project', type=Path, help='Previously prepared private project or profile directory')
    source.add_argument('--pdf-dir', type=Path, help='Matching first-edition N1V/G/R/L PDFs; image-only second edition is unsuitable')
    source.add_argument('--check', action='store_true', help='Validate installed original profile fonts')
    parser.add_argument('--sections', default='V,G,R,L', help='Comma-separated sections (default: V,G,R,L)')
    parser.add_argument('--destination', type=Path, default=PROFILE, help='Destination profile directory (normally leave unchanged)')
    args = parser.parse_args()
    sections = args.sections.split(',')
    if not sections or any(s not in 'VGRL' or len(s) != 1 for s in sections) or len(set(sections)) != len(sections):
        parser.error('--sections must contain distinct values from V,G,R,L')
    catalog = json.loads((PROFILE / 'font-catalog.json').read_text())['fonts']
    specifications = json.loads((PROFILE / 'font-reconstruction.json').read_text())['fonts']
    selected = {fid: rec for fid, rec in catalog.items() if rec['section'] in sections}
    if args.check:
        for fid, record in selected.items():
            validate(args.destination / record['file'], record, specifications[fid])
        print(f'PASS: {len(selected)} original profile fonts have the expected mappings, metrics and outlines.')
        return
    old = source_profile(args.from_project.resolve()) if args.from_project else None
    embedded = {}
    if args.pdf_dir:
        for section in sections:
            names = [f'N1{section}.pdf'] + (['N1L(1).pdf'] if section == 'L' else [])
            path = next((args.pdf_dir / name for name in names if (args.pdf_dir / name).is_file()), None)
            if path is None:
                raise ValueError(f'Missing original PDF: {args.pdf_dir / names[0]}')
            embedded[section] = pdf_candidates(path)
    # Validate every selected font before changing the destination.
    with tempfile.TemporaryDirectory(prefix='n1-original-fonts-') as temporary:
        staged = Path(temporary)
        for fid, record in selected.items():
            target = staged / record['file']
            target.parent.mkdir(parents=True, exist_ok=True)
            if old:
                original = old / record['file']
                validate(original, record, specifications[fid])
                shutil.copyfile(original, target)
            else:
                reasons = []
                for raw in embedded[record['section']].get(record['name'], []):
                    try:
                        font = wrap_cff(raw, record, specifications[fid])
                        font.save(target)
                        font.close()
                        validate(target, record, specifications[fid])
                        break
                    except (ValueError, KeyError, AssertionError) as exc:
                        reasons.append(str(exc))
                else:
                    detail = '; '.join(dict.fromkeys(reasons)) or 'matching embedded CFF font not found'
                    raise ValueError(f'{fid} {record["name"]}: {detail}. Supply the matching first-edition PDF or use --from-project.')
        for record in selected.values():
            destination = args.destination / record['file']
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(staged / record['file'], destination)
    print(f'Prepared and verified {len(selected)} original profile fonts in {args.destination.resolve()}.')
    print('These local font files are ignored by Git. Configure the complete original-family fonts separately for new characters.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError) as exc:
        print(f'Font preparation failed: {exc}', file=sys.stderr)
        sys.exit(1)
