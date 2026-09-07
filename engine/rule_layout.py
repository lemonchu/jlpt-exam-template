"""Default N1 generation: semantic content plus reusable layout rules.

Cover marks and the fixed ordering demonstration are independent templates.
All other body components, including headings, are generated without taking
measured text slots or consulting the content's calibration fingerprint.
"""
from component_layout import ComponentLayout
from geometry import metric, require_number
from group_flow import GroupFlow
from choice_rules import ChoiceRules
from listening_rules import ListeningRules
from ordering_templates import OrderingTemplates
from reading_rules import ReadingRules
from reference_rules import ReferenceRules
from rule_typography import TypographyRules
from written_rules import WrittenRules
from vertical_rules import VerticalRules
from rule_validation import validate_rule_content, validate_rule_dimensions


class RuleLayout(GroupFlow, OrderingTemplates, ListeningRules, ChoiceRules, ReferenceRules, VerticalRules, ReadingRules,
                 WrittenRules, TypographyRules, ComponentLayout):
    def __init__(self, catalog, blueprint, resources, out, reference):
        validate_rule_dimensions(blueprint.get('page', {}))
        super().__init__(catalog, blueprint, resources, out, reference)

    def heading_plan(self, group, config):
        fixed = self.ordering_heading_plan(group, config)
        if fixed is not None:
            return 'ordering', dict(fixed, height=fixed['advance'],
                                    top_overhang=fixed['overhang'])
        if self.section == 'L':
            return 'listening', self.listening_heading_plan(group, config)
        return 'written', self.written_heading_plan(group, config)

    def begin_group(self, group, config):
        self._pending_heading = self._opening_choice = None
        self._opening_listening = None
        self._opening_split_block = self._opening_split_minimum = None
        self._split_group_opening = False
        if config.get('new_page', True):
            self.new_page()
            return
        if self.page is None:
            self.new_page()
        self.geometry()
        heading = self.heading_plan(group, config)
        opening = self.first_item_keep(group, config)
        adjustment = require_number(config.get('body_start_adjust', 0),
                                    'body_start_adjust must be a number')
        if adjustment < 0:
            raise ValueError('Same-page groups require nonnegative body_start_adjust')
        height = heading[1]['height'] + adjustment
        minimum = height + opening['minimum']
        preferred = height + opening['preferred']
        if minimum > self.usable + 1e-6:
            raise ValueError('Heading and first indivisible content do not fit on one page; '
                             'shorten the heading or split the first item')
        keep = preferred if preferred <= self.usable + 1e-6 else minimum
        self._split_group_opening = preferred > self.usable + 1e-6
        self._opening_choice = ((opening['choice_item'], opening['choice_plan'])
                                if 'choice_plan' in opening else None)
        if 'listening_plan' in opening:
            self._opening_listening = opening['listening_item'], opening['listening_plan']
        if self._split_group_opening:
            self._opening_split_block = opening.get('split_block')
            self._opening_split_minimum = opening.get('split_minimum')
        occupied = bool(self.page['commands'])
        previous_sections = {identifier[:1] for identifier in self.page['group_ids']}
        # Different section tabs and facing spreads keep their page boundary.
        must_break = (opening.get('break_before', False)
                      or bool(previous_sections - {self.section}))
        gap = max(metric(config, 'group_gap', self.leading, allow_zero=True),
                  heading[1]['top_overhang']) if occupied else 0
        side = config.get('start_on')
        parity = {'left': 0, 'right': 1}.get(side)
        if config.get('layout') == 'facing_pages':
            parity = 0
        wrong_side = parity is not None and self.n() % 2 != parity
        if (occupied and must_break) or wrong_side or self.y + gap + keep > self.bottom + 1e-6:
            self.new_page()
            if parity is not None and self.n() % 2 != parity:
                self.new_page()
        else:
            self.y += gap
            self.add_band()
        self._pending_heading = heading

    def group_heading(self, group, config):
        kind, plan = self._pending_heading or self.heading_plan(group, config)
        self._pending_heading = None
        if kind == 'ordering':
            self._draw_ordering_plan(plan)
            self.component_audit[-1]['ordering_heading_template'] = True
        elif kind == 'listening':
            self.draw_listening_heading(plan)
        else:
            self.draw_written_heading(plan)

    def render_group(self, group, config):
        validate_rule_dimensions(config)
        validate_rule_content(group)
        if not isinstance(config.get('new_page', True), bool):
            raise ValueError('new_page must be true or false')
        super().render_group(group, config)
        self.component_audit[-1]['mode'] = 'rules'
        self.component_audit[-1]['reason'] = 'Semantic content and shared generation rules'
