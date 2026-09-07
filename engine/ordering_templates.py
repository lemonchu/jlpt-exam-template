"""The fixed ordering demonstration, independent of body calibration.

The small template owns only its heading and worked-example furniture. Every
glyph is resolved from the current local YAML fields; surrounding question IDs,
counts, and prose never participate in compatibility. Different example prose
or an unsupported style falls back to normal composition, not measured pages.
"""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from inline import parse
from semantic_bindings import chars_for, normal, pointer


def local_content(value):
    """Compare one template's content, preserving styles but not author IDs.

    Explicit mono-ruby partitions and equivalent group ruby have the same
    visible reading in this fixed asset. This is a local equality check, not
    an A-body fingerprint or a same-length replacement-text allowance.
    """
    if isinstance(value, dict):
        return {key: local_content(child) for key, child in value.items()
                if key not in {'id', 'source_number', 'source_pages'}}
    if isinstance(value, list):
        return [local_content(child) for child in value]
    if isinstance(value, str):
        return [(atom.text, atom.ruby, atom.bold, atom.underline,
                 atom.annotation, atom.annotation_span) for atom in parse(value)]
    return value


@lru_cache(maxsize=8)
def load_ordering_template(profile):
    asset = json.loads((Path(profile) / 'ordering-template.json').read_text(encoding='utf-8'))
    if asset.get('schema_version') != 1:
        raise ValueError('Ordering template schema_version must be 1')
    return asset


