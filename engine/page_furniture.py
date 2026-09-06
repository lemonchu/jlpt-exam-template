"""Dynamic original-style headers, page numbers and section tabs.

Coordinates are PDF bp measured from the top left.  This module only adds
page furniture; it neither reads an exam PDF nor retrieves question text.
"""
from inline import plain

INK = '0.13725,0.12157,0.12549'
TAB_FILL = '0.42745 0.43137 0.43922'
FULLWIDTH = str.maketrans('0123456789', '０１２３４５６７８９')
TAB_DEFAULTS = {
    'V': {'y': 94.997, 'height': 85.039, 'label': '文字・語彙', 'optical': 4.30782},
    'G': {'y': 180.066, 'height': 85.010, 'label': '文法', 'optical': 4.30327},
    'R': {'y': 265.106, 'height': 85.039, 'label': '読解', 'optical': 4.29877},
    'L': {'y': 350.175, 'height': 85.039, 'label': '聴解', 'optical': 4.30327},
}


def _is_right(position, pn):
    if position not in ('outer', 'inner', 'left', 'right'):
        raise ValueError('Sidebar position must be outer, inner, left or right')
    return pn % 2 == 1 if position == 'outer' else pn % 2 == 0 if position == 'inner' else position == 'right'


def _advance(layout, ch, size):
    # CJK furniture uses exact em advances.  The text engine's extra body
    # tracking must not leak into a measured running head.
    if ord(ch) >= 0x3000:
        return size
    return layout.catalog.width(ch, size, False, layout.section, role='header')


def _header_chars(layout, text, size):
    """Retain Japanese half-em punctuation packing from the original head."""
    out = []
    x = 0.0
    for ch in text:
        if ch in '（「『【［｛〈《':
            x -= size * .5
        out.append((ch, x))
        x += _advance(layout, ch, size)
        if ch in '）」』】］｝〉》':
            x -= size * .5
    return out, x


def _header(layout, pn, listening):
    value = layout.bp.get('header', '聴解' if listening else '言語知識（文字・語彙・文法）・読解')
    if value is False or value is None or value == '':
        return
    config = value if isinstance(value, dict) else {}
    text = str(config.get('text', value))
    if '{page}' not in text:
        text += '－{page}'
    prefix, suffix = text.split('{page}', 1)
    suffix = suffix.replace('{page}', str(pn).translate(FULLWIDTH))
    size = float(config.get('font_size', 9.0))
    number_size = float(config.get('number_font_size', size * 9.6 / 9.0))
    if size <= 0 or number_size <= 0:
        raise ValueError('Running head font sizes must be positive')
    positions, prefix_width = _header_chars(layout, prefix, size)
    base = float(config.get('baseline', 21.3901 if pn % 2 else 19.9200))
    number_base = base - .0719 * size / 9.0
    # The original keeps the subject end at this anchor, including when page
    # numbers change from one to two digits.  It does not right-align each
    # differing glyph bounding box.
    start = float(config.get('x', layout.W - 27.88 - prefix_width if pn % 2 else 18.27))
    color = str(config.get('color', INK)).replace(' ', ',')
    for ch, offset in positions:
        layout.glyph(ch, size, start + offset, base, color=color, role='header')
    number = str(pn).translate(FULLWIDTH)
    anchor = start + prefix_width
    step = number_size * .5
    nx = anchor - step * .5 * (len(number) - 1)
    for ch in number:
        layout.glyph(ch, number_size, nx, number_base, color=color, role='header')
        nx += step
    if suffix:
        after, _ = _header_chars(layout, suffix, size)
        suffix_x = anchor + max(number_size, step * len(number))
        for ch, offset in after:
            layout.glyph(ch, size, suffix_x + offset, base, color=color, role='header')


