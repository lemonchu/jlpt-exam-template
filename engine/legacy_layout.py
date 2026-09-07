"""Opt-in legacy adapter: A-body compatibility and measured fragment reuse.

Only --precise / --recompose load this module. Failed calibration falls back
to ComponentLayout's shared composition; the rules engine never enters here.
"""
from copy import deepcopy
import json

from component_layout import ComponentLayout
from geometry import body_grid
from semantic_bindings import CalibrationMismatch, iter_questions


STYLE_CONTROL_FIELDS = {
    'id', 'sidebar', 'numbering', 'number_start', 'new_page', 'start_on', 'use_measured', 'items',
}
HEADING_STYLE_FIELDS = (
    'heading_layout', 'heading_size', 'instruction_font_size', 'instruction_line_height',
    'instruction_width',
)


def canonicalize_config(value):
    """Match YAML mappings (including integer keys) to JSON-backed contracts."""
    return json.loads(json.dumps(value))


def style_config(config):
    return {key: value for key, value in config.items() if key not in STYLE_CONTROL_FIELDS}


class LegacyPolicy:
    """Blueprint compatibility and the single old reference interleaf."""

    def __init__(self, reference, blueprint, component_data, booklet, *, recompose):
        contracts = reference.contracts
        self.reference = reference
        self.blueprint = blueprint
        self.canonical = contracts['blueprints'][booklet]
        self.components = (contracts['components'].get(booklet) or {}).get('components', {})
        self.entries = {}
        for raw in self.canonical.get('groups', []):
            entry = {'id': raw} if isinstance(raw, str) else raw
            self.entries[entry['id']] = entry
        self.recompose = recompose
        self.blueprint_has_header = 'header' in blueprint
        self.page_is_canonical = canonicalize_config(blueprint.get('page')) == self.canonical.get('page')
        self.pristine = (canonicalize_config(blueprint) == self.canonical
                         and canonicalize_config(component_data) == contracts['components'].get(booklet))

    def configure_group(self, group, entry, config):
        canonical_style = {**self.canonical.get('group_defaults', {}),
                           **self.components.get(group['kind'], {}),
                           **self.entries.get(group['id'], {})}
        reuse = (not self.recompose and 'items' not in config and self.page_is_canonical
                 and canonicalize_config(style_config(config))
                     == canonicalize_config(style_config(canonical_style)))
        heading = (not self.recompose
                   and all(config.get(key) == canonical_style.get(key) for key in HEADING_STYLE_FIELDS))
        config.update(use_measured=reuse, _use_measured_heading=heading, _use_measured_example=reuse)
        config['_refresh_furniture'] = (
            self.blueprint.get('sidebar') != self.canonical.get('sidebar')
            or 'sidebar' in entry or self.blueprint_has_header or 'footer' in self.blueprint)

    def insert_interleaf(self, layout, group):
        if len(layout.pages) + layout.start_page != 29 or not self.pristine or self.recompose:
            return False
        page = deepcopy(self.reference.pages[('R', 18)])
        self.reference.resolved.update(self.reference.meta(page['commands']))
        layout.pages.append({'commands': page['commands'], 'bands': [],
                             'group_ids': [group['id']], 'measured': True})
        layout.page = layout.pages[-1]
        return True


class LegacyLayout(ComponentLayout):
    """Measured reuse around, never inside, the common drawing pipeline."""

    def measured_geometry_compatible(self):
        return body_grid(self.section).matches(self)

    def begin_group(self, group, config):
        if not config.get('new_page', True) and self.page is not None and self.page['commands']:
            raise ValueError('Same-page groups require the default rules mode; remove --precise/--recompose')
        super().begin_group(group, config)

    def compose_group(self, group, config):
        reason = 'Custom composition configuration'
        if config.get('use_measured', True):
            try:
                start = len(self.pages)
                current = self.reference.take_group(group, self.n(), config.get('_refresh_furniture', False))
                for page in current:
                    self._refresh_bands(page)
                self.pages.pop()
                self.pages.extend(current)
                self.page = self.pages[-1]
                self.geometry()
                self.y = self.bottom
                self.component_audit.append({'group': group['id'], 'placement': 'measured',
                                             'body_pages': list(range(start, len(self.pages) + 1))})
                self.number += sum(1 for _ in iter_questions(group))
                return
            except CalibrationMismatch as error:
                reason = str(error)
        super().compose_group(group, config, reason=reason)

    def group_opening(self, group, config):
        items = group.get('items', [])
        if (config.get('use_measured', True) and group['kind'] == 'listening_choice'
                and items and items[0].get('is_example')):
            try:
                page = self.reference.take_page(group, self.reference.components[group['id']]['pages'][0], self.n())
                self.pages[-1] = self.page = page
                self.y = self.bottom
                self.record_example(dict(items[0], label='例'))
                self.component_audit[-1]['shared_intro_page'] = True
                return 1
            except CalibrationMismatch:
                pass
        return super().group_opening(group, config)

    def group_heading(self, group, config):
        if config.get('_use_measured_heading', True) and self.measured_geometry_compatible():
            try:
                commands, spec = self.reference.heading(group, self.left)
                self.page['commands'] += commands
                self.page['_ink'] = None
                if self.section == 'L':
                    if group['kind'] == 'listening_memo':
                        self.y = spec['first_item_baseline'] - 25.1744
                    else:
                        self.y = spec['first_item_baseline'] + 18.8077 - 20
                elif group['kind'] in ('choice', 'word_order'):
                    self.y = spec['first_item_baseline'] + .828 - self.fs
                else:
                    self.y = spec['first_item_baseline'] - self.fs
                return
            except CalibrationMismatch:
                pass
        super().group_heading(group, config)

    def render_item(self, item, index):
        if (self.gc.get('use_measured', True) and self.group['kind'] == 'word_order'
                and item.get('is_example') and self.gc.get('_use_measured_example', True)
                and abs(float(self.gc.get('body_start_adjust', 0))) < 1e-9
                and self.measured_geometry_compatible()):
            try:
                commands, baseline = self.reference.slice_item(self.group, index, self.n(), self.left)
                self.page['commands'] += commands
                self.page['_ink'] = None
                self.y = baseline - self.fs
                self.component_audit[-1]['shared_example_component'] = True
                self.record_example(item)
                return
            except CalibrationMismatch:
                pass
        super().render_item(item, index)

    def _refresh_bands(self, page):
        if page.get('measured_body'):
            page['bands'] = [deepcopy(self.gc['sidebar'])] if self.gc.get('sidebar') else []

    def reference_material(self, stimulus):
        if self.gc.get('use_measured') and self.group['id'] in self.reference.components:
            try:
                page = self.reference.take_page(self.group, self.reference.components[self.group['id']]['pages'][-1],
                                                self.n(), self.gc.get('_refresh_furniture', False))
                self._refresh_bands(page)
                self.pages[-1] = self.page = page
                self.y = self.bottom
                self.component_audit[-1]['shared_reference_page'] = True
                return
            except CalibrationMismatch:
                pass
        super().reference_material(stimulus)
