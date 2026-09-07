"""Fit changed metadata inside the existing cover design, with no source text.

Unchanged capacities retain measured commands and the existing metadata resolver.
Changed capacities use only current YAML, measured field geometry and font metrics.
The original row count/baselines remain fixed; text may shrink to 75%, then errors.
"""
from pathlib import Path
from collections import defaultdict, Counter
import copy
import hashlib
import json
import re

from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from metadata_bindings import (format_field, format_pointer_template,
                               load_metadata, resolve_loaded)
from font_overrides import font_role

MIN_SCALE = .75
CLOSE = '、。，．・：；？！ー〜～）)]｝}」』】〉》〕'
OPEN = '（([｛{「『【〈《〔'
SUBJECT_KINDS = ('subject_ja', 'subject_en')


class MetadataCapacityError(ValueError):
    pass


def _kind(field):
    if '.notice.' in field:
        return 'notice.' + field.rsplit('.', 1)[-1]
    for tail in ('subject_ja', 'subject_en', 'title', 'duration'):
        if field.endswith('.' + tail):
            return tail
    return field


def _field_runs(commands, bindings):
    fields = defaultdict(list)
    for index, command in enumerate(commands):
        if command.get('type') != 'run' or command['run_id'] not in bindings['runs']:
            continue
        record = bindings['runs'][command['run_id']]
        names = {g['field'] for g in record['glyphs']}
        if len(names) != 1:
            raise MetadataCapacityError(f'Metadata run {command["run_id"]} mixes fields; split its measured geometry before editing it')
        fields[next(iter(names))].append((index, command, record))
    return fields


def _right(command, kind):
    ratio = command['sx'] / command['sy']
    # A conservative final advance; no original character is stored or read.
    final = command['sx'] * (.5 if kind.endswith('.en') or kind == 'subject_en' else 1)
    return command['x'] + (command['offsets'][-1] if command['offsets'] else 0) * ratio + final


def _regions(layout, bindings):
    ranges = defaultdict(list)
    for section in layout['sections'].values():
        for page in section['pages']:
            for field, rows in _field_runs(page['commands'], bindings).items():
                kind = _kind(field)
                if kind not in ('notice.ja', 'notice.en', 'subject_ja', 'subject_en'):
                    continue
                for _, command, _ in rows:
                    ranges[kind].append((command['x'], _right(command, kind)))
    return {kind: (min(x[0] for x in boxes), max(x[1] for x in boxes)) for kind, boxes in ranges.items()}


def _raw_field(field, metadata):
    spec = dict(field)
    spec['formatter'] = [t for t in spec.get('formatter', []) if t['op'] != 'strip_whitespace']
    return ''.join(format_field(spec, metadata))


def _prefix(field, metadata):
    for transform in field.get('formatter', []):
        if transform['op'] == 'prepend':
            return format_pointer_template(transform, metadata)
    return ''


def _style_key(command):
    return command['font'], command['sx'], command['sy'], command.get('shear', 0)


def _parenthetical_characters(text):
    """Yield characters with the parenthetical style state used on covers."""
    depth = 0
    for char in text:
        if char in '（(':
            depth += 1
        yield char, bool(depth)
        if char in '）)' and depth:
            depth -= 1


