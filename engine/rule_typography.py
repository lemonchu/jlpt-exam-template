"""Relative typography for the experimental rule composer.

No calibration scene or semantic binding is read here. The small metric table
describes type sizes, not pages or particular words. Per-kanji ruby alignment
is linguistic content: ``｜商品《しょう|ひん》`` supplies its two readings.
"""
from dataclasses import dataclass, replace
from math import ceil
import re

from component_fonts import ComponentFonts
from inline import Atom


# The PDF's displayed type sizes round the underlying typesetter's advances.
# Keeping these advances avoids accumulating several pixels across a line.
# Listening's 14.2 bp body size uses the profile-wide median advance; its
# specimen has small per-line export variations, which are not replayed here.
_CJK_ADVANCES = {
    5.6: 5.61008, 6.4: 6.3872, 7.1: 7.10994, 9.2: 9.21012,
    10.0: 9.99, 11.3: 11.31017, 12.8: 12.81024, 14.2: 14.19290,
    18.0: 18.0, 20.0: 20.01, 36.0: 36.0,
}
@dataclass
class MaterialNumber(Atom):
    """Fullwidth numeral shapes placed in half-em logical cells."""


def number_advance(char, size):
    return size * .5892 if char in ':：' else 1.5 * size - _CJK_ADVANCES.get(round(size, 6), size)


def material_number_atoms(atoms, catalog, size, section):
    """Compact multi-digit quantities without substituting ASCII glyphs.

    Single Japanese digits retain their full cell. Numeric separators can join
    a postal code, date or time, but styling and annotation boundaries remain
    explicit and ordinary prose never changes.
    """
    result = []
    index = 0
    while index < len(atoms):
        first = atoms[index]
        if first.ruby or first.annotation or not re.fullmatch('[０-９]+', first.text):
            result.append(first)
            index += 1
            continue
        end = index + 1
        while end < len(atoms):
            atom = atoms[end]
            same_style = (atom.bold, atom.underline) == (first.bold, first.underline)
            if not same_style or atom.ruby or atom.annotation:
                break
            if re.fullmatch('[０-９]+', atom.text):
                end += 1
            elif (atom.text in '－‐−–—-：:．.' and end + 1 < len(atoms)
                  and not atoms[end + 1].ruby and not atoms[end + 1].annotation
                  and (atoms[end + 1].bold, atoms[end + 1].underline) == (first.bold, first.underline)
                  and re.fullmatch('[０-９]+', atoms[end + 1].text)):
                end += 1
            else:
                break
        original = ''.join(atom.text for atom in atoms[index:end])
        if sum('０' <= char <= '９' for char in original) < 2:
            result.extend(atoms[index:end])
        else:
            advance = sum(number_advance(char, size) for char in original)
            result.append(MaterialNumber(original, bold=first.bold, underline=first.underline,
                                         width=advance))
        index = end
    return result


class RuleFonts(ComponentFonts):
    """The same font routing with calibrated advances for standard type sizes."""

    def preferred(self, bold, section, role=None):
        if role == 'notice-heading':
            return 'R030'
        guide_faces = {'guide-brand': 'R035', 'guide-heading': 'R032',
                       'guide-number': 'R027', 'guide-colon': 'R034'}
        return guide_faces.get(role) or super().preferred(bold, section, role)

    def width(self, char, size, bold=False, section='', role=None):
        width = super().width(char, size, bold, section, role)
        if ord(char) >= 0x3000 and not char.isspace():
            advance = _CJK_ADVANCES.get(round(size, 6))
            if advance is not None:
                width += advance - size - size * .0009
        return width

    def prepare_atoms(self, atoms):
        """Explicit mono-ruby may break between kanji, retaining first-note ownership."""
        for atom in atoms:
            parts = getattr(atom, 'ruby_parts', ())
            if len(parts) > 1:
                for index, (char, reading) in enumerate(zip(atom.text, parts)):
                    yield replace(atom, text=char, ruby=reading, ruby_parts=(),
                                  annotation=atom.annotation if index == 0 else '',
                                  annotation_span=atom.annotation_span if index == 0 else 0)
            else:
                yield atom

    def atom_width(self, atom, base, size, section=''):
        """Keep ruby readable by expanding long-reading cells in half-em steps."""
        if not atom.ruby:
            return base
        ruby_size = 5.6 if abs(size - 11.3) < 1e-6 else size / 2
        required = len(atom.ruby) * ruby_size * .67
        # Three-kana .67 ruby can overrun its nominal cell by export rounding.
        if required <= base + size * .01:
            return base
        quantum = 5.61008 if abs(size - 11.3) < 1e-6 else 7.08012 if abs(size - 14.2) < 1e-6 else size / 2
        return base + ceil((required - base - size * .01) / quantum) * quantum


