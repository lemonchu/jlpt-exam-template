"""Listening components generated from a body grid and typographic measures.

The instruction measure is independent of the much wider answer panel.  A
first-line indent displaces a line; it does not change the number of cells in
that line.  This distinction is what lets one specification cover short and
long instructions without embedding their original line endings.

This mixin is used only by the experimental rule renderer.  Coordinates here
are component dimensions and baseline offsets, never page/item lookups.
"""
from dataclasses import dataclass, replace
import re

from geometry import metric, require_number
from inline import measure, parse


@dataclass(frozen=True)
class ListeningStyle:
    """Lengths in bp, relative to the current component or text baseline."""

    instruction_cells: int = 43
    memo_instruction_cells: int = 41
    label_size: float = 20
    number_advance: float = 18
    label_ruby_gap: float = 18.8077
    heading_size: float = 36
    heading_baseline: float = 34.0712
    heading_ruby_baseline: float = .2312
    instruction_top: float = 51.204
    after_instruction: float = 21.606
    memo_measure: float = 486.310325

    def instruction_measure(self, kind, cell, available, indent, cells=None):
        count = cells if cells is not None else (
            self.memo_instruction_cells if kind == 'listening_memo'
            else self.instruction_cells
        )
        return min(count * cell, available - indent)


LISTENING_STYLE = ListeningStyle()


def instruction_chunks(atoms, width):
    """Keep short kana continuations readable without a word dictionary.

    Ruby already makes annotated words indivisible.  Unannotated hiragana
    would otherwise break at every character, including halfway through a
    short connective or kana-only word.  Keep each such run together, but let
    a grammatical particle immediately following a kanji remain with it.

    This is an orthographic heuristic, not morphological analysis.  A kana
    run wider than the line falls back to ordinary character breaking.
    """
    def kana(atom):
        return (not atom.ruby and not atom.underline and not atom.annotation
                and re.fullmatch('[ぁ-ゖ]+', atom.text) is not None)

    result = []
    index = 0
    while index < len(atoms):
        atom = atoms[index]
        if not kana(atom):
            result.append(atom)
            index += 1
            continue
        chunk = [atom]
        index += 1
        while index < len(atoms) and kana(atoms[index]) and atoms[index].bold == atom.bold:
            chunk.append(atoms[index])
            index += 1
        previous = result[-1].text[-1:] if result else ''
        after_kanji = bool(previous and '\u3400' <= previous <= '\u9fff')
        if after_kanji and chunk[0].text in 'がをにはへとでもの' and len(chunk) > 1:
            result.append(chunk.pop(0))
        extent = sum(part.width for part in chunk)
        if extent > width:
            result.extend(chunk)
        else:
            result.append(replace(chunk[0], text=''.join(part.text for part in chunk), width=extent))
    return result