def _footer(layout, pn, listening):
    value = layout.bp.get('footer', {})
    if value is False or value is None:
        return
    config = value if isinstance(value, dict) else {}
    # Helvetica source text matrices are (17, 14.45), not (17, 17).
    # PyMuPDF's reported span size alone loses this 85% vertical scale.
    font_size = float(config.get('font_size', 14.45))
    hscale = float(config.get('hscale', 17.0 / 14.45))
    scale = font_size / 14.45
    number = str(pn)
    odd = bool(pn % 2)
    if listening:
        left_mark = 276.24 if odd else 259.23
        number_x = 301.26 if odd else 284.25
        number_base = layout.H - 32.2616
        mark_base = layout.H - 32.0672
    else:
        left_mark = 274.80 if odd else 260.64
        number_x = 299.82 if odd else 285.66
        number_base = layout.H - 34.3916
        mark_base = layout.H - 34.1972
    # Mirror the original gutter compensation, then translate proportionally
    # when a paper other than 595 bp wide is requested.
    dx = (layout.W - 595.0) * .5 + float(config.get('x_offset', 0))
    dy = float(config.get('y_offset', 0))
    color = str(config.get('color', INK)).replace(' ', ',')
    mark = str(config.get('mark', '―'))
    if len(mark) != 1:
        raise ValueError('Footer mark must contain one character')
    for x in (left_mark, left_mark + 46.6496):
        layout.glyph(mark, 12.8 * scale, x + dx, mark_base + dy,
                     color=color, role='header')
    # Exact one- and two-digit origins from the source; the same centered
    # progression continues for longer user-defined pagination.
    number_x -= 4.71 * (len(number) - 1)
    advance = 9.4503 * scale * hscale / (17.0 / 14.45)
    for i, ch in enumerate(number):
        layout.glyph(ch, font_size, number_x + dx + i * advance,
                     number_base + dy, bold=True, color=color,
                     role='footer', hscale=hscale)


def _sidebar(layout, pn, band):
    section = str(band.get('section', layout.section))[:1]
    defaults = TAB_DEFAULTS.get(section, TAB_DEFAULTS['V'])
    text = plain(str(band.get('text', defaults['label'])))
    if not text:
        return
    right = _is_right(band.get('position', 'outer'), pn)
    original_width = 'width' not in band
    width = float(band.get('width', 28.228 if right else 28.169))
    height = float(band.get('height', defaults['height']))
    y = float(band.get('y', defaults['y']))
    x = float(band.get('x', layout.W - 28.204 if right and original_width
                       else .014771 if original_width else layout.W - width if right else 0.0))
    # A tiny original bleed over the paper's right edge is intentional.
    if width <= 0 or height <= 0 or y < 0 or y + height > layout.H or x < 0 or x + width > layout.W + .05:
        raise ValueError('Sidebar geometry exceeds the page')
    fill = str(band.get('fill', band.get('color', TAB_FILL))).replace(',', ' ')
    foreground = str(band.get('text_color', '1,1,1')).replace(' ', ',')
    layout.rect(x, y, width, height, fill=fill, stroke=False)
    size = float(band.get('font_size', band.get('size', 11.3)))
    if size <= 0:
        raise ValueError('Sidebar font size must be positive')
    # A two-character label has one em of added tracking, matching 文法/読解.
    # The longer 文字・語彙 label uses normal one-em vertical advance.
    step = float(band.get('line_height', size * 1.0009 * (2 if len(text) == 2 else 1)))
    if (len(text) - 1) * step + size > height - 8:
        fit = (height - 8) / ((len(text) - 1) * step + size)
        size *= fit
        step *= fit
    first = y + height / 2 - (len(text) - 1) * step / 2 + defaults['optical'] * size / 11.3
    if original_width and 'x' not in band:
        gx = layout.W - 19.7151 if right else 8.405
        gx += (11.3 - size) / 2
    else:
        gx = x + (width - size) / 2
    gx += float(band.get('text_x_offset', 0))
    first += float(band.get('text_y_offset', 0))
    for i, ch in enumerate(text):
        layout.glyph(ch, size, gx, first + step * i, color=foreground, role='sidebar')


def decorate(layout):
    """Add fresh furniture to unmeasured body pages, preserving layout state."""
    previous_page = layout.page
    previous_section = layout.section
    try:
        for index, page in enumerate(layout.pages):
            if page.get('measured'):
                continue
            layout.page = page
            group_ids = page.get('group_ids', [])
            layout.section = page.get('section') or (str(group_ids[0])[:1] if group_ids else previous_section)
            pn = int(layout.start_page) + index
            listening = layout.section == 'L'
            _header(layout, pn, listening)
            _footer(layout, pn, listening)
            for band in page.get('bands', []):
                if band:
                    _sidebar(layout, pn, {'text': band} if isinstance(band, str) else band)
    finally:
        layout.page = previous_page
        layout.section = previous_section
