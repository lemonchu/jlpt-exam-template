"""Rule-composed choices with punctuation-aware widths and paragraph boundaries.

Question and answer fields share one measurement/drawing plan. Short fields
can tighten enough to avoid an unnecessary wrap; prose that spans several
rows uses its own, more conservative, spacing budget. No specimen identifiers
or stored line endings are consulted.
"""
from dataclasses import dataclass, replace
from math import floor
import re

from geometry import CHOICE, metric
from inline import Atom, OPEN, CLOSE, measure, parse
from reading_rules import RIGID_PUNCTUATION, justified_gaps, kana_compressed_gaps, punctuation_gaps
from rule_typography import material_number_atoms


@dataclass(frozen=True)
class ChoiceStyle:
    single_line_shrink: float = .45
    prose_line_shrink: float = .18
    contraction_quantum: float = .0186
    dialogue_line_shrink: float = .75
    compact_column_clearance: float = .25
    compact_column_step: float = .0505


@dataclass
class DialogueLabel(Atom):
    """A speaker name centered in the shared field of a dialogue."""

    parts: tuple = ()


@dataclass
class DialogueColon(Atom):
    """A colon drawn optically at the center of its Japanese label cell."""


class ChoiceRow(list):
    """An ordinary atom list carrying its already measured spacing plan."""

    def __init__(self, atoms, gaps, *, rigid_tracking=None, uniform_tracking=0):
        super().__init__(atoms)
        self.gaps = gaps
        self.rigid_tracking = rigid_tracking
        self.uniform_tracking = uniform_tracking


def choice_gaps(atoms, width, size, *, maximum=0, bearings=False, justify=False, kana=False):
    """Return inter-atom gaps, or None when the row exceeds its fit budget."""
    gaps = punctuation_gaps(atoms, size)
    natural = sum(atom.width for atom in atoms) + sum(gaps)
    if (natural > width + .02 and atoms and atoms[-1].text in '、。'
            and not atoms[-1].underline):
        natural -= atoms[-1].width
    deficit = natural - width
    if deficit <= .02:
        return justified_gaps(atoms, width, size) if justify else gaps
    bearing_slots, flexible = [], []
    for index, (left, right) in enumerate(zip(atoms, atoms[1:])):
        a, b = left.text[-1:], right.text[:1]
        if not a or not b or a.isspace() or b.isspace() or gaps[index]:
            continue
        if a in '、。）」』】〉》' or b in '（「『【〈《':
            if bearings:
                bearing_slots.append(index)
        elif a not in RIGID_PUNCTUATION and b not in RIGID_PUNCTUATION:
            flexible.append(index)
    quarter = size / 4
    if deficit > len(bearing_slots) * quarter + len(flexible) * maximum + .02:
        return None
    if kana:
        contracted = kana_compressed_gaps(atoms, width, size)
        if contracted is not None:
            return contracted
    # Punctuation's empty side bearings absorb compression before letter gaps.
    for index in reversed(bearing_slots):
        amount = min(quarter, max(0, deficit))
        gaps[index] -= amount
        deficit -= amount
    if deficit <= .02:
        return gaps
    quantum = min(size * ChoiceStyle.contraction_quantum, maximum)
    common = floor(deficit / (len(flexible) * quantum)) * quantum
    for index in flexible:
        gaps[index] -= common
    deficit -= len(flexible) * common
    for index in reversed(flexible):
        amount = min(maximum - common, quantum, max(0, deficit))
        gaps[index] -= amount
        deficit -= amount
    return gaps