@dataclass(frozen=True)
class RubyGlyph:
    char: str
    x: float
    size: float
    above: float
    hscale: float = 1.0


def mono_ruby(reading, cell_width, size, *, bold=False, available_width=None):
    """Place one reading inside one base cell; x is relative to that cell.

    One kana is centered, two fill the cell, and longer readings condense
    horizontally. The 0.67 three-kana scale is a source typesetting setting;
    larger readings use the same rule with a scale derived from their length.
    """
    if not reading:
        return []
    count = len(reading)
    if abs(size - 11.3) < 1e-6:
        ruby_size = 5.6
        above = 10.6223 if count > 2 else 10.6225 if bold else 10.626
        one = 2.85
        start = .06 if bold else .03
        pitch = 5.57984 if bold else 5.61008
        condensed_pitch = 5.5524 if bold else 5.5972
    elif abs(size - 14.2) < 1e-6:
        ruby_size, above = 7.1, 13.3367
        one, start, pitch, condensed_pitch = 3.54, 0.0, 7.08012, 7.07444
    else:
        ruby_size, above = size / 2, size * .94
        one, start, pitch, condensed_pitch = (cell_width - ruby_size) / 2, 0.0, ruby_size, ruby_size
    if abs(size - 11.3) < 1e-6 or abs(size - 14.2) < 1e-6:
        # The optical offsets above describe a Japanese fullwidth cell. An
        # annotated Latin letter is narrower but shares the same cell center.
        center_shift = (cell_width - _CJK_ADVANCES[size]) / 2
        one += center_shift
        start += center_shift
    if count == 1:
        return [RubyGlyph(reading, one, ruby_size, above)]
    capacity = cell_width if available_width is None else available_width
    hscale = min(.67 if count > 2 else 1.0, round(capacity / (count * ruby_size), 2))
    # Nominal two-kana readings do not acquire rounding-induced compression.
    if count == 2:
        hscale = 1.0
    pitch = (condensed_pitch if count > 2 else pitch) * hscale
    if count > 3:
        start = (cell_width - ((count - 1) * pitch + ruby_size * hscale)) / 2
    return [RubyGlyph(char, start + index * pitch, ruby_size, above, hscale)
            for index, char in enumerate(reading)]


def ruby_layout(atom, glyph_widths, size, *, tracking=0, available_width=None):
    """Return ruby positions relative to the base text's first glyph.

    Explicit partitions follow each character even when line tracking changes.
    Unpartitioned compounds use evenly centered group ruby; no dictionary or
    guesses about a kanji's pronunciation are needed at rendering time.
    """
    if not atom.ruby:
        return []
    parts = getattr(atom, 'ruby_parts', ())
    if parts:
        if len(parts) != len(glyph_widths):
            raise ValueError('Ruby partitions must match the base character count')
        result = []
        cursor = 0.0
        for reading, cell in zip(parts, glyph_widths):
            result.extend(replace(glyph, x=glyph.x + cursor)
                          for glyph in mono_ruby(reading, cell, size, bold=atom.bold))
            cursor += cell + tracking
        return result
    if len(glyph_widths) == 1:
        return mono_ruby(atom.ruby, glyph_widths[0], size, bold=atom.bold,
                         available_width=available_width)
    base_width = sum(glyph_widths) + tracking * max(0, len(glyph_widths) - 1)
    width = base_width if available_width is None else available_width
    ruby_size = 5.6 if abs(size - 11.3) < 1e-6 else size / 2
    above = 10.626 if abs(size - 11.3) < 1e-6 else 13.3367 if abs(size - 14.2) < 1e-6 else size * .94
    step = width / len(atom.ruby)
    hscale = min(1.0, step / ruby_size)
    start = (step - ruby_size * hscale) / 2 - (width - base_width) / 2
    return [RubyGlyph(char, start + index * step, ruby_size, above, hscale)
            for index, char in enumerate(atom.ruby)]