class _Metrics:
    def __init__(self, fonts):
        self.resolver = getattr(fonts, 'resolver', fonts)
        self.tables = {}
        self.glyphsets = {}
        self.ink_bounds = {}

    def table(self, fid):
        if fid not in self.tables:
            record = self.resolver.fonts[fid].record
            tt = TTFont(self.resolver.resources / record['file'])
            cm = tt.getBestCmap() or {}
            self.tables[fid] = (tt['head'].unitsPerEm, {cp: tt['hmtx'].metrics[g][0] for cp, g in cm.items()})
            self.glyphsets[fid] = (tt.getGlyphSet(), cm)
            tt.close()
        return self.tables[fid]

    def bounds(self, fid, cp):
        key = fid, cp
        if key not in self.ink_bounds:
            self.table(fid)
            glyphs, cmap = self.glyphsets[fid]
            pen = BoundsPen(glyphs)
            glyphs[cmap[cp]].draw(pen)
            self.ink_bounds[key] = pen.bounds
        return self.ink_bounds[key]

    def width(self, char, style):
        if char == '\n':
            return 0
        if char.isspace():
            if char == '\u3000':
                return style['sx']
            upm, widths = self.table(style['font'])
            return widths.get(32, upm / 4) / upm * style['sx']
        fid, cp = self.resolver.resolve(style['font'], char, 'normal')
        upm, widths = self.table(fid)
        # A changed regular-Mincho numeric sentence keeps source half-em advances.
        if char.isascii() and char.isdigit() and font_role(self.resolver.fonts[style['font']].record) == 'mincho_regular':
            return style['sx'] * .5
        return widths[cp] / upm * style['sx']



def _rectangles(commands):
    """Read only rectangle geometry from the scene's existing PDF drawing ops."""
    rectangles = []
    identity = (1., 0., 0., 1., 0., 0.)
    for command in commands:
        if command.get('type') != 'vector':
            continue
        matrix = identity
        stack = []
        numbers = []
        for token in re.findall(r'/[^\s]+|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?|[A-Za-z*]+|[^\s]', command['pdf']):
            try:
                numbers.append(float(token))
                continue
            except ValueError:
                pass
            if token == 'q':
                stack.append(matrix)
            elif token == 'Q':
                matrix = stack.pop() if stack else identity
            elif token == 'cm' and len(numbers) >= 6:
                a,b,c,d,e,f = matrix
                aa,bb,cc,dd,ee,ff = numbers[-6:]
                matrix = (a*aa+c*bb,b*aa+d*bb,a*cc+c*dd,b*cc+d*dd,a*ee+c*ff+e,b*ee+d*ff+f)
            elif token == 're' and len(numbers) >= 4:
                x,y,w,h = numbers[-4:]
                a,b,c,d,e,f = matrix
                points = [(a*xx+c*yy+e,b*xx+d*yy+f) for xx,yy in ((x,y),(x+w,y),(x,y+h),(x+w,y+h))]
                rectangles.append((min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)))
            numbers = []
    return rectangles


def _attached_boxes(rows, metrics, rectangles):
    """A small rectangle enclosing a measured custom numeral is its decoration."""
    boxes = []
    for _, command, _ in rows:
        if metrics.resolver.fonts[command['font']].record.get('family') != 'custom':
            continue
        x = command['x'] + command['sx'] * .3
        y = command['y'] + command['sy'] * .4
        for box in rectangles:
            left,bottom,right,top = box
            if left <= x <= right and bottom <= y <= top and right-left <= command['sx']*4 and top-bottom <= command['sy']*2:
                boxes.append((command,box))
                break
    return boxes


def _clip_decorations(command, boxes, paper):
    if command.get('type') != 'vector' or not boxes:
        return command
    result = copy.deepcopy(command)
    path = f"0 0 {paper['width']} {paper['height']} re\n"
    for left,bottom,right,top in boxes:
        pad = .5
        path += f"{left-pad:.12g} {bottom-pad:.12g} {right-left+2*pad:.12g} {top-bottom+2*pad:.12g} re\n"
    result['pdf'] = 'q\n' + path + 'W* n\n' + result['pdf'] + '\nQ'
    return result