def choice_rows(atoms, first_width, rest_width, size, *, maximum=0, bearings=False):
    """Greedy kinsoku wrapping using the same gaps later supplied to drawing."""
    def fits(candidate, width):
        return choice_gaps(candidate, width, size, maximum=maximum, bearings=bearings) is not None

    result, row = [], []
    for index, atom in enumerate(atoms):
        if atom.text == '\n':
            result.append(row)
            row = []
            continue
        width = rest_width if result else first_width
        if not fits([atom], width):
            raise ValueError('Indivisible cluster exceeds choice width: ' + atom.text)
        separator = atom.text.isspace() and not atom.underline
        if row and not fits(row + [atom], width):
            if separator:
                continue
            if (index + 1 < len(atoms) and atoms[index + 1].text in '、。'
                    and fits(row + [atom, atoms[index + 1]], width)):
                row.append(atom)
                continue
            carry = []
            if atom.text[:1] in CLOSE:
                while row:
                    carry.insert(0, row.pop())
                    if carry[0].text[:1] not in CLOSE and not carry[0].text.isspace():
                        break
            while row and row[-1].text[-1:] in OPEN:
                carry.insert(0, row.pop())
            if row:
                result.append(row)
            row = carry
        if not row and separator:
            continue
        row.append(atom)
    if row or not result:
        result.append(row)
    for index, row in enumerate(result):
        if not fits(row, first_width if index == 0 else rest_width):
            raise ValueError('Unbreakable kinsoku cluster exceeds choice width: '
                             + ''.join(atom.text for atom in row))
    return result