class ListeningRules:
    """Compose listening headings and labels without measured fragments."""

    def listen_label(self, label, baseline, x=None):
        style = LISTENING_STYLE
        size = style.label_size
        x = self.left if x is None else x
        for atom in measure(parse(label, True), self.catalog, size, self.section):
            start = x
            for char in atom.text:
                number = char.isascii() and char.isdigit()
                role = 'listening-number' if char.isdigit() or char == '番' else 'heading'
                self.glyph(char, size, x, baseline, True, role=role,
                           hscale=.8 if number else 1)
                x += (style.number_advance if number else
                      self.catalog.width(char, size, True, self.section, role))
            ruby_x = start
            for char in atom.ruby:
                self.glyph(char, size / 2, ruby_x, baseline - style.label_ruby_gap,
                           True, role='ruby-heading')
                ruby_x += self.catalog.width(char, size / 2, True,
                                             self.section, 'ruby-heading')

    def listening_heading_plan(self, group, config):
        """Measure a heading without emitting ink or changing the page cursor.

        Heights describe an unbroken heading. The first chunk keeps the title
        with one instruction row; longer instructions may paginate after that.
        All positions remain relative to the eventual drawing origin.
        """
        if config.get('heading_layout', 'stacked') != 'stacked':
            raise ValueError('Listening heading_layout must be stacked')
        style = LISTENING_STYLE
        heading_size = metric(config, 'heading_size', style.heading_size)
        size = metric(config, 'instruction_font_size', 11.3)
        leading = metric(config, 'instruction_line_height', 25.47)
        available = metric(config, 'instruction_width', self.width)
        if available > self.width + 1e-6:
            raise ValueError('Listening instruction width must fit inside the body width')
        cell = self.catalog.width('あ', size, True, self.section)
        indent = size * (11.31 / 11.3)
        cells = (metric(config, 'instruction_cells', style.instruction_cells)
                 if 'instruction_cells' in config else None)
        width = style.instruction_measure(group['kind'], cell, available, indent, cells)
        if width <= 0:
            raise ValueError('Listening instruction width must leave room after its indent')
        scale = heading_size / style.heading_size
        title = config.get('title', group.get('title', ''))
        title_glyphs, title_width = self._listening_title_glyphs(title, heading_size)
        if title_width > self.width + 1e-6:
            raise ValueError('Listening title must fit inside the body width')
        rows = self._listening_instruction_plan(group.get('instruction', ''), width, indent, size)
        instruction_offset = style.instruction_top * scale
        after = 0 if group['kind'] == 'listening_memo' else style.after_instruction
        title_baseline = style.heading_baseline * scale
        ruby_baseline = style.heading_ruby_baseline * scale
        # The source title's ruby rises above the body cursor. A same-page
        # group can reserve this logical glyph extent without changing the
        # original top-of-page anchor or guessing a fixed listening gap.
        top_overhang = max([0] + [glyph_size - (ruby_baseline if role == 'ruby-heading'
                                               else title_baseline)
                                 for _, glyph_size, _, role, _ in title_glyphs])
        return {
            'title_glyphs': title_glyphs,
            'title_baseline': title_baseline,
            'ruby_baseline': ruby_baseline,
            'instruction_offset': instruction_offset,
            'rows': rows, 'size': size, 'leading': leading, 'after': after,
            'height': instruction_offset + len(rows) * leading + after,
            'first_chunk_height': instruction_offset + (leading if rows else after),
            'top_overhang': top_overhang,
        }

    def draw_listening_heading(self, plan):
        """Draw one measured plan at the current cursor, allowing long text to flow."""
        self.ensure(plan['first_chunk_height'])
        origin = self.y
        self._draw_listening_title(plan['title_glyphs'],
                                   origin + plan['title_baseline'],
                                   origin + plan['ruby_baseline'])
        self.y = origin + plan['instruction_offset']
        self._draw_listening_instruction_rows(plan['rows'], plan['size'], plan['leading'])
        if plan['after']:
            self.gap(plan['after'])

    def _listening_heading(self, group, config):
        self.draw_listening_heading(self.listening_heading_plan(group, config))

    def _listening_title_glyphs(self, title, size):
        glyphs = []
        x = 0
        for atom in parse(title, True):
            start = x
            for char in atom.text:
                glyphs.append((char, size, x, 'heading', 1))
                x += self.catalog.width(char, size, True, self.section, 'heading')
            if not atom.ruby:
                continue
            ruby_size = size / 2
            advances = [self.catalog.width(char, ruby_size, True, self.section, 'ruby-heading')
                        for char in atom.ruby]
            extent = sum(advances)
            hscale = min(1, (x - start) / extent) if extent else 1
            ruby_x = start + (x - start - extent * hscale) / 2
            for char, advance in zip(atom.ruby, advances):
                glyphs.append((char, ruby_size, ruby_x, 'ruby-heading', hscale))
                ruby_x += advance * hscale
        return glyphs, x

    def _draw_listening_title(self, glyphs, baseline, ruby_baseline):
        for char, size, x, role, hscale in glyphs:
            self.glyph(char, size, self.left + x,
                       ruby_baseline if role == 'ruby-heading' else baseline,
                       True, role=role, hscale=hscale)

    def _listening_instruction_plan(self, text, width, indent, size):
        result = []
        for paragraph in (part for part in str(text).splitlines() if part.strip()):
            atoms = measure(parse(paragraph, True), self.catalog, size, self.section)
            rows = self.hanging_lines(paragraph, size, width, width, True,
                                      atoms=instruction_chunks(atoms, width))
            for index, atoms in enumerate(rows):
                result.append({'atoms': atoms, 'inset': indent if index == 0 else 0})
        return result

    def _draw_listening_instruction_rows(self, rows, size, leading):
        for row in rows:
            self.ensure(leading)
            self.line(row['atoms'], self.left + row['inset'], self.y, size)
            self.y += leading

    def _listening_instruction(self, text, width, tracking=0, size=11.3, leading=25.47):
        """Track the opening row's base cells, leaving each ruby reading intact."""
        size = require_number(size, 'Listening instruction size must be a finite positive number')
        leading = require_number(leading, 'Listening instruction line height must be a finite positive number')
        width = require_number(width, 'Listening instruction width must be a finite positive number')
        tracking = require_number(tracking, 'Listening instruction tracking must be a finite signed number')
        if size <= 0 or leading <= 0:
            raise ValueError('Listening instruction size and line height must be positive')
        indent = size * (11.31 / 11.3)
        if width <= indent or width > self.width + 1e-6:
            raise ValueError('Listening instruction width must fit inside the body width')
        for paragraph in (part for part in str(text).splitlines() if part.strip()):
            atoms = measure(parse(paragraph, True), self.catalog, size, self.section)
            tracked = [replace(atom, width=atom.width + tracking * self.tracking_units(atom))
                       for atom in atoms]
            if any(atom.width <= 0 for atom in tracked):
                raise ValueError('Listening instruction tracking must leave positive advances')
            # Find only the first break using tracked widths. An unrestricted
            # temporary continuation avoids imposing that tracking on later rows.
            split = self.hanging_lines(paragraph, size, width - indent + tracking,
                                       max(width, sum(atom.width for atom in tracked)), True, atoms=tracked)
            natural = [[replace(atom, width=atom.width - tracking * self.tracking_units(atom))
                        for atom in row] for row in split]
            remainder = [atom for row in natural[1:] for atom in row]
            rows = natural[:1]
            if remainder:
                rows.extend(self.hanging_lines('', size, width, width, True, atoms=remainder))
            for index, row in enumerate(rows):
                self.ensure(leading)
                self.line(row, self.left + (indent if index == 0 else 0), self.y, size,
                          tracking=tracking if index == 0 else 0)
                self.y += leading

    def _listening_memo(self, block):
        # The source's memo title is centered in the instruction field, not
        # the wider answer panel. Narrow/custom fields still get a true center.
        if 'memo_center_offset' in self.gc:
            return super()._listening_memo(block)
        config = self.gc
        self.gc = {**config, 'memo_center_offset':
                   min(self.width, LISTENING_STYLE.memo_measure) / 2}
        try:
            return super()._listening_memo(block)
        finally:
            self.gc = config