def _styles(rows, metrics, kind, attached_boxes=()):
    counts = Counter()
    examples = {}
    for _, command, record in rows:
        key = _style_key(command)
        counts[key] += len(record['glyphs'])
        examples[key] = command
    candidates = [key for key in counts if metrics.resolver.fonts[key[0]].record['family'] != 'custom'] or list(counts)
    if kind in SUBJECT_KINDS:
        main = max(candidates, key=lambda k: (k[2], counts[k]))
    elif kind == 'duration':
        regular = [k for k in candidates if not any(n in metrics.resolver.fonts[k[0]].record.get('name', '').lower() for n in ('helvetica', 'gothicmb'))]
        main = max(regular or candidates, key=lambda k: counts[k])
    else:
        main = max(candidates, key=lambda k: counts[k])
    baselines = sorted({command['y'] for _, command, _ in rows if _style_key(command) == main}, reverse=True)
    if not baselines:
        raise MetadataCapacityError('Metadata has no measured baseline')
    styles = {}
    for key, command in examples.items():
        baseline = min(baselines, key=lambda y: abs(y - command['y']))
        styles[key] = {'font': key[0], 'sx': key[1], 'sy': key[2], 'shear': key[3], 'dy': command['y'] - baseline}
    for command, (left,bottom,right,top) in attached_boxes:
        key = _style_key(command)
        styles[key].setdefault('box', {'dx': left-command['x'], 'dy': bottom-command['y'], 'width': right-left, 'height': top-bottom, 'line_width': .33})
    small = min(styles, key=lambda k: k[2]) if kind in SUBJECT_KINDS else main
    custom = next((key for key in styles if metrics.resolver.fonts[key[0]].record['family'] == 'custom'), None)
    digits = None
    if kind == 'duration':
        digits = next((key for key in styles if key != main), None)
    return styles, main, small, custom, digits, baselines


def _capacity_reason(field_name, rows, chars, metrics):
    """Equal character count is insufficient for proportional text or style spans."""
    kind = _kind(field_name)
    styles, main, small, _, _, baselines = _styles(rows, metrics, kind)
    if kind in SUBJECT_KINDS and main != small:
        expected_small = [inside for _, inside in _parenthetical_characters(chars)]
        for _, command, record in rows:
            is_small = abs(command['sy'] - styles[small]['sy']) < .01
            for glyph in record['glyphs']:
                if any(expected_small[i] != is_small for i in glyph['char_indices']):
                    return 'parenthetical-style-spans-changed'
    lines = defaultdict(list)
    for _, command, record in rows:
        for slot, glyph in enumerate(record['glyphs']):
            text = ''.join(chars[i] for i in glyph['char_indices'])
            form = command.get('forms', ['normal'] * command['slot_count'])[slot]
            if text.isspace():
                continue
            fid, cp = metrics.resolver.resolve(command['font'], text, form)
            bbox = metrics.bounds(fid, cp)
            if bbox is None:
                continue
            upm, _ = metrics.table(fid)
            x = command['x'] + command['offsets'][slot] * command['sx'] / command['sy']
            left, right = x + bbox[0] / upm * command['sx'], x + bbox[2] / upm * command['sx']
            row = min(baselines, key=lambda y: abs(y - command['y']))
            lines[row].append((x, left, right, command['sy']))
    for entries in lines.values():
        entries.sort()
        for previous, current in zip(entries, entries[1:]):
            # A tiny overlap of bounding boxes is normal kerning; large overlaps
            # expose new wide letters forced into old narrow-letter advances.
            if previous[2] - current[1] > min(previous[3], current[3]) * .07:
                return 'new-glyphs-overlap-measured-slots'
    return None


def _chars(text, styles, main, small, custom, digits, kind, metrics):
    result = []
    for char, inside_parentheses in _parenthetical_characters(text):
        key = main
        if kind in SUBJECT_KINDS and inside_parentheses:
            key = small
        elif kind == 'duration' and char.isdigit() and digits is not None:
            key = digits
        elif custom is not None and char.isascii() and char.isdigit():
            key = custom
        style = styles[key]
        item = {'char': char, 'style': style, 'width': metrics.width(char, style)}
        if 'box' in style and not char.isspace():
            margin = style['sy'] * .12
            item['width'] = style['box']['width'] + 2*margin
            item['glyph_shift'] = margin - style['box']['dx']
        result.append(item)
    return result