class OrderingTemplates:
    """Optional hooks used only by RuleLayout; precise composition is unchanged."""

    def _ordering_asset(self):
        return load_ordering_template(self.reference.profile)

    def _ordering_style_fits(self, asset, config):
        if config.get('heading_layout') is not None:
            return False
        style = asset['style']
        current = {'font_size': self.fs, 'line_height': self.leading,
                   'body_width': self.width,
                   'heading_size': config.get('heading_size', 12.8),
                   'instruction_font_size': config.get('instruction_font_size', 11.3)}
        if any(abs(float(current[key]) - expected) > 1e-4 for key, expected in style.items()):
            return False
        return (abs(float(config.get('instruction_line_height', self.leading)) - self.leading) < 1e-4
                and abs(float(config.get('instruction_width', self.width)) - self.width) < 1e-4)

    def _ordering_part_plan(self, asset, name, content):
        """Local dimensions only: never advance the cursor or create a page.

        ``advance`` is the cursor movement from the component's origin.
        ``overhang`` precedes that origin (the example's top separator), and
        ``minimum_height`` includes it for placement on an otherwise empty page.
        Adjacent heading + example reservations normally share that overhang
        with the heading's trailing whitespace instead of counting it twice.
        """
        part = asset[name]
        first_line = min(line[index] for line in part['lines'] for index in (1, 3))
        overhang = max(0, asset['stroke']/2 - first_line)
        height = part['advance'] + overhang
        if height > self.usable:
            return None
        return {'asset': asset, 'name': name, 'content': content,
                'advance': part['advance'], 'overhang': overhang,
                'minimum_height': height}

    def ordering_heading_plan(self, group, config):
        """Return applicable fixed-heading dimensions, without page side effects."""
        if group.get('kind') != 'word_order':
            return None
        asset = self._ordering_asset()
        content = {'title': config.get('title', group.get('title', '')),
                   'instruction': group.get('instruction', '')}
        if (not self._ordering_style_fits(asset, config)
                or local_content(content) != local_content(asset['heading']['content'])):
            return None
        return self._ordering_part_plan(asset, 'heading', content)

    def ordering_example_plan(self, item):
        """Use the exact same local-content/style checks for measuring and drawing."""
        if self.group.get('kind') != 'word_order' or not item.get('is_example'):
            return None
        asset = self._ordering_asset()
        if (not self._ordering_style_fits(asset, self.gc)
                or local_content(item) != local_content(asset['example']['content'])):
            return None
        # Body-only question selection and per-question option overrides are
        # irrelevant. Overrides of this example itself must remain effective.
        if self.configured_columns(item) not in ('auto', 4):
            return None
        columns = self.gc.get('table_column_widths', {})
        expected = [.13, .165, .11, .19, .11, .295]
        weights = columns.get(6, columns.get('6', expected))
        if list(weights) != expected:
            return None
        unsupported = ('table_font_size', 'table_line_height', 'table_cell_padding_x',
                       'table_cell_padding_top', 'table_cell_padding_bottom',
                       'table_column_alignments', 'material_line_height',
                       'material_box_padding', 'material_box_stroke',
                       'choice_prompt_max_negative_tracking',
                       'choice_option_max_negative_tracking',
                       'word_order_blank_max_negative_tracking')
        if any(key in self.gc for key in unsupported):
            return None
        if abs(float(self.gc.get('body_start_adjust', 0))) > 1e-9:
            return None
        if abs(float(self.gc.get('question_gap', 14.13)) - 14.13) > 1e-9:
            return None
        return self._ordering_part_plan(asset, 'example', item)

    def template_example(self, item):
        plan = self.ordering_example_plan(item)
        if plan is None:
            return False
        self._draw_ordering_plan(plan)
        self.component_audit[-1]['shared_example_component'] = True
        self.component_audit[-1]['ordering_example_template'] = True
        return True

    def _draw_ordering_plan(self, plan):
        # The top separator slightly precedes the label's flow origin. When
        # moving to a fresh page, reserve that overhang inside the usable area.
        overhang = plan['overhang']
        if self.y + plan['advance'] > self.bottom:
            self.new_page()
        if self.y - overhang < self.top:
            self.y = self.top + overhang
        self._place_ordering_part(plan['asset'], plan['name'], plan['content'], self.y)

    def _place_ordering_part(self, asset, name, content, top):
        """Instantiate local field slots and paths at the current body origin."""
        part = asset[name]
        values = {}
        for key, field in part['fields'].items():
            value = (str(field['option_number']) if 'option_number' in field
                     else str(pointer(content, field['pointer'])))
            values[key] = chars_for(value, field['role'])
        commands, resolved, ledger = [], {}, []
        serial = getattr(self, '_ordering_serial', 0)
        for index, source in enumerate(part['runs']):
            command = {key: deepcopy(value) for key, value in source.items() if key != 'slots'}
            run_id = f'ordering-{serial}-{name}-{index}'
            glyphs = []
            for slot in source['slots']:
                text = values[slot[0]][slot[1]]
                formatter = slot[2] if len(slot) > 2 else 'identity'
                if formatter == 'fullwidth':
                    text = ''.join(chr(ord(char) + 0xFEE0) if '!' <= char <= '~' else char
                                   for char in normal(text))
                elif formatter == 'ring':
                    text = '○'
                elif formatter != 'identity':
                    raise ValueError(f'Unknown ordering-template formatter: {formatter}')
                glyphs.append(text)
                ledger.append({'run': run_id, 'index': len(glyphs)-1, 'text': text,
                               'template': 'ordering', 'field': slot[0], 'char': slot[1]})
            command.update(type='run', run_id=run_id, slot_count=len(glyphs), shear=0,
                           x=self.left + source['x'], y=self.H - top - source['y'])
            commands.append(command)
            resolved[run_id] = {'glyphs': glyphs}
        rgb = ' '.join(str(value) for value in asset['ink'])
        operations = [f'q {rgb} RG {asset["stroke"]} w 0 J 0 j 10 M [] 0 d']
        for x1, y1, x2, y2 in part['lines']:
            operations.append(f'{self.left+x1:.12g} {self.H-top-y1:.12g} m '
                              f'{self.left+x2:.12g} {self.H-top-y2:.12g} l S')
        for x, y, width, height in part.get('rectangles', []):
            operations.append(f'{self.left+x:.12g} {self.H-top-y:.12g} '
                              f'{width:.12g} {-height:.12g} re S')
        commands[:0] = [{'type': 'vector', 'pdf': '\n'.join(operations + ['Q'])},
                        {'type': 'ink', 'rgb': asset['ink']}]
        self.page['commands'].extend(commands)
        self.page['_ink'] = None
        self.resolved.update(resolved)
        self.reference.ledger.extend(ledger)
        self.y = top + part['advance']
        self._ordering_serial = serial + 1