class TypographyRules:
    """Add relative ruby and note placement to the common base-line renderer."""

    def tracking_units(self, atom):
        return 1 if isinstance(atom, MaterialNumber) else super().tracking_units(atom)

    def _draw_number(self, atom, x, top, size, color):
        cursor = x
        for char in atom.text:
            if char in ':：':
                self.glyph(':', size, cursor + size * .1565, top + size - size * .1248,
                           atom.bold, color)
            else:
                self.glyph(char, size, cursor - size / 4, top + size, atom.bold, color)
            cursor += number_advance(char, size)
        if atom.underline:
            self.rule(x, top + size + 3, x + atom.width, top + size + 3, .33)

    def line_gaps(self, atoms, x, top, size, gaps,
                  color='0.13725,0.12157,0.12549', *, tracking=0):
        """Draw a justified row with explicit extra spacing between intact atoms.

        The paragraph breaker owns gap priorities. Ruby and note clusters stay
        intact, and this method uses the same line renderer as ordinary rows.
        """
        if len(gaps) != max(0, len(atoms) - 1):
            raise ValueError('One spacing adjustment is required between each pair of atoms')
        for index, atom in enumerate(atoms):
            self.line([atom], x, top, size, color=color, tracking=tracking)
            x += atom.width + tracking * max(0, self.tracking_units(atom) - 1)
            if index < len(gaps):
                gap = gaps[index]
                if gap > 0 and atom.underline and atoms[index + 1].underline:
                    self.rule(x, top + size + 3, x + gap, top + size + 3, .33)
                x += gap

    def line(self, atoms, x, top, size, align='left', width=None,
             color='0.13725,0.12157,0.12549', tracking=0, rigid_blanks=False):
        if any(isinstance(atom, MaterialNumber) for atom in atoms):
            extent = sum(atom.width for atom in atoms) + tracking * self.tracking_gaps(atoms, rigid_blanks)
            if width is not None and align in ('center', 'right'):
                x += (width - extent) / (2 if align == 'center' else 1)
            previous_flexible = False
            for atom in atoms:
                flexible = not rigid_blanks or (not atom.underline and not atom.text.isspace())
                if flexible and previous_flexible:
                    x += tracking
                internal = tracking if flexible else 0
                if isinstance(atom, MaterialNumber):
                    self._draw_number(atom, x, top, size, color)
                else:
                    self.line([atom], x, top, size, color=color, tracking=internal,
                              rigid_blanks=rigid_blanks)
                x += atom.width + internal * max(0, self.tracking_units(atom) - 1)
                previous_flexible = flexible
            return
        if not any(atom.ruby or atom.annotation for atom in atoms):
            return super().line(atoms, x, top, size, align, width, color, tracking, rigid_blanks)
        # Keep the established base/box/underline implementation and its metrics.
        bare = [replace(atom, ruby='', annotation='') for atom in atoms]
        super().line(bare, x, top, size, align, width, color, tracking, rigid_blanks)
        line_width = sum(atom.width for atom in atoms) + tracking * self.tracking_gaps(atoms, rigid_blanks)
        if width is not None and align in ('center', 'right'):
            x += (width - line_width) / (2 if align == 'center' else 1)
        baseline = top + size
        cursor = x
        shift = 0.0
        previous_flexible = False
        for index, atom in enumerate(atoms):
            flexible = not rigid_blanks or (not atom.underline and not atom.text.isspace())
            if flexible and previous_flexible:
                shift += tracking
            origin = cursor + shift
            internal = tracking if flexible else 0.0
            gaps = max(0, self.tracking_units(atom) - 1)
            if atom.ruby:
                advances = [self.catalog.width(char, size, atom.bold, self.section) for char in atom.text]
                # An underlined star can reserve more width than its glyph.
                base_width = sum(advances) + internal * max(0, len(advances) - 1)
                base_x = origin + (atom.width + internal * gaps - base_width) / 2
                for glyph in ruby_layout(atom, advances, size, tracking=internal,
                                         available_width=atom.width + internal * gaps):
                    self.glyph(glyph.char, glyph.size, base_x + glyph.x,
                               baseline - glyph.above, atom.bold, color, hscale=glyph.hscale)
            if atom.annotation:
                scale = size / 11.3
                note_x = origin - 3.17 * scale
                note_size = 6.4 * scale
                for char in atom.annotation:
                    self.glyph(char, note_size, note_x, baseline + 6.9804 * scale, False, color)
                    note_x += self.catalog.width(char, note_size, False, self.section)
            cursor += atom.width
            if flexible:
                shift += tracking * gaps
            previous_flexible = flexible
