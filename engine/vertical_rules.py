"""Vertical quotations: logical cells, bibliographic units and relative frames."""
from dataclasses import dataclass, replace
from math import floor

from component_layout import _VERTICAL_FORMS
from geometry import metric
from inline import measure, parse, plain
from reading_rules import citation_parts, justified_gaps, punctuation_gaps


@dataclass(frozen=True)
class VerticalStyle:
    body_cells: int = 25
    citation_cells: int = 30
    body_size: float = 11.3
    citation_size: float = 9.2
    column_pitch: float = 24.05996
    citation_pitch: float = 16.98044
    citation_transition: float = 23.01024
    before: float = 12.6422
    after: float = 6.744
    top_baseline: float = 26.798
    column_slack: float = 1.04575
    bottom_padding: float = 6.853
    citation_bottom: float = 13.416
    inset_right: float = 24.039
    inset_left: float = 12.364


STYLE = VerticalStyle()


def pack_citation(text, cells):
    """Pack author/title/publisher units before splitting an oversized unit."""
    columns, column = [], []
    used = 0
    for paragraph in text.splitlines() or ['']:
        for part in citation_parts(paragraph):
            atoms = parse(part)
            count = sum(len(atom.text) for atom in atoms)
            if column and used + count > cells:
                columns.append(column)
                column, used = [], 0
            for atom in atoms:
                if len(atom.text) > cells:
                    if atom.ruby:
                        raise ValueError('An indivisible citation ruby exceeds the vertical column')
                    pieces = [replace(atom, text=char,
                                      annotation=atom.annotation if index == 0 else '')
                              for index, char in enumerate(atom.text)]
                else:
                    pieces = [atom]
                for piece in pieces:
                    if column and used + len(piece.text) > cells:
                        columns.append(column)
                        column, used = [], 0
                    column.append(piece)
                    used += len(piece.text)
        if column:
            columns.append(column)
            column, used = [], 0
    return columns


def vertical_gaps(atoms, measure_width, size, final):
    gaps = punctuation_gaps(atoms, size)
    if final:
        return gaps
    if not any(gaps):
        return justified_gaps(atoms, measure_width, size)
    # In a vertical cell grid, adjacent punctuation shares bearings, but does
    # not admit an extra character. Redistribute that space over the column.
    slack = measure_width - sum(atom.width for atom in atoms) - sum(gaps)
    if slack <= 0 or not gaps:
        return gaps
    quantum = size * .0009
    common = floor(slack / (len(gaps) * quantum)) * quantum
    result = [gap + common for gap in gaps]
    result[-1] += slack - common * len(gaps)
    return result


class VerticalRules:
    def vertical_plan(self, block):
        size = metric(self.gc, 'vertical_font_size', STYLE.body_size)
        scale = size / STYLE.body_size
        raw_cells = self.gc.get('vertical_cells', STYLE.body_cells)
        if isinstance(raw_cells, bool) or not isinstance(raw_cells, int) or raw_cells < 2:
            raise ValueError('vertical_cells must be an integer of at least two')
        cell = self.catalog.width('文', size, False, self.section)
        extent = raw_cells * cell + STYLE.column_slack * scale
        height = STYLE.top_baseline * scale + extent + STYLE.bottom_padding * scale
        columns = []
        for child in block.get('blocks', []):
            if child.get('type') not in ('vertical', 'paragraph'):
                raise ValueError('Vertical quotation supports vertical text and paragraph citations only')
            text = child.get('text', '')
            if child.get('type') != 'vertical':
                small = STYLE.citation_size * scale
                for part in pack_citation(text, STYLE.citation_cells):
                    atoms = measure(part, self.catalog, small, self.section)
                    columns.append(dict(size=small, atoms=atoms, citation=True, indent=0, gaps=[]))
                continue
            for paragraph in text.splitlines() or ['']:
                atoms = measure(parse(paragraph), self.catalog, size, self.section)
                # An opening quote begins at the column edge. Other paragraphs
                # indent one logical cell; continuation columns do not indent.
                indent = 0 if plain(paragraph).startswith(('「', '『')) else cell
                logical = [replace(atom, width=len(atom.text) * cell) for atom in atoms]
                rows = self.hanging_lines(paragraph, size, raw_cells * cell - indent,
                                          raw_cells * cell, atoms=logical)
                for index, row in enumerate(rows):
                    inset = indent if index == 0 else 0
                    columns.append(dict(size=size, atoms=row, citation=False, indent=inset,
                                        gaps=vertical_gaps(row, extent - inset, size,
                                                           index + 1 == len(rows))))
        distances = []
        for previous, current in zip(columns, columns[1:]):
            distance = (STYLE.citation_pitch if previous['citation'] and current['citation']
                        else STYLE.citation_transition if current['citation']
                        else STYLE.column_pitch)
            distances.append(distance * scale)
        width = (STYLE.inset_left + STYLE.inset_right) * scale + sum(distances)
        return dict(columns=columns, distances=distances, width=width, height=height,
                    scale=scale, before=STYLE.before * scale, after=STYLE.after * scale)

    def estimate_block(self, block, width=None):
        if block.get('type') == 'box' and self._has_vertical(block):
            plan = self.vertical_plan(block)
            return plan['before'] + plan['height'] + plan['after']
        return super().estimate_block(block, width)

    def vertical_box(self, block, x, width):
        plan = self.vertical_plan(block)
        if plan['width'] > width + 1e-6:
            raise ValueError('Vertical quotation exceeds the page width; shorten it or use a reference asset')
        offset = x - self.left
        self.ensure(plan['before'] + plan['height'] + plan['after'])
        left = self.left + offset + (width - plan['width']) / 2
        top = self.y + plan['before']
        self.rect(left, top, plan['width'], plan['height'])
        xx = left + plan['width'] - STYLE.inset_right * plan['scale']
        for index, column in enumerate(plan['columns']):
            if index:
                xx -= plan['distances'][index - 1]
            atoms, size = column['atoms'], column['size']
            if column['citation']:
                total = sum(len(atom.text) for atom in atoms)
                advance = self.catalog.width('文', size, False, self.section)
                yy = top + plan['height'] - STYLE.citation_bottom * plan['scale'] - (total - 1) * advance
            else:
                advance = self.catalog.width('文', size, False, self.section)
                yy = top + STYLE.top_baseline * plan['scale'] + column['indent']
            for atom_index, atom in enumerate(atoms):
                for char_index, char in enumerate(atom.text):
                    drawn = _VERTICAL_FORMS.get(char, char)
                    self.glyph(drawn, size, xx, yy, atom.bold,
                               rotation=-90 if char in 'ー―—〜～' else 0,
                               semantic_char=char if drawn != char else None)
                    if char_index == 0 and atom.ruby:
                        reading_step = len(atom.text) * advance / len(atom.ruby)
                        for ruby_index, kana in enumerate(atom.ruby):
                            self.glyph(kana, size / 2, xx + size * 1.02,
                                       yy - size * .44 + ruby_index * reading_step, atom.bold)
                    if atom.underline:
                        self.rule(xx + size * 1.1, yy - size * .9,
                                  xx + size * 1.1, yy + size * .1)
                    yy += advance
                if atom_index < len(column['gaps']):
                    yy += column['gaps'][atom_index]
        self.y = top + plan['height'] + plan['after']
        self._last_was_note = self._last_note_wrapped = False
        self._last_material_kind = 'vertical_box'
