#!/usr/bin/env python3
"""Check A's 60 choice prompts and 260 options against existing source rows.

Expected text is resolved from semantic bindings and the current A content;
the profile's run baselines determine only which glyphs shared a source row.
Actual rows come from RuleLayout.choice_metrics with the canonical blueprint.
No external PDF, copied golden-text fixture, XeLaTeX, or rendered output is
needed. Complete fonts may be required by strict production font routing;
pass the same --fonts configuration used for a real --rules build.

This is a diagnostic CLI, not a default unit test: missing fonts are errors,
never skipped checks or metric-only substitutions.
"""
from argparse import ArgumentParser
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build
from calibrated_renderer import GlyphError
from geometry import body_grid
from reference_components import ReferenceComponents
from rule_layout import RuleLayout
from rule_typography import RuleFonts
from semantic_bindings import pointer

CHOICE_FIELD = re.compile(r'(?P<owner>.*)/(?P<field>prompt|options/[0-3])#base$')
EXPECTED_COUNTS = {'prompts': 60, 'options': 260}


def compact(text):
    """Compare row membership, ignoring optical spaces and colon glyph style."""
    return ''.join(char for char in text if not char.isspace()).replace(':', '：')


def source_rows(reference, group):
    """Recover only choice-field row text from existing measured bindings."""
    commands = []
    for page in reference.components[group['id']]['pages']:
        source = reference.pages[(group['id'][0], page['source_page'])]
        commands.extend((page['source_page'], command) for command in source['commands']
                        if command['type'] == 'run'
                        and command['run_id'] in reference.bindings['runs'])
    resolved, _ = reference.resolve_runs(group, [command['run_id'] for _, command in commands])
    fields = defaultdict(lambda: defaultdict(list))
    for page, command in commands:
        run_id = command['run_id']
        for index, glyph in enumerate(reference.bindings['runs'][run_id]['glyphs']):
            targets = {ref['field'] for ref in glyph['refs'] if CHOICE_FIELD.fullmatch(ref['field'])}
            # Offsets are expressed before the run's horizontal scale.
            x = command['x'] + command['offsets'][index] * command['sx'] / command['sy']
            key = (page, round(-command['y'], 2))
            for field in targets:
                fields[field][key].append((x, resolved[run_id]['glyphs'][index]))

    result = {}
    for field, baselines in fields.items():
        rows = []
        for (page, baseline), glyphs in sorted(baselines.items()):
            # A's raised dialogue colon belongs to the adjacent body baseline,
            # not its own line. Normal body rows are over 19 bp apart.
            if rows and rows[-1][0] == page and abs(baseline - rows[-1][1]) < 2:
                rows[-1][2].extend(glyphs)
            else:
                rows.append((page, baseline, list(glyphs)))
        result[field] = [compact(''.join(char for _, char in sorted(glyphs, key=lambda g: g[0])))
                         for _, _, glyphs in rows]
    return result


def check(font_config=None):
    profile = ROOT / 'profiles/n1-original'
    reference = ReferenceComponents(profile, ROOT / 'content/common/metadata.yaml')
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
        expected = source_rows(reference, group)
        group_index = reference.components[group['id']]['group_index']
        content = {'groups': [None] * group_index + [group]}
        layout.section, layout.group = group['id'][0], group
        layout.gc = {**blueprint.get('group_defaults', {}),
                     **defaults.get(group['kind'], {}), **entry}
        _, layout.width = body_grid(layout.section).geometry(1, blueprint['page'])
        owners = sorted({CHOICE_FIELD.fullmatch(field)['owner'] for field in expected})
        for owner in owners:
            question = dict(pointer(content, owner.split(':', 1)[1]))
            question.pop('stimulus', None)
            try:
                plan = layout.choice_metrics(question)
            except GlyphError as error:
                raise GlyphError(f'{owner}: {error}') from error
            actual_fields = [('prompt', plan['promptlines'])]
            actual_fields.extend((f'options/{index}', rows)
                                 for index, rows in enumerate(plan['oplines']))
            for suffix, rows in actual_fields:
                field = f'{owner}/{suffix}#base'
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
