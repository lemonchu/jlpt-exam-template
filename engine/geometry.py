"""Calibrated N1 dimensions shared by layout and fixed templates.

All lengths are PDF bp. Page positions use a top-left origin; component
positions are offsets from the current body's left edge and text baseline.
Keep measured optical offsets here when deriving them would change the print.
"""
from dataclasses import dataclass
from math import isfinite

PAPER_WIDTH = 595.0
PAPER_HEIGHT = 842.0
BODY_BOTTOM = 783.0


def require_number(value, message):
    """Parse a finite dimension, rejecting YAML booleans and NaN/Infinity."""
    if isinstance(value, bool):
        raise ValueError(message)
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(message) from error
    if not isfinite(number):
        raise ValueError(message)
    return number


def metric(config, name, default, *, allow_zero=False):
    requirement = 'non-negative' if allow_zero else 'positive'
    message = f'{name} must be a {requirement} number'
    value = require_number(config.get(name, default), message)
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError(message)
    return value


@dataclass(frozen=True)
class BodyGrid:
    left_odd: float
    left_even: float
    width: float
    top: float
    font_size: float
    line_height: float

    def left(self, page_number, overrides=None):
        key = 'left_odd' if page_number % 2 else 'left_even'
        return float((overrides or {}).get(key, getattr(self, key)))

    def geometry(self, page_number, overrides=None):
        return self.left(page_number, overrides), float((overrides or {}).get('body_width', self.width))

WRITTEN = BodyGrid(78.96, 63.63, 452.41, 62.4928, 11.3, 24.05996)
LISTENING = BodyGrid(63.45, 45.21, 513.6, 61.4489, 14.2, 28.35)


def body_grid(section):
    return LISTENING if section == 'L' else WRITTEN


@dataclass(frozen=True)
class ChoiceGrid:
    """One answer grid for measurement, automatic columns and drawing.

    Two-column answers occupy every other anchor of the four-column grid.
    The 0.05 bp fit allowance preserves the rounding of the measured slots.
    """
    inset: float = 16.95
    em: float = 11.31
    column_pitch: float = 101.79
    fit_allowance: float = .05

    def prompt_inset(self, line):
        return self.inset + self.em if line == 0 else self.inset

    def answer_inset(self, line):
        return 2 * self.em if line == 0 else self.em

    def starts(self, columns):
        if columns not in (1, 2, 4):
            raise ValueError('Choice columns must be 1, 2, or 4')
        step = 4 // columns
        return [round(self.inset + i * step * self.column_pitch, 2) for i in range(columns)]

    def geometry(self, columns, available):
        if isinstance(available, bool) or not isinstance(available, (int, float)) or available <= 0:
            raise ValueError('Choice width must be a positive number')
        starts = self.starts(columns)
        widths = []
        for index, start in enumerate(starts):
            end = starts[index + 1] - self.em if index + 1 < columns else available
            first = end - start - self.answer_inset(0)
            rest = end - start - self.answer_inset(1)
            if min(first, rest) <= 0:
                raise ValueError('Choice width is too narrow for its columns')
            widths.append((first + self.fit_allowance, rest + self.fit_allowance))
        return starts, widths


CHOICE = ChoiceGrid()


@dataclass(frozen=True)
class ClozeBox:
    """Inline blank frame, scaled from the standard 11.3 bp body size."""
    body_size: float = 11.3
    width: float = 33.75
    suffix_width: float = 11.31
    margin: float = 5.655
    closing_margin: float = 2.655
    top_from_baseline: float = -12.655
    height: float = 16.742
    label_size: float = 9.2
    label_from_baseline: float = -.798
    digit_advance: float = 5.070304
    suffix_advance: float = 4.6

    def frame_width(self, suffix, scale=1):
        return (self.width + (self.suffix_width if suffix else 0)) * scale


CLOZE_BOX = ClozeBox()
