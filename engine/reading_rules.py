"""Relative reading-material rules for the experimental composition path.

The A specimen supplies typography, not content identities or page coordinates.
Paragraphs occupy a baseline grid; fitting a row tests its ink, not the empty
leading below it. Editorial roles are explicit ``rule_style`` metadata so that
quoted prose need not be guessed from its first character.
"""
from dataclasses import dataclass, replace
from math import ceil, floor
import re

from geometry import CLOZE_BOX, metric
from inline import Atom, measure, parse, plain, REFERENCE_BOX_RE
from rule_typography import MaterialNumber, material_number_atoms


RIGID_PUNCTUATION = frozenset('、。，．・：；？！「」『』（）()[]｛｝【】〈〉《》〔〕')


@dataclass
class MaterialLatin(Atom):
    """An embedded Western word owns quarter-em CJK separation."""


@dataclass
class MaterialColon(Atom):
    """Japanese colon spacing around the source font's raised ASCII colon."""


@dataclass
class MaterialDash(Atom):
    """An uninterrupted editorial dash is a vector, not a font-specific glyph."""


def punctuation_gaps(atoms, size):
    """Adjacent Japanese punctuation shares the half-cell of blank bearing."""
    close = '、。，．）」』】〉》'
    brackets = '（「『【〈《）」』】〉》、。，．'
    half_cell = size * (11.31017 / 11.3) / 2
    result = []
    for left, right in zip(atoms, atoms[1:]):
        gap = 0.0
        if left.text and right.text:
            if (left.text[-1] in close
                    and right.text[0] in brackets
                    and not REFERENCE_BOX_RE.fullmatch(left.text)):
                gap = -half_cell
            elif ((isinstance(right, MaterialLatin) and left.text[-1] in RIGID_PUNCTUATION)
                  or (isinstance(left, MaterialLatin) and right.text[0] in RIGID_PUNCTUATION)):
                gap = -size / 4
        result.append(gap)
    return result


def justified_gaps(atoms, width, size, *, hanging=True):
    """Distribute Japanese line slack in small, right-to-left increments.

    Punctuation keeps its natural surrounding space. A's expanded lines use
    0.0159 em increments, with one boundary absorbing the fractional remainder.
    This policy works for any text and line width; it does not consult A data.
    Multi-character ruby/Latin atoms remain indivisible at this layer.
    """
    gaps = punctuation_gaps(atoms, size)
    natural = sum(atom.width for atom in atoms) + sum(gaps)
    if (hanging and natural > width + 0.02 and atoms
            and atoms[-1].text in '、。' and not atoms[-1].underline):
        natural -= atoms[-1].width
    slack = width - natural
    eligible = [index for index, (left, right) in enumerate(zip(atoms, atoms[1:]))
                if left.text and right.text
                and not left.text[-1].isspace() and not right.text[0].isspace()
                and left.text[-1] not in RIGID_PUNCTUATION
                and right.text[0] not in RIGID_PUNCTUATION
                and not isinstance(left, (MaterialNumber, MaterialLatin))
                and not isinstance(right, (MaterialNumber, MaterialLatin))]
    if slack <= 0.02 or not eligible:
        return gaps
    quantum = size * 0.0159
    common = floor(slack / (len(eligible) * quantum)) * quantum
    for index in eligible:
        gaps[index] = common
    remainder = slack - len(eligible) * common
    for index in reversed(eligible):
        extra = min(quantum, max(0.0, remainder))
        gaps[index] += extra
        remainder -= extra
    return gaps


