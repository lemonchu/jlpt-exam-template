"""Written-paper instructions and captioned figures on the shared body grid."""
from dataclasses import dataclass, replace
import re

from geometry import metric
from inline import Atom, CLOSE, measure, parse, plain


@dataclass(frozen=True)
class InstructionStyle:
    first_inset: float = 50.88
    rest_inset: float = 39.57
    minimum_tail_cells: float = 6
    after: float = 14.13
    first_line_quantum: float = .0159
    first_line_max_shrink: float = .0531
    enumeration_shrink: float = .3
    fit_allowance: float = .05


@dataclass
class InstructionEnumeration(Atom):
    """An answer-label list is one wrapping unit, not ordinary prose."""

    parts: tuple = ()


def instruction_enumerations(atoms):
    """Group plain digit/middle-dot lists without crossing annotation or style."""
    result = []
    index = 0

    def bare(atom, pattern, bold):
        return (re.fullmatch(pattern, atom.text) is not None and atom.bold == bold
                and not atom.ruby and not atom.annotation and not atom.underline)

    while index < len(atoms):
        first = atoms[index]
        end = index + 1
        if bare(first, '[１-９1-9]', first.bold):
            while (end + 1 < len(atoms) and bare(atoms[end], '・', first.bold)
                   and bare(atoms[end + 1], '[１-９1-9]', first.bold)):
                end += 2
        parts = atoms[index:end]
        result.append(InstructionEnumeration(''.join(atom.text for atom in parts),
                                             bold=first.bold, width=sum(atom.width for atom in parts),
                                             parts=tuple(parts)) if len(parts) > 1 else first)
        index = end
    return result


def expand_instruction_atoms(atoms):
    return [part for atom in atoms for part in
            (atom.parts if isinstance(atom, InstructionEnumeration) else (atom,))]


def balance_instruction_tail(rows, minimum_width):
    """Avoid an isolated short ending without storing specimen line breaks.

    Only the final two rows change. Ruby clusters stay indivisible, and closing
    punctuation carries the preceding character onto the final row.
    """
    rows = [list(row) for row in rows]
    if len(rows) < 2:
        return rows
    previous, last = rows[-2:]
    while len(previous) > 1 and sum(atom.width for atom in last) < minimum_width - .05:
        last.insert(0, previous.pop())
    while len(previous) > 1 and last and last[0].text[:1] in CLOSE:
        last.insert(0, previous.pop())
    return rows