def _tokens(chars):
    result = []
    for char in chars:
        c = char['char']
        if result and re.fullmatch(r'[A-Za-z0-9]', c) and all(re.fullmatch(r'[A-Za-z0-9]', x['char']) for x in result[-1]):
            result[-1].append(char)
        else:
            result.append([char])
    return result


def _wrap(chars, widths, scale):
    tokens = _tokens(chars)
    lines = []
    line = []
    used = 0.0
    row = 0
    queue = list(tokens)
    while queue:
        token = queue.pop(0)
        if row >= len(widths):
            return None
        if token[0]['char'] == '\n':
            lines.append(line); line = []; used = 0.0; row += 1
            continue
        size = sum(c['width'] for c in token) * scale
        if size > widths[row] + 1e-7 and len(token) > 1:
            queue = [[c] for c in token] + queue
            continue
        if size > widths[row] + 1e-7:
            return None
        if not line and all(c['char'].isspace() for c in token):
            continue
        if used + size <= widths[row] + 1e-7:
            line.extend(token); used += size
            continue
        if all(c['char'].isspace() for c in token):
            continue
        moved = []
        if token[0]['char'] in CLOSE:
            while line:
                moved.insert(0, line.pop())
                if moved[0]['char'] not in CLOSE and not moved[0]['char'].isspace():
                    break
        while line and line[-1]['char'] in OPEN:
            moved.insert(0, line.pop())
        if not line:
            return None
        lines.append(line); row += 1
        line = []; used = 0.0
        queue = [[c] for c in moved] + [token] + queue
    if line:
        lines.append(line)
    return lines if len(lines) <= len(widths) else None


def _emit(chars, x, baseline, scale, stem, counter):
    commands = []
    resolved = {}
    cursor = x
    current = None
    for char in chars:
        style = char['style']
        if char['char'].isspace():
            cursor += char['width'] * scale
            continue
        glyph_x = cursor + char.get('glyph_shift', 0)*scale
        if 'box' in style:
            box = style['box']
            bx = glyph_x + box['dx']*scale
            by = baseline + (style['dy']+box['dy'])*scale
            commands.append({'type':'vector','pdf': f"q {box['line_width']*scale:.12g} w {bx:.12g} {by:.12g} {box['width']*scale:.12g} {box['height']*scale:.12g} re S Q"})
        key = (style['font'], style['sx'], style['sy'], style['shear'], style['dy'])
        if current is None or current['_key'] != key:
            counter[0] += 1
            rid = stem + '-%03d' % counter[0]
            current = {'type': 'run', 'run_id': rid, 'font': style['font'],
                       'sx': style['sx'] * scale, 'sy': style['sy'] * scale,
                       'x': glyph_x, 'y': baseline + style['dy'] * scale,
                       'offsets': [], 'slot_count': 0, 'shear': style['shear'], '_key': key}
            commands.append(current)
            resolved[rid] = {'glyphs': []}
        # Offsets are in the pre-horizontal-scale coordinate system of NRun.
        current['offsets'].append((glyph_x - current['x']) * current['sy'] / current['sx'])
        current['slot_count'] += 1
        resolved[current['run_id']]['glyphs'].append(char['char'])
        cursor += char['width'] * scale
    for command in commands:
        if command['type'] == 'run':
            del command['_key']
    return commands, resolved, cursor