def kana_compressed_gaps(atoms, width, size, *, maximum_em=.04):
    """Tighten kana clusters, then return spare space to ordinary boundaries.

    Consecutive kana contract internally; their first character stays attached
    to a preceding kanji's cell. A lone kana between kanji contracts at its
    leading boundary. This keeps dense kanji runs readable and gives wrapped
    reading answers a consistent texture. The caller retains its original
    whole-row fit budget; this function only chooses where that space goes.
    """
    def kana(char):
        return bool(char and ('\u3041' <= char <= '\u3096' or '\u30a1' <= char <= '\u30fa'
                              or char == 'ー'))
    def kanji(char):
        return bool(char and ('\u3400' <= char <= '\u9fff' or '\U00020000' <= char <= '\U0003134f'))
    def latin(char):
        return bool(char and (char.isascii() and char.isalpha() or 'Ａ' <= char <= 'Ｚ'
                              or 'ａ' <= char <= 'ｚ'))

    gaps = punctuation_gaps(atoms, size)
    natural = sum(atom.width for atom in atoms) + sum(gaps)
    if (natural > width + .02 and atoms and atoms[-1].text in '、。'
            and not atoms[-1].underline):
        natural -= atoms[-1].width
    deficit = natural - width
    if deficit <= .02:
        return None
    selected = []
    closing = '、。）」』】〉》'
    for index, (left, right) in enumerate(zip(atoms, atoms[1:])):
        if (gaps[index] or left.ruby or right.ruby or left.underline or right.underline
                or not left.text or len(right.text) != 1):
            continue
        a, b = left.text[-1], right.text
        following = atoms[index + 2].text[:1] if index + 2 < len(atoms) else ''
        if ((kana(a) and (kana(b) or b in closing))
                or (kana(b) and latin(a))
                or (kanji(a) and kana(b) and not kana(following) and following not in closing)):
            selected.append(index)
    if not selected:
        return None
    quantum = .03 * size / 11.3
    # Source PDF cell rounding can leave a few hundredths beyond the nominal
    # measure. Keep the common quantum, with one boundary absorbing that tail.
    amount = ceil(max(0, deficit - .05 * size / 11.3) / (len(selected) * quantum)) * quantum
    final_amount = amount + max(0.0, deficit - len(selected) * amount)
    if final_amount > maximum_em * size + 1e-6:
        return None
    for index in selected:
        gaps[index] -= amount
    spare = len(selected) * amount - deficit
    if spare < 0:
        gaps[selected[-1]] += spare
        spare = 0
    adjustable = [index for index, (left, right) in enumerate(zip(atoms, atoms[1:]))
                  if not gaps[index] and left.text and right.text
                  and not left.text[-1].isspace() and not right.text[0].isspace()
                  and left.text[-1] not in RIGID_PUNCTUATION
                  and right.text[0] not in RIGID_PUNCTUATION
                  and not isinstance(left, MaterialNumber) and not isinstance(right, MaterialNumber)]
    if spare > .02 and not adjustable:
        return None
    # Compensation uses the same right-to-left priority as expanded body rows,
    # but never loosens a boundary that was selected for kana contraction.
    for index in reversed(adjustable):
        extra = min(size * .0159, max(0.0, spare))
        gaps[index] += extra
        spare -= extra
    if spare > .02:
        return None
    return gaps


def row_ink_height(atoms, size):
    """Conservative ink below the row top, including below-word notes."""
    below_baseline = size * 0.25
    if any(getattr(atom, 'annotation', '') for atom in atoms):
        below_baseline = max(below_baseline, 6.98 + 6.4 * 0.25)
    return size + below_baseline


def citation_parts(text):
    """Author, quoted title, and publisher are meaningful wrapping units."""
    if '\n' in text:
        return text.splitlines()
    website = re.search(r'[＜<]https?://', text)
    if website and website.start():
        return [text[:website.start()].rstrip(), text[website.start():]]
    start = text.find('『')
    end = text.rfind('』')
    if 0 < start < end:
        return [part for part in (text[:start], text[start:end + 1], text[end + 1:]) if part]
    return [text]


@dataclass(frozen=True)
class MaterialFrame:
    """Insets and spacing relative to the article's current flow position."""
    outset_left: float
    outset_right: float
    inset_left: float
    inset_right: float
    before: float
    top: float
    bottom: float
    after: float
    stroke: float


@dataclass
class CompactReference(Atom):
    """A parenthesized subitem label occupies one Japanese text cell."""
    number: str = ''