class ChoiceRules:
    choice_style = ChoiceStyle()

    def _choice_atoms(self, text, size):
        return material_number_atoms(measure(parse(text), self.catalog, size, self.section),
                                      self.catalog, size, self.section)

    def choice_option_atoms(self, text, size):
        return self._choice_atoms(text, size)

    def _choice_paragraph(self, text, first, rest, size, *, reading=False,
                          atoms=None, dialogue=False, option=False, single_limit=None):
        atoms = self._choice_atoms(text, size) if atoms is None else atoms
        if any(atom.text == '\n' for atom in atoms):
            paragraphs = [[]]
            for atom in atoms:
                if atom.text == '\n':
                    paragraphs.append([])
                else:
                    paragraphs[-1].append(atom)
            return [row for index, paragraph in enumerate(paragraphs)
                    for row in self._choice_paragraph('', first if index == 0 else rest,
                        rest, size, reading=reading, atoms=paragraph, dialogue=dialogue,
                        option=option, single_limit=single_limit)]
        default_single = (self.choice_style.prose_line_shrink if option and reading
                          else self.choice_style.single_line_shrink)
        single = metric(self.gc, 'choice_option_max_negative_tracking' if option
                        else 'choice_prompt_max_negative_tracking', default_single, allow_zero=True)
        if single_limit is not None:
            single = single_limit
        key = 'choice_option_max_negative_tracking' if option else 'choice_prompt_max_negative_tracking'
        # Answer prose uses kana-first tightening; prompts retain their own
        # punctuation-first policy. Explicit editor budgets remain authoritative.
        kana = reading and option and key not in self.gc
        gaps = choice_gaps(atoms, first, size, maximum=single, bearings=True, kana=kana)
        if gaps is not None:
            return [ChoiceRow(atoms, gaps)]
        maximum = (self.choice_style.dialogue_line_shrink if dialogue else
                   self.choice_style.prose_line_shrink if reading else 0)
        if key in self.gc:
            maximum = min(maximum, single)
        bearings = reading or dialogue
        rows = choice_rows(atoms, first, rest, size, maximum=maximum, bearings=bearings)
        return [ChoiceRow(row, choice_gaps(row, first if index == 0 else rest, size,
                                           maximum=maximum, bearings=bearings,
                                           justify=index + 1 < len(rows), kana=kana))
                for index, row in enumerate(rows)]

    def _prompt_paragraphs(self, text, size):
        """Recognize a multi-paragraph dialogue by its repeated speaker fields."""
        paragraphs = [self._choice_atoms(part, size) for part in text.splitlines() or ['']]
        prefixes = []
        for atoms in paragraphs:
            split = next((index for index, atom in enumerate(atoms)
                          if atom.text in ('「', '：', ':')), None)
            label = ''.join(atom.text for atom in atoms[:split]) if split is not None else ''
            valid = bool(split and len(label) <= 8 and not re.search(r'[\s、。（）「」：:]', label))
            prefixes.append(split if valid else None)
        if sum(index is not None for index in prefixes) < 2:
            return [(atoms, 0.0) for atoms in paragraphs]
        field = max(sum(atom.width for atom in atoms[:split])
                    for atoms, split in zip(paragraphs, prefixes) if split is not None)
        result = []
        for atoms, split in zip(paragraphs, prefixes):
            if split is None:
                result.append((atoms, 0.0))
                continue
            label = DialogueLabel(''.join(atom.text for atom in atoms[:split]),
                                  width=field, parts=tuple(atoms[:split]))
            tail = list(atoms[split:])
            if tail[0].text in ('：', ':'):
                tail[0] = DialogueColon('：', width=size * (11.16 / 11.3))
            result.append(([label] + tail, field))
        return result

    def _option_single_limit(self, options, widths, columns, size):
        """Tighten a reading answer set together when all four can stay single-row."""
        maximum = metric(self.gc, 'choice_option_max_negative_tracking',
                         self.choice_style.single_line_shrink, allow_zero=True)
        if self.section != 'R' or all(
            not any(atom.text == '\n' for atom in atoms) and
            choice_gaps(atoms, widths[index % columns][0], size,
                        maximum=maximum, bearings=True) is not None
            for index, atoms in enumerate(options)
        ):
            return maximum
        return min(maximum, self.choice_style.prose_line_shrink)

    def ordering_atoms(self, text, size, bold=False):
        """Keep ordering slots rigid on the same calibrated cell grid as text."""
        atoms = super().ordering_atoms(text, size, bold)
        cell = self.catalog.width('あ', size, bold, self.section)
        return [replace(atom, width=3 * cell) if atom.underline and (
                    atom.text.isspace() or atom.text == '★') else
                replace(atom, width=cell) if atom.text == '　' and not atom.underline else atom
                for atom in atoms]

    def _ordering_rows(self, text, size):
        """Fit rigid answer slots, then justify only rows ending in prose.

        Slots and their separators keep their widths under both contraction
        and expansion. A row broken within the slot sequence stays ragged;
        spreading its surrounding prose would move a single answer field.
        """
        atoms = material_number_atoms(self.ordering_atoms(text, size),
                                      self.catalog, size, self.section)
        first, rest = self.width - CHOICE.prompt_inset(0), self.width - CHOICE.prompt_inset(1)
        maximum = metric(self.gc, 'choice_prompt_max_negative_tracking', .15, allow_zero=True)
        blank_maximum = metric(self.gc, 'word_order_blank_max_negative_tracking', .27, allow_zero=True)
        rows = self.hanging_lines(text, size, first, rest, atoms=atoms,
            max_negative_tracking=maximum, rigid_blanks=True,
            max_negative_blank_tracking=blank_maximum, hanging_punctuation=True)
        result = []
        for index, row in enumerate(rows):
            width = first if index == 0 else rest
            tracking = self.line_tracking(row, width, maximum, True, blank_maximum, True) or 0.0
            if tracking >= 0 and index + 1 < len(rows) and row and not (row[-1].underline or row[-1].text.isspace()):
                gaps = justified_gaps(row, width, size)
            else:
                gaps = punctuation_gaps(row, size)
            result.append(ChoiceRow(row, gaps, rigid_tracking=tracking if tracking < 0 else None))
        return result

    def _compact_option(self, rows, width, columns, column, size):
        """Give near-full compact answer cells clearance before the next label.

        Automatic column selection still tests the ordinary cell. Only a
        naturally fitting single row gets the compact style's tracking step;
        the final column has no neighbouring answer label to clear.
        """
        if columns != 4 or column == columns - 1 or len(rows) != 1 or any(rows[0].gaps):
            return rows
        row = rows[0]
        extent = sum(atom.width for atom in row)
        target = width - size * self.choice_style.compact_column_clearance
        if extent <= target + .02:
            return rows
        step = size * self.choice_style.compact_column_step
        if ('choice_option_max_negative_tracking' in self.gc and
                metric(self.gc, 'choice_option_max_negative_tracking', step, allow_zero=True) < step):
            return rows
        if extent - step * self.tracking_gaps(row) > target + .02:
            return rows
        return [ChoiceRow(row, row.gaps, uniform_tracking=-step)]

    def choice_prompt_plan(self, item, size, rigid_blanks):
        rows, insets = [], []
        if rigid_blanks:
            rows = self._ordering_rows(item.get('prompt', ''), size)
            insets = [CHOICE.prompt_inset(index) for index in range(len(rows))]
        else:
            for atoms, label_width in self._prompt_paragraphs(item.get('prompt', ''), size):
                first_inset = CHOICE.prompt_inset(0)
                rest_inset = first_inset + label_width if label_width else CHOICE.prompt_inset(1)
                current = self._choice_paragraph('', self.width - first_inset,
                                                  self.width - rest_inset, size,
                                                  reading=self.section == 'R', atoms=atoms,
                                                  dialogue=bool(label_width) and not any(
                                                      isinstance(atom, DialogueColon) for atom in atoms))
                rows.extend(current)
                insets.extend(first_inset if index == 0 else rest_inset for index in range(len(current)))
        return {'promptlines': rows, 'prompt_insets': insets, 'prompt_tracking': [0.0] * len(rows)}

    def choice_option_plan(self, options, option_atoms, widths, cols, size):
        single = self._option_single_limit(option_atoms, widths, cols, size)
        result = []
        for index, (text, atoms) in enumerate(zip(options, option_atoms)):
            first, rest = widths[index % cols]
            current = self._choice_paragraph(text, first, rest, size,
                                              reading=self.section == 'R', option=True,
                                              atoms=atoms, single_limit=single)
            result.append(self._compact_option(current, first, cols, index % cols, size))
        return result

    def prompt_line(self, atoms, x, top, size, width, final, tracking, rigid_blanks):
        if isinstance(atoms, ChoiceRow):
            if atoms.rigid_tracking is not None:
                return self.line(atoms, x, top, size, tracking=atoms.rigid_tracking, rigid_blanks=True)
            return self.line_gaps(atoms, x, top, size, atoms.gaps)
        return super().prompt_line(atoms, x, top, size, width, final, tracking, rigid_blanks)

    def option_line(self, atoms, x, top, size, width, final):
        if isinstance(atoms, ChoiceRow):
            if atoms.uniform_tracking:
                return self.line(atoms, x, top, size, tracking=atoms.uniform_tracking)
            return self.line_gaps(atoms, x, top, size, atoms.gaps)
        return super().option_line(atoms, x, top, size, width, final)

    def tracking_units(self, atom):
        if isinstance(atom, (DialogueLabel, DialogueColon)):
            return 1
        return super().tracking_units(atom)

    def line(self, atoms, x, top, size, align='left', width=None,
             color='0.13725,0.12157,0.12549', tracking=0, rigid_blanks=False, **kwargs):
        if not any(isinstance(atom, (DialogueLabel, DialogueColon)) for atom in atoms):
            return super().line(atoms, x, top, size, align, width, color,
                                 tracking, rigid_blanks, **kwargs)
        extent = sum(atom.width for atom in atoms) + tracking * self.tracking_gaps(atoms, rigid_blanks)
        if width is not None and align in ('center', 'right'):
            x += (width - extent) / (2 if align == 'center' else 1)
        for index, atom in enumerate(atoms):
            if isinstance(atom, DialogueLabel):
                inset = (atom.width - sum(part.width for part in atom.parts)) / 2
                super().line(list(atom.parts), x + inset, top, size, color=color)
            elif isinstance(atom, DialogueColon):
                self.glyph(':', size, x + size * .4009, top + size * (1 - .1248),
                           atom.bold, color)
            else:
                super().line([atom], x, top, size, color=color,
                              tracking=tracking, rigid_blanks=rigid_blanks, **kwargs)
            x += atom.width
            if index + 1 < len(atoms):
                x += tracking