def _reflow(field_name, field, rows, metadata, metrics, regions, page_width, attached_boxes):
    kind = _kind(field_name)
    styles, main, small, custom, digits, baselines = _styles(rows, metrics, kind, attached_boxes)
    text = _raw_field(field, metadata)
    prefix = _prefix(field, metadata) if kind == 'notice.ja' else ''
    if prefix and not text.startswith(prefix):
        raise MetadataCapacityError(f'{field_name}: notice prefix does not match its formatter')
    content = text[len(prefix):] if prefix else text
    low = min(command['x'] for _, command, _ in rows)
    high = max(_right(command, kind) for _, command, _ in rows)
    if kind in regions:
        low, high = regions[kind]
    center = kind in ('title', 'duration', 'subject_ja', 'label.notes_ja', 'label.notes_en', 'label.booklet')
    if kind in ('title', 'duration'):
        # These cover elements share the centered subject line's design axis.
        axis = sum(regions.get('subject_ja', (0, page_width))) / 2
        span = high - low
        low, high = axis - span / 2, axis + span / 2
    lefts = []
    for baseline in baselines:
        on_row = [command['x'] for _, command, _ in rows if abs(command['y'] - baseline) < 2.5]
        lefts.append(min(on_row) if on_row else low)
    if kind == 'notice.en':
        lefts = [regions[kind][0]] * len(baselines)
    if center or kind == 'subject_en':
        lefts = [low] * len(baselines)
    positions = {}
    for _, command, record in rows:
        for index, glyph in enumerate(record['glyphs']):
            for char_index in glyph['char_indices']:
                positions[char_index] = command['x'] + command['offsets'][index] * command['sx'] / command['sy']
    compact_prefix = ''.join(prefix.split())
    if compact_prefix:
        original_prefix_length = 2  # number + punctuation, declared by notice_prefix's formatter
        # Prefer the geometric first-body anchor; no original body text is read.
        lefts[0] = positions.get(original_prefix_length, low + styles[main]['sx'] * 2.25)
    chars = _chars(content, styles, main, small, custom, digits, kind, metrics)
    widths = [high - x for x in lefts]
    chosen = None
    for step in range(101):
        scale = 1.0 - step * (1.0 - MIN_SCALE) / 100
        lines = _wrap(chars, widths, scale)
        if lines is not None:
            chosen = scale, lines
            break
    if chosen is None:
        pointer = field['pointer']
        raise MetadataCapacityError(f'Metadata field {pointer} does not fit its {len(baselines)} original row(s) '
                                    f'at {MIN_SCALE:.0%} of the original size; shorten this field or provide a different cover layout')
    scale, lines = chosen
    commands = []
    resolved = {}
    stem = 'MC-' + rows[0][1]['run_id'] + '-' + hashlib.sha256(field_name.encode()).hexdigest()[:8]
    counter = [0]
    if compact_prefix:
        prefix_chars = _chars(compact_prefix, styles, main, small, custom, digits, kind, metrics)
        # Retain native prefix anchors when their standard two-character shape remains.
        if len(prefix_chars) == 2 and all(i in positions for i in (0, 1)):
            for i, char in enumerate(prefix_chars):
                cc, rr, _ = _emit([char], positions[i], baselines[0], scale, stem, counter)
                commands.extend(cc); resolved.update(rr)
        else:
            cc, rr, end = _emit(prefix_chars, low, baselines[0], scale, stem, counter)
            if end > lefts[0] - styles[main]['sx'] * .1:
                raise MetadataCapacityError(f'{field["pointer"]}: notice prefix exceeds its reserved hanging-indent area')
            commands.extend(cc); resolved.update(rr)
    max_right = 0
    for i, line in enumerate(lines):
        length = sum(c['width'] for c in line) * scale
        x = (low + high - length) / 2 if center else lefts[i]
        cc, rr, end = _emit(line, x, baselines[i], scale, stem, counter)
        if end > high + 1e-6:
            raise MetadataCapacityError(f'{field["pointer"]}: computed text crosses its reserved right boundary')
        max_right = max(max_right, end)
        commands.extend(cc); resolved.update(rr)
    audit = {'field': field_name, 'pointer': field['pointer'], 'mode': 'fit-original-field',
             'current_visible_characters': len(''.join(text.split())),
             'original_rows': len(baselines), 'used_rows': len(lines), 'baselines': baselines,
             'region': {'left': low, 'right': high, 'row_lefts': lefts},
             'scale': round(scale, 6), 'min_scale': MIN_SCALE, 'max_advance_right': max_right,
             'source_text_used': False, 'new_runs': [c['run_id'] for c in commands if c['type']=='run'],
             'redrawn_inline_boxes': sum(c['type']=='vector' for c in commands)}
    return commands, resolved, audit


