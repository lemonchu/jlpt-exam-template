#!/usr/bin/env python3
"""Check A's 60 choice prompts and 260 options against source row lengths.

The compact fixture stores only character counts per row; expected text comes
from current YAML. It was extracted from the source geometry before the old
engine was removed. Actual rows come from RuleLayout.choice_metrics.
Pass the same --fonts configuration used for a real build.

This is a diagnostic CLI, not a default unit test: missing fonts are errors,
never skipped checks or metric-only substitutions.
"""
from argparse import ArgumentParser
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build
from calibrated_renderer import GlyphError
from geometry import body_grid
from cover_templates import CoverTemplates
from rule_layout import RuleLayout
from rule_typography import RuleFonts
from semantic_bindings import chars_for, pointer

CHOICE_FIELD = re.compile(r'(?P<owner>.*)/(?P<field>prompt|options/[0-3])$')
EXPECTED_COUNTS = {'prompts': 60, 'options': 260}


def compact(text):
    """Compare row membership, ignoring optical spaces and colon glyph style."""
    return ''.join(char for char in text if not char.isspace()).replace(':', '：')


def source_rows(fields, content):
    """Split current semantic text using the independent source row lengths."""
    result = {}
    for field, lengths in fields.items():
        text = compact(''.join(chars_for(pointer(content, field), 'base')))
        if not lengths or any(type(length) is not int or length < 1 for length in lengths):
            raise ValueError(f'Invalid source row lengths: {field}')
        if len(text) != sum(lengths):
            raise ValueError(f'Source-row baseline no longer fits {field}: '
                             f'expected {sum(lengths)} characters, got {len(text)}')
        start = 0
        result[field] = []
        for length in lengths:
            result[field].append(text[start:start + length])
            start += length
    return result


def check(font_config=None):
    profile = ROOT / 'profiles/n1-original'
    reference = CoverTemplates(profile, ROOT / 'content/common/metadata.yaml')
    baseline = json.loads((ROOT / 'tests/fixtures/a-choice-rows.json').read_text(encoding='utf-8'))
    if baseline.get('schema_version') != 1:
        raise ValueError('Unsupported source-row baseline schema')
    catalog = RuleFonts(profile, font_config, ROOT)
    blueprint = build.load(ROOT / 'blueprints/written.yaml')
    defaults = build.load(ROOT / 'blueprints/components.yaml')['components']
    groups, _ = build.load_content(ROOT / 'content/paper-a')
    # Construction and choice_metrics do not write files. Stimuli are omitted
    # below because this diagnostic measures question fields, not page flow.
    layout = RuleLayout(catalog, blueprint, ROOT / 'resources', ROOT / 'tmp', reference)
    checked = dict.fromkeys(EXPECTED_COUNTS, 0)
    matched = dict.fromkeys(EXPECTED_COUNTS, 0)
    failures = []
    for entry in blueprint['groups']:
        group = groups[entry['id']]
        if group['kind'] == 'word_order':
            continue  # Its five slot-bearing prompts have separate tests.
        content = group
        expected = source_rows(baseline['groups'][group['id']], content)
        layout.section, layout.group = group['id'][0], group
        layout.gc = {**blueprint.get('group_defaults', {}),
                     **defaults.get(group['kind'], {}), **entry}
        _, layout.width = body_grid(layout.section).geometry(1, blueprint['page'])
        owners = sorted({CHOICE_FIELD.fullmatch(field)['owner'] for field in expected})
        for owner in owners:
            question = dict(pointer(content, owner))
            question.pop('stimulus', None)
            try:
                plan = layout.choice_metrics(question)
            except GlyphError as error:
                raise GlyphError(f'{owner}: {error}') from error
            actual_fields = [('prompt', plan['promptlines'])]
            actual_fields.extend((f'options/{index}', rows)
                                 for index, rows in enumerate(plan['oplines']))
            for suffix, rows in actual_fields:
                field = f'{owner}/{suffix}'
                if field not in expected:
                    continue  # Cloze answer sets have no prompt glyphs.
                kind = 'prompts' if suffix == 'prompt' else 'options'
                actual = [compact(''.join(atom.text for atom in row)) for row in rows]
                checked[kind] += 1
                if actual == expected[field]:
                    matched[kind] += 1
                else:
                    failures.append({'group': group['id'], 'field': field,
                                     'columns': plan['cols'],
                                     'expected_rows': expected[field], 'actual_rows': actual})
    return {
        'passed': checked == EXPECTED_COUNTS and not failures,
        'font_config': str(font_config) if font_config else None,
        'expected_counts': EXPECTED_COUNTS,
        'checked': checked, 'matched': matched, 'failures': failures,
    }


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--fonts', type=Path, help='Complete-font configuration used by build.py')
    parser.add_argument('--output', type=Path, help='Optional JSON diagnostic report')
    args = parser.parse_args(argv)
    try:
        result = check(args.fonts)
    except GlyphError as error:
        parser.error(f'{error}\nSupply --fonts with matching complete fonts; no fields were skipped.')
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for kind in EXPECTED_COUNTS:
        print(f"{kind}: {result['matched'][kind]}/{result['checked'][kind]} source rows match")
    if result['checked'] != EXPECTED_COUNTS:
        print(f'Coverage changed: expected {EXPECTED_COUNTS}', file=sys.stderr)
    for failure in result['failures']:
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