def cloze_frame(config):
    # The thick frame's two edges have independently measured optical offsets.
    # Its text returns to the ordinary body grid on both sides.
    left = metric(config, 'material_box_outset', 11.91, allow_zero=True)
    right = metric(config, 'material_box_outset', 11.30, allow_zero=True)
    return MaterialFrame(
        left, right,
        metric(config, 'material_box_padding', left, allow_zero=True),
        metric(config, 'material_box_padding', right, allow_zero=True),
        1.31732,
        metric(config, 'material_box_top_padding', 24.15268, allow_zero=True),
        metric(config, 'material_box_bottom_padding', 28.917, allow_zero=True),
        5.105, metric(config, 'material_box_stroke', 1.71),
    )


def notice_frame(config):
    """An administrative notice has its own inset body and footer space."""
    return MaterialFrame(.55, .583, 23.17, 11.893,
                         12.73128, 19.8789, 10.51644, 13.539, .33)


class ReadingRules:
    """Mixin placed before ComponentLayout in the rules-only renderer."""

    def paragraph_indent(self, block, bold, align, width):
        style = block.get('rule_style')
        if style in ('dialogue', 'quotation', 'continuation') and 'indent' not in block:
            return 0.0
        if style == 'contact' and 'indent' not in block:
            return 11.31
        if style == 'contact_detail' and 'indent' not in block:
            return 0.0
        indent = super().paragraph_indent(block, bold, align, width)
        if (self._is_cloze() and getattr(self, '_cloze_material_depth', 0)
                and 'indent' not in block and REFERENCE_BOX_RE.match(block.get('text', ''))):
            # The first frame's outside stroke, not its surrounding blank cell,
            # aligns with the paragraph's usual first-character column.
            indent = max(0.0, indent - CLOZE_BOX.margin - .33 / 2)
        return indent

    def paragraph_format(self, block):
        if getattr(self, '_rule_material_style', None) == 'notice' and block.get('type') == 'heading':
            return 12.8, 49.79964, True
        return super().paragraph_format(block)

    def paragraph_spec(self, block, width):
        spec = list(super().paragraph_spec(block, width))
        if getattr(self, '_rule_material_style', None) == 'notice':
            if block.get('type') == 'heading':
                spec[-1] = -.17972
            elif block.get('rule_style') == 'contact':
                spec[-1] = self.leading
            elif block.get('rule_style') == 'contact_detail':
                spec[5] = 'left'
        return tuple(spec)

    def _material_geometry(self, block, x, width):
        """Use the same semantic insets while measuring and while drawing."""
        style = getattr(self, '_rule_material_style', None)
        if block.get('rule_style') == 'contact_detail':
            inset = getattr(self, '_contact_detail_inset', 0.0)
            x, width = x + inset, width - inset
        elif (style == 'notice' and block.get('type') == 'paragraph'
              and block.get('align', 'left') == 'left' and not block.get('rule_style')):
            width -= 11.31
        elif style == 'notice' and block.get('type') == 'heading':
            x += .4116
        elif (self._is_cloze() and block.get('style') == 'small'
              and block.get('align') == 'right' and getattr(self, '_last_material_kind', None) == 'box'):
            frame = cloze_frame(self.gc)
            # A source following a thick article frame hangs optically outside
            # the frame edge, rather than aligning with the inset body text.
            width += frame.outset_right + frame.stroke * .75
        return x, width

    def _remember_contact(self, block, width):
        if block.get('rule_style') != 'contact':
            return
        text = block.get('text', '')
        self._contact_detail_inset = 0.0
        if '〒' not in plain(text):
            return
        size, _, bold, _, _, align, indent, _ = self.paragraph_spec(block, width)
        rows = self._reading_rows(text, width, size, bold, align, indent)
        for index, row in enumerate(rows):
            postal = next((i for i, atom in enumerate(row) if atom.text == '〒'), None)
            if postal is None:
                continue
            inset = indent if index == 0 else 0
            gaps = (justified_gaps(row, width - inset, size) if index + 1 < len(rows)
                    else punctuation_gaps(row, size))
            prefix_width = sum(atom.width for atom in row[:postal]) + sum(gaps[:postal])
            self._contact_detail_inset = max(0.0, inset + prefix_width - size / 2)
            break

    def block(self, block, x=None, width=None):
        previous = getattr(self, '_rule_reading_block', None)
        if self._uses_reading_spacing() and block.get('type') in ('paragraph', 'heading'):
            self._rule_reading_block = block
        x, width = self._material_geometry(block, self.left if x is None else x,
                                          self.width if width is None else width)
        relative_x = x - self.left
        try:
            result = super().block(block, x, width)
            self._remember_contact(block, width)
            if getattr(self, '_rule_material_style', None) == 'notice' and block.get('type') == 'heading':
                size, leading, _ = self.paragraph_format(block)
                baseline = self._notice_heading_baseline
                start = self.left + relative_x - .4116 - 23.17
                heading_rows = self._reading_rows(block.get('text', ''), width, size, True, 'left', 0)
                measure_width = max((sum(atom.width for atom in row) for row in heading_rows), default=0)
                line_width = min(width + 35.063,
                                 measure_width + 61.73712)
                self.rule(start, baseline + 5.7371, start + line_width, baseline + 5.7371,
                          2.82, '.57647 .58431 .59608')
            return result
        finally:
            self._rule_reading_block = previous

    def _material_atoms(self, text, size, bold, small=False):
        # Route the printable ASCII colon before font measurement. Its semantic
        # fullwidth spelling must not require an unused glyph in a sample subset.
        source = [MaterialColon(**{**vars(atom), 'text': ':'}) if atom.text == '：' and not atom.ruby
                  else atom for atom in parse(text, bold)]
        measured = measure(source, self.catalog, size, self.section)
        measured = [replace(atom, text='：', width=size * (1.0298 if atom.bold else .9874))
                    if isinstance(atom, MaterialColon) else atom for atom in measured]
        measured = material_number_atoms(measured, self.catalog, size, self.section)
        result = []
        for index, atom in enumerate(measured):
            if re.fullmatch('[―—]+', atom.text) and not atom.ruby and not atom.annotation:
                if (result and isinstance(result[-1], MaterialDash)
                        and (result[-1].bold, result[-1].underline) == (atom.bold, atom.underline)):
                    result[-1].text += atom.text
                    result[-1].width += atom.width
                    continue
                atom = MaterialDash(**vars(atom))
            elif not small and re.fullmatch('[A-Za-z]+', atom.text) and not atom.ruby:
                atom = MaterialLatin(**{**vars(atom), 'width': atom.width + size / 2})
            elif atom.text == ' ' and 0 < index < len(measured) - 1:
                left, right = measured[index - 1].text[-1:], measured[index + 1].text[:1]
                # English word spaces stay half-em. Only the separator between
                # a Western author/abbreviation and Japanese prose is quarter-em.
                if ((left.isascii() and left.isalpha() and right and ord(right) >= 0x3000)
                        or (right.isascii() and right.isalpha() and left and ord(left) >= 0x3000)):
                    atom = replace(atom, width=size / 4)
            result.append(atom)
        return result

    def _reading_rows(self, text, width, size, bold, align, indent):
        block = getattr(self, '_rule_reading_block', None) or {}
        small = block.get('style') == 'small'
        def atoms_for(part):
            return self._material_atoms(part, size, bold, small)
        if small and align == 'right':
            rows = self.hanging_lines(text, size, width, width, bold, atoms=atoms_for(text))
            if len(rows) > 1:
                parts = citation_parts(text)
                if len(parts) > 1:
                    rows = [row for part in parts
                            for row in self.hanging_lines(part, size, width, width, bold, atoms=atoms_for(part))]
            return rows
        return self.hanging_lines(text, size, width - indent, width, bold,
                                  hanging_punctuation=not small, atoms=atoms_for(text))

    def _paragraph_grid_leading(self, block, leading):
        if getattr(self, '_rule_material_style', None) == 'notice' and block.get('type') == 'heading':
            return min(leading, self.leading)
        return leading

    def paragraph(self, text, x=None, width=None, size=None, leading=None,
                  bold=False, align='left', gap=0, indent=0, reserve_after=0):
        block = getattr(self, '_rule_reading_block', None)
        if not block:
            return super().paragraph(text, x, width, size, leading, bold, align,
                                     gap, indent, reserve_after)
        x = self.left if x is None else x
        width = self.width if width is None else width
        size = size or self.fs
        leading = leading or self.leading
        grid_leading = self._paragraph_grid_leading(block, leading)
        after_title = leading - grid_leading
        origin = self.left
        rows = self._reading_rows(text, width, size, bold, align, indent)
        for index, row in enumerate(rows):
            remaining = len(rows) - index
            need = row_ink_height(row, size)
            if after_title:
                need = max(need, size + 7.2)  # Under-title rule has visible ink below the ordinary descender.
            if reserve_after and remaining <= 2:
                need = ((remaining - 1) * grid_leading + after_title
                        + row_ink_height(rows[-1], size) + reserve_after)
            self.ensure(need if need <= self.usable else row_ink_height(row, size))
            inset = indent if index == 0 else 0
            xx = x + self.left - origin + inset
            available = width - inset
            if (block.get('style') == 'small' and align == 'right' and len(rows) > 1
                    and row and row[-1].text in '）」』】〉》'):
                available += self.catalog.width('　', size, bold, self.section) / 2
            justify = (index + 1 < len(rows) and align == 'left'
                       and block.get('style') != 'small')
            gaps = justified_gaps(row, available, size) if justify else punctuation_gaps(row, size)
            if gaps and any(gaps) and hasattr(self, 'line_gaps'):
                extent = sum(atom.width for atom in row) + sum(gaps)
                if align in ('center', 'right'):
                    xx += (available - extent) / (2 if align == 'center' else 1)
                self.line_gaps(row, xx, self.y, size, gaps)
            else:
                self.line(row, xx, self.y, size, align, available)
            if after_title:
                self._notice_heading_baseline = self.y + size
            self.y += grid_leading
        self.gap(after_title)
        self.gap(gap)

    def estimate_block(self, block, width=None):
        width = self.width if width is None else width
        if self._uses_reading_spacing() and block.get('type') in ('paragraph', 'heading'):
            previous = getattr(self, '_rule_reading_block', None)
            self._rule_reading_block = block
            try:
                _, width = self._material_geometry(block, self.left, width)
                size, leading, bold, _, _, align, indent, before = self.paragraph_spec(block, width)
                text = self.paragraph_body_text(block)
                grid_leading = self._paragraph_grid_leading(block, leading)
                height = (len(self._reading_rows(text, width, size, bold, align, indent)) * grid_leading
                          + leading - grid_leading + before)
                self._remember_contact(block, width)
                return height
            finally:
                self._rule_reading_block = previous
        if (block.get('type') == 'box' and (self._is_cloze() or block.get('rule_style') == 'notice')
                and not self._has_vertical(block)):
            frame = cloze_frame(self.gc) if self._is_cloze() else notice_frame(self.gc)
            inner = width + frame.outset_left + frame.outset_right - frame.inset_left - frame.inset_right
            depth = getattr(self, '_cloze_material_depth', 0)
            previous_style = getattr(self, '_rule_material_style', None)
            previous_contact = getattr(self, '_contact_detail_inset', 0.0)
            self._contact_detail_inset = 0.0
            self._rule_material_style = block.get('rule_style')
            if self._is_cloze():
                self._cloze_material_depth = depth + 1
            try:
                return (frame.before + frame.top + frame.bottom + frame.after
                        + self.reading_sequence_height(block.get('blocks', []), inner))
            finally:
                self._cloze_material_depth = depth
                self._rule_material_style = previous_style
                self._contact_detail_inset = previous_contact
        return super().estimate_block(block, width)

    def reading_sequence_height(self, blocks, width):
        previous = getattr(self, '_contact_detail_inset', 0.0)
        try:
            return super().reading_sequence_height(blocks, width)
        finally:
            self._contact_detail_inset = previous

    def reading_box(self, block, x, width):
        if (not self._is_cloze() and block.get('rule_style') != 'notice') or self._has_vertical(block):
            return super().reading_box(block, x, width)
        frame = cloze_frame(self.gc) if self._is_cloze() else notice_frame(self.gc)
        offset = x - self.left - frame.outset_left
        needed = self.estimate_block(block, width)
        keep = needed if needed <= self.usable else frame.before + frame.top + 2 * self.leading
        self.ensure(self.opening_keep_height(block, keep, width))
        self.gap(frame.before)
        outer_width = width + frame.outset_left + frame.outset_right
        first, start_y = len(self.pages) - 1, self.y
        self.y += frame.top
        depth = getattr(self, '_cloze_material_depth', 0)
        previous_style = getattr(self, '_rule_material_style', None)
        previous_contact = getattr(self, '_contact_detail_inset', 0.0)
        self._contact_detail_inset = 0.0
        self._rule_material_style = block.get('rule_style')
        if self._is_cloze():
            self._cloze_material_depth = depth + 1
        try:
            self.blocks(block.get('blocks', []), self.left + offset + frame.inset_left,
                        outer_width - frame.inset_left - frame.inset_right,
                        tail_reserve=frame.bottom)
        finally:
            self._cloze_material_depth = depth
            self._rule_material_style = previous_style
            self._contact_detail_inset = previous_contact
        self.y += frame.bottom
        self.frame_segments(first, start_y, offset, outer_width, frame.stroke)
        self.gap(frame.after)
        self._last_was_note = self._last_note_wrapped = False
        self._last_material_kind = 'box'

    def written_instruction_atoms(self, text, size=11.3, bold=True):
        if self.section != 'R':
            return measure(parse(text, bold), self.catalog, size, self.section)
        atoms = []
        for part in re.split(r'([（(][１-９1-9][）)])', text):
            match = re.fullmatch(r'[（(]([１-９1-9])[）)]', part)
            if match:
                number = str(int(match[1]))
                atoms.append(CompactReference(part, bold=bold,
                                              width=self.catalog.width('１', size, bold, self.section),
                                              number=number))
            else:
                atoms.extend(measure(parse(part, bold), self.catalog, size, self.section))
        return atoms

    def written_instruction(self, atoms, x, top, width, final):
        if self.section == 'R' or self._is_cloze():
            size = metric(self.gc, 'instruction_font_size', 11.3)
            gaps = punctuation_gaps(atoms, size) if final else justified_gaps(atoms, width, size)
            if self.section == 'R' and not final:
                # Instructions may justify gently, but a short opening row
                # should not acquire the stretched texture of body prose.
                # The profile uses at most two ordinary spacing quanta here.
                maximum = metric(self.gc, 'instruction_max_positive_tracking',
                                 2 * .0159 * size, allow_zero=True)
                if max(gaps, default=0) > maximum + 1e-6:
                    gaps = punctuation_gaps(atoms, size)
            if any(gaps):
                return self.line_gaps(atoms, x, top, size, gaps)
            return self.line(atoms, x, top, size)
        return super().written_instruction(atoms, x, top, width, final)

    def tracking_units(self, atom):
        return 1 if isinstance(atom, CompactReference) else super().tracking_units(atom)

    def line_tracking(self, atoms, width, max_negative=0, rigid_blanks=False,
                      max_negative_blanks=None, hanging_punctuation=False):
        if getattr(self, '_rule_reading_block', None):
            size = self.paragraph_format(self._rule_reading_block)[0]
            width -= sum(punctuation_gaps(atoms, size))
        return super().line_tracking(atoms, width, max_negative, rigid_blanks,
                                     max_negative_blanks, hanging_punctuation)

    def line(self, atoms, x, top, size, align='left', width=None,
             color='0.13725,0.12157,0.12549', tracking=0, rigid_blanks=False, **kwargs):
        if not any(isinstance(atom, (CompactReference, MaterialColon, MaterialDash))
                   or (self._is_cloze() and REFERENCE_BOX_RE.fullmatch(atom.text)) for atom in atoms):
            return super().line(atoms, x, top, size, align, width, color,
                                tracking, rigid_blanks, **kwargs)
        extent = sum(atom.width for atom in atoms) + tracking * self.tracking_gaps(atoms, rigid_blanks)
        if width is not None and align in ('center', 'right'):
            x += (width - extent) / (2 if align == 'center' else 1)
        for index, atom in enumerate(atoms):
            if isinstance(atom, CompactReference):
                if self.page.get('_ink') != color:
                    self.emit({'type': 'ink', 'rgb': [float(value) for value in color.split(',')]})
                    self.page['_ink'] = color
                self.run_counter += 1
                run = f'composed-{self.run_counter:06}'
                self.emit({'type': 'run', 'run_id': run, 'font': 'R001',
                           'sx': size, 'sy': size, 'x': x, 'y': self.H - top - size,
                           'offsets': [0], 'slot_count': 1, 'shear': 0,
                           'forms': ['combined'], 'role': 'subitem-parentheses'})
                self.resolved[run] = {'glyphs': ['( )']}
                self.semantic_glyphs.append({'page_ref': id(self.page), 'char': '( )',
                                            'font': 'R001', 'size': size, 'x': x,
                                            'y': top + size, 'role': 'subitem-parentheses'})
                scale = size / 11.3
                self.glyph(chr(ord('０') + int(atom.number)), 10.6 * scale,
                           x + .36 * scale, top + size - .27294 * scale, True)
            elif isinstance(atom, MaterialColon):
                inset = size * (.3767 if atom.bold else .4007)
                self.glyph(':', size, x + inset, top + size - size * .1248, atom.bold, color)
                if atom.underline:
                    self.rule(x, top + size + 3, x + atom.width, top + size + 3, .33)
            elif isinstance(atom, MaterialDash):
                baseline = top + size
                self.rule(x - .03, baseline - size * .382, x + atom.width + .03,
                          baseline - size * .382, .42 if size < 10 else .33,
                          color.replace(',', ' '))
                if atom.underline:
                    self.rule(x, baseline + 3, x + atom.width, baseline + 3, .33)
            else:
                reference = REFERENCE_BOX_RE.fullmatch(atom.text)
                previous_shift = getattr(self, '_reference_label_shift', 0.0)
                if reference and self._is_cloze():
                    scale = size / CLOZE_BOX.body_size
                    last = (reference[1] + (reference[2] or ''))[-1]
                    role = 'question-number' if last.isdigit() else 'body'
                    final_width = self.catalog.width(last, CLOZE_BOX.label_size * scale,
                                                     False, self.section, role=role)
                    if last.isdigit():
                        final_width *= .8
                    final_advance = (CLOZE_BOX.digit_advance if last.isdigit()
                                     else CLOZE_BOX.suffix_advance) * scale
                    # Logical digit pitch is tighter than the full glyph cell.
                    # Center the visible label span, including its final cell.
                    self._reference_label_shift = (final_width - final_advance) / 2
                try:
                    super().line([atom], x, top, size, color=color, tracking=tracking,
                                 rigid_blanks=rigid_blanks, **kwargs)
                finally:
                    self._reference_label_shift = previous_shift
            x += atom.width + tracking * max(0, self.tracking_units(atom) - 1)
            if index + 1 < len(atoms):
                x += tracking

    def glyph(self, char, size, x, baseline, bold=False,
              color='0.13725,0.12157,0.12549', rotation=0, semantic_char=None, role=None, hscale=1):
        block = getattr(self, '_rule_reading_block', None) or {}
        if (role is None and getattr(self, '_rule_material_style', None) == 'notice'
                and block.get('type') == 'heading'):
            role = 'notice-heading'
        x -= getattr(self, '_reference_label_shift', 0.0)
        result = super().glyph(char, size, x, baseline, bold, color, rotation, semantic_char, role, hscale)
        if role == 'notice-heading':
            # Administrative-notice emphasis is an optically calibrated 15°
            # oblique, independent of whether a font supplies an italic face.
            self.page['commands'][-1]['shear'] = .26796875
        return result