class WrittenRules:
    instruction_style = InstructionStyle()

    def written_instruction_atoms(self, text, size=11.3, bold=True):
        return measure(parse(text, bold), self.catalog, size, self.section)

    def _instruction_first_row(self, atoms, size, width, tracking=0, compact=False):
        internal = -size * self.instruction_style.enumeration_shrink if compact else tracking
        measured = []
        for atom in atoms:
            extent = (atom.width + internal * (len(atom.parts) - 1) + tracking
                      if isinstance(atom, InstructionEnumeration)
                      else atom.width + tracking * self.tracking_units(atom))
            if extent <= 0:
                raise ValueError('Instruction contraction must leave positive advances')
            measured.append(replace(atom, width=extent))
        original = {id(copy): atom for copy, atom in zip(measured, atoms)}
        # Source glyph advances are rounded independently of the text field.
        available = width + tracking + self.instruction_style.fit_allowance
        oversized = next((index for index, atom in enumerate(measured)
                          if atom.width > available), None)
        if oversized == 0:
            return None
        if oversized is not None:
            measured = measured[:oversized]
        first = self.hanging_lines('', size, available,
                                   max(width, sum(atom.width for atom in measured)), True,
                                   hanging_punctuation=True, atoms=measured)[0]
        return [original[id(atom)] for atom in first]

    def reading_instruction_rows(self, atoms, size, first_width, rest_width, config):
        """Infer a bounded first-row policy, not the original editor's algorithm.

        The profile permits a small uniform first-row contraction. A numeric
        answer list can use compact spacing when that keeps the entire list on
        that row; continuations return to ordinary paragraph justification.
        """
        grouped = instruction_enumerations(atoms)
        hard_break = next((index for index, atom in enumerate(grouped) if atom.text == '\n'), len(grouped))
        opening = grouped[:hard_break]
        maximum = metric(config, 'instruction_first_line_max_negative_tracking',
                         size * self.instruction_style.first_line_max_shrink, allow_zero=True)
        normal = self._instruction_first_row(opening, size, first_width)
        selected, tracking, compact = normal, 0.0, False
        if maximum:
            gentle = min(maximum, size * self.instruction_style.first_line_quantum)
            candidate = self._instruction_first_row(opening, size, first_width, -gentle)
            if candidate is not None and (normal is None or
                    len(expand_instruction_atoms(candidate)) > len(expand_instruction_atoms(normal))):
                selected, tracking = candidate, -gentle
            candidate = self._instruction_first_row(opening, size, first_width, -maximum, True)
            before = {id(atom) for atom in normal or [] if isinstance(atom, InstructionEnumeration)}
            after = {id(atom) for atom in candidate or [] if isinstance(atom, InstructionEnumeration)}
            if after - before:
                selected, tracking, compact = candidate, -maximum, True
        if selected is None:
            raise ValueError('Indivisible cluster exceeds instruction width: ' + opening[0].text)
        cut = next((index + 1 for index, atom in enumerate(grouped)
                    if selected and atom is selected[-1]), 0)
        if cut == hard_break and cut < len(grouped):
            cut += 1
        remainder = expand_instruction_atoms(grouped[cut:])
        rows = [expand_instruction_atoms(selected)]
        if remainder:
            rows.extend(self.hanging_lines('', size, rest_width, rest_width, True,
                                           hanging_punctuation=True, atoms=remainder))
        gaps = []
        for index, atom in enumerate(selected):
            if index:
                gaps.append(tracking)
            if isinstance(atom, InstructionEnumeration):
                internal = -size * self.instruction_style.enumeration_shrink if compact else tracking
                gaps.extend([internal] * (len(atom.parts) - 1))
        return rows, gaps if tracking else None, tracking

    @staticmethod
    def material_segments(blocks):
        """Keep ordinary sequences intact so citation/box pairing still works."""
        ordinary = []
        index = 0
        while index < len(blocks):
            block = blocks[index]
            if block.get('rule_style') == 'figure_caption':
                if block.get('type') != 'paragraph':
                    raise ValueError('figure_caption requires a paragraph')
                if index + 1 == len(blocks) or blocks[index + 1].get('type') != 'image':
                    raise ValueError('figure_caption must immediately precede an image')
                if ordinary:
                    yield ordinary
                    ordinary = []
                yield (block, blocks[index + 1])
                index += 2
            else:
                ordinary.append(block)
                index += 1
        if ordinary:
            yield ordinary

    def figure_plan(self, caption, picture):
        asset, width, height = self.image_geometry(picture, self.width)
        size, leading = self.fs, self.leading
        rows = self.hanging_lines(caption.get('text', ''), size, width, width,
                                  caption.get('style') == 'bold')
        # A captioned figure sits between text baselines, with one body cell
        # above the caption and optical spacing before and after its artwork.
        caption_top = self.catalog.width('文', size, False, self.section)
        image_top = caption_top + (len(rows) - 1) * leading + size + 8.4322 * size / 11.3
        after = 23.25734 * size / 11.3
        return dict(asset=asset, width=width, height=height, rows=rows, size=size,
                    caption_top=caption_top, image_top=image_top,
                    total=image_top + height + after)

    def material_height(self, blocks, width):
        total = 0
        for segment in self.material_segments(blocks):
            total += (self.figure_plan(*segment)['total'] if isinstance(segment, tuple)
                      else super().material_height(segment, width))
        return total

    def blocks(self, blocks, x=None, width=None, tail_reserve=0):
        for segment in self.material_segments(blocks):
            if not isinstance(segment, tuple):
                super().blocks(segment, x, width, tail_reserve)
                continue
            plan = self.figure_plan(*segment)
            self.ensure(plan['total'])
            left = self.left + (self.width - plan['width']) / 2
            start = self.y
            for index, row in enumerate(plan['rows']):
                self.line(row, left, start + plan['caption_top'] + index * self.leading,
                          plan['size'])
            self.emit({'type': 'image', 'asset': plan['asset'],
                       'width': round(plan['width'], 5), 'height': round(plan['height'], 5),
                       'x': round(left, 5),
                       'y': round(self.H - start - plan['image_top'] - plan['height'], 5)})
            self.y = start + plan['total']
            self._last_material_kind = 'image'
            self._last_was_note = self._last_note_wrapped = False

    def written_instruction(self, atoms, x, top, width, final):
        self.line(atoms, x, top, metric(self.gc, 'instruction_font_size', 11.3))

    def written_heading_plan(self, group, config):
        """Measure one heading independently of its eventual page/cursor."""
        title = config.get('title', group.get('title', ''))
        match = re.fullmatch(r'問題\s*([0-9０-９]{1,2})', plain(title))
        title_size = metric(config, 'heading_size', 12.8)
        title_scale = title_size / 12.8
        title_baseline = 12.6201 * title_scale
        title_glyphs = []
        if match:
            title_glyphs.extend([('問', 0), ('題', 12.81024 * title_scale)])
            digits = match[1].translate(str.maketrans('0123456789', '０１２３４５６７８９'))
            for index, char in enumerate(digits):
                inset = 22.42048 + index * 6.38976 if len(digits) == 2 else 25.62048
                title_glyphs.append((char, inset * title_scale))
        else:
            x = 0
            for char in plain(title):
                title_glyphs.append((char, x))
                x += self.catalog.width(char, title_size, True, self.section)
        text = group.get('instruction', '')
        style = self.instruction_style
        size = metric(config, 'instruction_font_size', 11.3)
        scale = size / 11.3
        leading = metric(config, 'instruction_line_height', self.leading * scale)
        available = metric(config, 'instruction_width', self.width)
        if available > self.width + 1e-6:
            raise ValueError('Written instruction_width must fit within the body width')
        title_extent = (3 * title_size if match else
                        sum(self.catalog.width(char, title_size, True, self.section)
                            for char in plain(title)))
        first_inset = max(style.first_inset * scale, title_extent + size)
        rest_inset = style.rest_inset * scale
        # An opening parenthesis occupies a half-em at the optical line edge.
        opening = size / 2 if plain(text).startswith('（') else 0
        first_width = available - first_inset + opening
        rest_width = available - rest_inset
        if min(first_width, rest_width) < size:
            raise ValueError('Written heading leaves no room for instructions; shorten the title or reduce its size')
        measured = self.written_instruction_atoms(text, size)
        first_gaps, first_tracking = None, 0
        if self.section == 'R':
            rows, first_gaps, first_tracking = self.reading_instruction_rows(
                measured, size, first_width, rest_width, config)
        else:
            rows = self.hanging_lines(text, size, first_width, rest_width, True,
                                      hanging_punctuation=True, atoms=measured)
        if self.section != 'R' and group.get('kind') in ('choice', 'word_order'):
            rows = balance_instruction_tail(rows, min(rest_width, style.minimum_tail_cells * size * 1.0009))
        items = group.get('items', [])
        labelled = bool(items and items[0].get('label'))
        after = (self.leading if self._uses_reading_spacing() and not labelled
                 and config.get('layout') != 'facing_pages' else style.after * scale)
        title_height = title_baseline + title_size * .25 if title_glyphs else 0
        top_overhang = max(0, title_size - title_baseline) if title_glyphs else 0
        if rows:
            from rule_typography import ruby_layout
            for atom in rows[0]:
                if atom.ruby:
                    widths = [self.catalog.width(char, size, atom.bold, self.section)
                              for char in atom.text]
                    top_overhang = max([top_overhang] + [glyph.size + glyph.above - size
                                         for glyph in ruby_layout(atom, widths, size)])
        return {
            'title_glyphs': title_glyphs, 'title_size': title_size,
            'title_baseline': title_baseline, 'title_height': title_height,
            'rows': rows, 'size': size, 'leading': leading, 'available': available,
            'first_inset': first_inset - opening, 'rest_inset': rest_inset,
            'first_gaps': first_gaps, 'first_tracking': first_tracking, 'after': after,
            'height': max(len(rows) * leading + after, title_height),
            'first_chunk_height': max(leading if rows else after, title_height),
            'top_overhang': top_overhang,
        }

    def draw_written_heading(self, plan):
        """Draw the measured rows at the current cursor, rebasing after breaks."""
        self.ensure(plan['first_chunk_height'])
        top, first_page = self.y, self.page
        for char, inset in plan['title_glyphs']:
            self.glyph(char, plan['title_size'], self.left + inset,
                       top + plan['title_baseline'], True)
        rows = plan['rows']
        for index, atoms in enumerate(rows):
            if index:
                self.ensure(plan['leading'])
            inset = plan['first_inset'] if index == 0 else plan['rest_inset']
            if index == 0 and plan['first_gaps'] is not None:
                self.line_gaps(atoms, self.left + inset, self.y, plan['size'],
                               plan['first_gaps'], tracking=plan['first_tracking'])
            else:
                self.written_instruction(atoms, self.left + inset, self.y,
                                         plan['available'] - inset, index + 1 == len(rows))
            self.y += plan['leading']
        self.gap(plan['after'])
        if self.page is first_page:
            self.y = max(self.y, top + plan['title_height'])

    def dynamic_heading(self, group, config):
        if self.section == 'L':
            return self._listening_heading(group, config)
        self.draw_written_heading(self.written_heading_plan(group, config))
