#!/usr/bin/env python3
"""Compare freshly built exact A booklets with their visual examples."""
import hashlib
import sys
from pathlib import Path

import fitz

ROOT=Path(__file__).resolve().parents[1]
PAPERS=('paper-a-written','paper-a-listening')


def page_hashes(path):
    with fitz.open(path) as document:
        return [hashlib.sha256(page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False).samples).hexdigest()
                for page in document]


def main():
    failures=[]
    for paper in PAPERS:
        actual=ROOT/'output'/f'N1-{paper}.pdf'
        expected=ROOT/'examples'/f'N1-{paper}.pdf'
        if not actual.is_file():
            failures.append(f'{paper}: build output is missing')
            continue
        current=page_hashes(actual);golden=page_hashes(expected)
        changed=[index for index,(left,right) in enumerate(zip(current,golden),1) if left!=right]
        changed.extend(range(min(len(current),len(golden))+1,max(len(current),len(golden))+1))
        if changed:failures.append(f'{paper}: changed pages {changed}')
        else:print(f'{paper}: {len(current)} pages match')
    if failures:
        print('\n'.join(failures),file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
