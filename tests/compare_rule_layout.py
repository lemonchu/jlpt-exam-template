#!/usr/bin/env python3
"""Quantify a generated PDF against a golden PDF without scoring white space.

The raster score counts visibly changed pixels, normalized by golden ink.
Matched-glyph positions are a secondary diagnostic, not proof of text equality.
Neither score is an assertion that the original typesetter has been recovered.
"""
from argparse import ArgumentParser
from difflib import SequenceMatcher
import json
from math import isfinite
from pathlib import Path
from statistics import median

import fitz


def percentile(values, fraction):
    if not values:
        return None
    return sorted(values)[min(len(values) - 1, int((len(values) - 1) * fraction))]


def base_glyphs(page, clip):
    glyphs = []
    for block in page.get_text('rawdict')['blocks']:
        for line in block.get('lines', []):
            for span in line['spans']:
                if not 9 <= span['size'] <= 22:
                    continue
                for glyph in span['chars']:
                    char = glyph['c']
                    x, y = glyph['origin']
                    if char.isspace() or not clip.contains(fitz.Point(x, y)):
                        continue
                    glyphs.append((char, x, y))
    # The measured PDF may store entire paragraphs in one run, whereas the
    # generated one stores glyphs; compare their visual reading order.
    return sorted(glyphs, key=lambda glyph: (round(glyph[2]), glyph[1]))


def glyph_metrics(expected, actual, clip):
    left, right = base_glyphs(expected, clip), base_glyphs(actual, clip)
    matcher = SequenceMatcher(None, [glyph[0] for glyph in left],
                              [glyph[0] for glyph in right], autojunk=False)
    differences = []
    for first, second, count in matcher.get_matching_blocks():
        differences.extend((abs(left[first + i][1] - right[second + i][1]),
                            abs(left[first + i][2] - right[second + i][2]))
                           for i in range(count))
    distances = [max(dx, dy) for dx, dy in differences]
    return {
        'golden_glyphs': len(left), 'generated_glyphs': len(right),
        'aligned_glyphs': len(differences),
        'within_0_1bp': sum(distance <= .1 for distance in distances),
        'median_max_axis_bp': round(median(distances), 5) if distances else None,
        'p95_max_axis_bp': (round(percentile(distances, .95), 5) if distances else None),
    }


def compare(expected, actual, *, scale=2, threshold=16, skip_leading=0, excluded_pages=()):
    if not isfinite(scale) or scale <= 0:
        raise ValueError('Raster scale must be finite and positive')
    if not 0 <= threshold <= 255 or skip_leading < 0:
        raise ValueError('Threshold must be 0..255 and skip_leading nonnegative')
    excluded_pages = set(excluded_pages)
    if any(not isinstance(page, int) or page < 1 for page in excluded_pages):
        raise ValueError('Excluded page numbers must be positive integers')
    pages = []
    with fitz.open(expected) as golden, fitz.open(actual) as generated:
        for index in range(min(len(golden), len(generated))):
            left, right = golden[index], generated[index]
            same_size = left.rect == right.rect
            if not same_size:
                raise ValueError(f'Page {index + 1} has different dimensions: '
                                 f'{left.rect} vs {right.rect}; raster comparison is not meaningful')
            # Exclude page-edge blank area and footer, but retain instructions,
            # sidebars and all body material. Cover pages remain reported.
            clip = fitz.Rect(25, 40, left.rect.width - 25, left.rect.height - 50)
            settings = dict(matrix=fitz.Matrix(scale, scale), clip=clip,
                            colorspace=fitz.csGRAY, alpha=False)
            a, b = left.get_pixmap(**settings), right.get_pixmap(**settings)
            first, second = a.samples, b.samples
            if (a.width, a.height, len(first)) != (b.width, b.height, len(second)):
                raise ValueError(f'Page {index + 1} produced incompatible raster dimensions')
            pixels = sum(abs(x - y) > threshold for x, y in zip(first, second))
            ink = sum(value < 240 for value in first)
            pages.append({
                'page': index + 1,
                'included': index >= skip_leading and index + 1 not in excluded_pages,
                'same_page_size': same_size,
                'changed_pixels': pixels, 'golden_ink_pixels': ink,
                'changed_per_golden_ink': round(pixels / max(1, ink), 6),
                **glyph_metrics(left, right, clip),
            })
        selected = [page for page in pages if page['included']]
        total_ink = sum(page['golden_ink_pixels'] for page in selected)
        changed = sum(page['changed_pixels'] for page in selected)
        return {
            'golden': str(expected), 'generated': str(actual),
            'golden_pages': len(golden), 'generated_pages': len(generated),
            'same_page_count': len(golden) == len(generated),
            'raster_scale': scale, 'gray_threshold': threshold,
            'skip_leading': skip_leading,
            'excluded_pages': sorted(excluded_pages),
            'changed_pixels': changed, 'golden_ink_pixels': total_ink,
            'changed_per_golden_ink': round(changed / max(1, total_ink), 6),
            'pages': pages,
        }


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('golden', type=Path)
    parser.add_argument('generated', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--scale', type=float, default=2)
    parser.add_argument('--threshold', type=int, default=16)
    parser.add_argument('--skip-leading', type=int, default=2)
    parser.add_argument('--exclude-page', type=int, action='append', default=[],
                        help='Exclude a physical page from totals, but still report its metrics (repeatable)')
    args = parser.parse_args(argv)
    try:
        result = compare(args.golden, args.generated, scale=args.scale,
                         threshold=args.threshold, skip_leading=args.skip_leading,
                         excluded_pages=args.exclude_page)
    except ValueError as error:
        parser.error(str(error))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print('Pages:', result['golden_pages'], 'golden /', result['generated_pages'], 'generated')
    print('Changed pixels / golden ink:', result['changed_pixels'], '/', result['golden_ink_pixels'])
    print('page  changed/ink   aligned  <=0.1bp  median(bp)   p95(bp)')
    for page in result['pages']:
        if page['included']:
            print(f"{page['page']:4} {page['changed_per_golden_ink']:12.3%} "
                  f"{page['aligned_glyphs']:8} {page['within_0_1bp']:8} "
                  f"{str(page['median_max_axis_bp']):>11} {str(page['p95_max_axis_bp']):>10}")
    return 0 if result['same_page_count'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