def resolve_metadata_components(profile, metadata_path, commands, fonts, body_pages=None, *, template=None):
    """Return (new_commands, resolved_runs, audit) for one page's commands.

    `fonts` accepts ComponentFonts or an already-configured Resolver. Metadata
    glyphs on a page are replaced only when that semantic field changes capacity.
    Non-metadata commands are left alone. No original PDF/content is consulted.
    A preloaded cover template supplies bindings, paper and fit regions without
    reading the legacy all-body layout or metadata binding files.
    """
    profile = Path(profile)
    metadata_path = Path(metadata_path)
    bindings = (template['bindings'] if template is not None
                else json.loads((profile / 'metadata-bindings.json').read_text()))
    metadata = load_metadata(metadata_path, bindings, body_pages)
    by_field = _field_runs(commands, bindings)
    for booklet in ('written', 'listening'):
        if any(name.startswith(booklet + '.notice.') for name in by_field):
            expected_indices = {int(name.split('.')[2]) for name in bindings['fields'] if name.startswith(booklet + '.notice.')}
            supplied = metadata['booklets'][booklet]['notices']
            if not isinstance(supplied, list) or len(supplied) != len(expected_indices):
                raise MetadataCapacityError(f'The {booklet} cover defines {len(expected_indices)} notice blocks; change their text, or provide a different cover layout to change the block count')
    changes = []
    metrics = _Metrics(fonts)
    for field_name in by_field:
        field = bindings['fields'][field_name]
        chars = format_field(field, metadata)
        expected = field.get('glyph_slots')
        reason = 'character-count-changed' if expected is not None and len(chars) != expected else _capacity_reason(field_name, by_field[field_name], chars, metrics)
        if reason:
            changes.append((field_name, reason))
    changed_fields = {field_name for field_name, _ in changes}
    untouched_ids = [command['run_id'] for field, rows in by_field.items() if field not in changed_fields for _, command, _ in rows]
    resolved = resolve_loaded(metadata, bindings, metadata_path.name, run_ids=untouched_ids)['runs']
    output = []
    replacements = {}
    remove = set()
    audits = []
    paper = None
    regions = {}
    if changes:
        if template is not None:
            paper, regions = template['paper'], template['regions']
        else:
            layout = json.loads((profile / 'layout.json').read_text())
            paper, regions = layout['paper'], _regions(layout, bindings)
    rectangles = _rectangles(commands) if changes else []
    removed_boxes = []
    for field_name, reason in changes:
        rows = by_field[field_name]
        attached_boxes = _attached_boxes(rows, metrics, rectangles)
        cc, rr, aa = _reflow(field_name, bindings['fields'][field_name], rows, metadata, metrics, regions, paper['width'], attached_boxes)
        removed_boxes.extend(box for _, box in attached_boxes)
        replacements[rows[0][0]] = cc
        remove.update(index for index, _, _ in rows)
        resolved.update(rr)
        aa['reason'] = reason
        audits.append(aa)
    for index, command in enumerate(commands):
        if index in replacements:
            output.extend(replacements[index])
        if index not in remove:
            output.append(_clip_decorations(command, removed_boxes, paper))
    audit = {'schema_version': 1, 'unchanged_fields': sorted(set(by_field) - changed_fields),
             'changed_fields': audits, 'body_pages': body_pages, 'source_text_used': False,
             'original_run_count': sum(len(rows) for rows in by_field.values()),
             'resolved_run_count': len(resolved), 'removed_inline_box_rectangles': removed_boxes}
    return output, resolved, audit
