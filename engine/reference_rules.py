"""A compact guide document generated from editorial roles and relative flow.

Use ``rule_style: guide`` on a boxed reference document and mark its children
as brand/title/intro/section/subsection/caption/caution. All measurements below
are type/style metrics. No page, question ID or source glyph coordinates are
consulted, and changing a paragraph or table row moves subsequent content.
"""
from dataclasses import dataclass, field, replace
import re

from inline import measure, parse, plain
from reading_rules import justified_gaps


@dataclass(frozen=True)
class GuideStyle:
    body_size: float = 11.3
    body_pitch: float = 10.65025
    body_leading: float = 16.40986
    outline_inset: float = 30.437
    outline_step: float = 11.31017
    body_inset: float = 8.64
    right_inset: float = 29.91
    brand_size: float = 12.4
    brand_pitch: float = 17.5501333333
    brand_shear: float = .36395161
    title_size: float = 17.7
    title_pitch: float = 19.68063
    outer_stroke: float = .72
    brand_baseline: float = 35.1373
    brand_rule_gap: float = 11.2967
    title_gap: float = 51.0528
    intro_gap: float = 19.3739
    first_section_gap: float = 32.6629
    section_gap: float = 27.3748
    subsection_gap: float = 18.9603
    subsection_after_table: float = 28.9125
    prose_after_heading: float = 20.01
    caption_gap: float = 24.99
    table_gap: float = 8.4171
    caution_gap: float = 19.7998
    bottom_padding: float = 25.6084


GUIDE = GuideStyle()
TEXT_ROLES = frozenset({
    'guide_brand', 'guide_title', 'guide_intro', 'guide_section',
    'guide_subsection', 'guide_caption', 'guide_caution',
    'guide_table_intro', 'guide_paragraph',
})


@dataclass
class GuidePlan:
    width: float
    operations: list = field(default_factory=list)
    baseline: float = 0.0
    last_role: str = ''
    level: int = 0
    height: float = 0.0


class ReferenceRules:
    """Opt-in document style; other reference material follows ordinary blocks."""

    def block(self, block, x=None, width=None):
        if block.get('type') == 'box' and block.get('rule_style') == 'guide':
            return self.guide_document(block, self.left if x is None else x,
                                       self.width if width is None else width)
        return super().block(block, x, width)

    def estimate_block(self, block, width=None):
        if block.get('type') == 'box' and block.get('rule_style') == 'guide':
            return self.guide_plan(block, self.width if width is None else width).height + 1.3532
        return super().estimate_block(block, width)

    def glyph(self, char, size, x, baseline, bold=False, *args, role=None, **kwargs):
        context = getattr(self, '_guide_glyph_style', None)
        if context is not None and role is None:
            role = context[0] or ('guide-heading' if bold else None)
        super().glyph(char, size, x, baseline, bold, *args, role=role, **kwargs)
        if context is not None and context[1] and not char.isspace():
            self.page['commands'][-1]['shear'] = context[1]

    def guide_plan(self, block, width):
        if width <= 2 * GUIDE.outline_inset + 4 * GUIDE.body_size:
            raise ValueError('Guide document width leaves too little room for its text')
        plan = GuidePlan(width + .038)
        children = block.get('blocks', [])
        if not children:
            raise ValueError('Guide documents require at least one text or table block')
        for index, child in enumerate(children):
            role = child.get('rule_style', 'guide_paragraph')
            if child.get('type') == 'table':
                self._guide_table_plan(plan, child)
                role = 'guide_table'
            elif child.get('type') in ('paragraph', 'heading'):
                if role not in TEXT_ROLES:
                    raise ValueError(f'Unknown guide text rule_style: {role}')
                following = children[index + 1] if index + 1 < len(children) else {}
                caption_width = None
                if role == 'guide_caption' and following.get('type') == 'table':
                    caption_width = sum(self._guide_table_columns(following, plan.width))
                self._guide_text_plan(plan, child, role, caption_width=caption_width)
            else:
                raise ValueError('Guide documents support text and tables; use ordinary blocks for mixed artwork')
            plan.last_role = role
        plan.height = plan.baseline + GUIDE.bottom_padding
        return plan

    def _guide_add_row(self, plan, atoms, x, baseline, size, *, tracking=0,
                       gaps=None, font_role=None, shear=0):
        plan.operations.append(dict(kind='row', atoms=atoms, x=x, baseline=baseline,
                                    size=size, tracking=tracking, gaps=gaps or [],
                                    font_role=font_role, shear=shear))
        plan.baseline = max(plan.baseline, baseline)

    def _guide_centered(self, plan, text, baseline, size, pitch, *, font_role=None,
                         shear=0, left=None):
        atoms = measure(parse(text), self.catalog, size, self.section)
        first = next((char for atom in atoms for char in atom.text if not char.isspace()), '文')
        tracking = pitch - self.catalog.width(first, size, False, self.section, font_role)
        available = plan.width - (2 * GUIDE.outline_inset if left is None else left + GUIDE.right_inset)
        dense = [replace(atom, width=atom.width + tracking * self.tracking_units(atom)) for atom in atoms]
        rows = self.hanging_lines(text, size, available, available, atoms=dense)
        for index, row in enumerate(rows):
            original = [replace(atom, width=atom.width - tracking * self.tracking_units(atom)) for atom in row]
            extent = sum(atom.width for atom in row) - (tracking if row else 0)
            if row and row[-1].text in '、。':
                extent -= size / 2
            x = (plan.width - extent) / 2 if left is None else left
            self._guide_add_row(plan, original, x, baseline + index * size * 1.35, size,
                                tracking=tracking, font_role=font_role, shear=shear)

    def _guide_text_plan(self, plan, block, role, *, caption_width=None):
        text = block.get('text', '')
        if role == 'guide_brand':
            baseline = plan.baseline + GUIDE.brand_baseline
            self._guide_centered(plan, text, baseline, GUIDE.brand_size, GUIDE.brand_pitch,
                                 font_role='guide-brand', shear=GUIDE.brand_shear, left=29.7786)
            length = 29.7786 + (len(plain(text)) - 1) * GUIDE.brand_pitch + GUIDE.brand_size + GUIDE.outline_step
            plan.operations.append(dict(kind='rule', x=0, y=plan.baseline + GUIDE.brand_rule_gap,
                                        width=min(plan.width, length), stroke=2.82,
                                        color='.57647 .58431 .59608'))
            return
        if role == 'guide_title':
            self._guide_centered(plan, text, plan.baseline + GUIDE.title_gap, GUIDE.title_size,
                                 GUIDE.title_pitch, font_role='guide-heading')
            return
        if role == 'guide_intro':
            self._guide_centered(plan, text, plan.baseline + GUIDE.intro_gap, 12, 12)
            return
        if role in ('guide_section', 'guide_subsection'):
            plan.level = int(role == 'guide_subsection')
            if plan.last_role == 'guide_intro':
                before = GUIDE.first_section_gap
            elif role == 'guide_subsection':
                before = GUIDE.subsection_after_table if plan.last_role == 'guide_table' else GUIDE.subsection_gap
            else:
                before = GUIDE.section_gap
            self._guide_outline(plan, text, plan.baseline + before)
            return
        if role == 'guide_caption':
            x = ((plan.width - caption_width) / 2 - .3695 - 2.60436
                 if caption_width is not None else GUIDE.outline_inset)
            self._guide_paragraph(plan, text, x, plan.width - x - GUIDE.right_inset,
                                  plan.baseline + GUIDE.caption_gap, indent=0)
            return
        x = GUIDE.outline_inset + GUIDE.body_inset + plan.level * GUIDE.outline_step
        width = plan.width - GUIDE.right_inset - x
        if role == 'guide_caution':
            self._guide_caution(plan, text, x + GUIDE.body_pitch,
                                width - GUIDE.body_pitch, plan.baseline + GUIDE.caution_gap)
        else:
            before = GUIDE.prose_after_heading if plan.last_role in ('guide_section', 'guide_subsection') else GUIDE.body_leading
            # The first prose following a major heading uses an ordinary
            # paragraph indent; subsequent paragraphs use the dense text cell.
            indent = GUIDE.outline_step if role == 'guide_table_intro' else GUIDE.body_pitch
            self._guide_paragraph(plan, text, x, width, plan.baseline + before, indent=indent)

    def _guide_outline(self, plan, text, baseline):
        x = GUIDE.outline_inset + plan.level * GUIDE.outline_step
        marker = re.match(r'^([①②③④⑤⑥⑦⑧⑨⑩])(?:[－-]([Ａ-ＺA-Z]))?\s*(.*)$', plain(text))
        if marker is None:
            return self._guide_centered(plan, text, baseline, GUIDE.body_size, GUIDE.outline_step,
                                        font_role='guide-heading', left=x)
        mark, letter, body = marker.groups()
        self._guide_add_row(plan, measure(parse(mark), self.catalog, 11.3, self.section), x,
                            baseline, 11.3, font_role='guide-number')
        if letter:
            plan.operations.append(dict(kind='rule', x=x + 11.27983, y=baseline - 4.3132,
                                        width=11.37, stroke=1.14))
            self._guide_add_row(plan, measure(parse(letter), self.catalog, 11.3, self.section),
                                x + 22.62034, baseline, 11.3, font_role='guide-heading')
            x += 39.57082
        else:
            x += 19.77048
        self._guide_centered(plan, body, baseline, 11.3, GUIDE.outline_step,
                             font_role='guide-heading', left=x)

    def _guide_paragraph(self, plan, text, x, width, baseline, *, indent=0):
        size = GUIDE.body_size
        tracking = GUIDE.body_pitch - 11.31017
        for paragraph in text.splitlines() or ['']:
            natural = measure(parse(paragraph), self.catalog, size, self.section)
            dense = [replace(atom, width=atom.width + tracking * self.tracking_units(atom))
                     for atom in natural]
            rows = self.hanging_lines(paragraph, size, width - indent, width,
                                      hanging_punctuation=True, atoms=dense)
            for index, row in enumerate(rows):
                inset = indent if index == 0 else 0
                gaps = justified_gaps(row, width - inset, size) if index + 1 < len(rows) else []
                original = [replace(atom, width=atom.width - tracking * self.tracking_units(atom))
                            for atom in row]
                self._guide_add_row(plan, original, x + inset, baseline, size,
                                    tracking=tracking, gaps=gaps)
                baseline += GUIDE.body_leading
        plan.baseline = baseline - GUIDE.body_leading

    def _guide_caution(self, plan, text, x, width, baseline):
        marker = re.match(r'^\*\*(.+?)[：:]\*\*(.*)$', text, re.DOTALL)
        if marker is None:
            return self._guide_paragraph(plan, text, x, width, baseline)
        label, body = marker.groups()
        label_width = (len(label) + 1) * GUIDE.body_pitch
        self._guide_centered(plan, label, baseline, 11.3, GUIDE.outline_step,
                             font_role='guide-heading', left=x)
        self._guide_add_row(plan, measure(parse(':'), self.catalog, 11.3, self.section),
                            x + len(label) * GUIDE.outline_step + 3.06004,
                            baseline - 1.41024, 11.3, font_role='guide-colon')
        self._guide_paragraph(plan, body, x + label_width, width - label_width, baseline)

    def _guide_table_width(self, rows):
        longest = max((len(plain(str(row[0]))) for row in rows if row), default=0)
        label = max(120.473, longest * GUIDE.body_pitch + GUIDE.body_size)
        columns = max((len(row) for row in rows), default=3)
        return label + max(0, columns - 1) * 65.197

    def _guide_table_columns(self, block, document_width):
        rows = block.get('rows', [])
        if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
            raise ValueError('Guide tables require equally sized nonempty rows')
        columns = len(rows[0])
        available = document_width - 2 * GUIDE.outline_inset
        preferred = self._guide_table_width(rows)
        width = min(available, preferred)
        weights = [preferred - (columns - 1) * 65.197] + [65.197] * (columns - 1)
        widths = [weight * width / preferred for weight in weights]
        if min(widths) < 2 * GUIDE.body_size:
            raise ValueError('Guide table has too many columns for readable cells; split the table')
        return widths

    def _guide_table_plan(self, plan, block):
        widths = self._guide_table_columns(block, plan.width)
        rows = block['rows']
        columns = len(widths)
        width = sum(widths)
        x = (plan.width - width) / 2 - .3695
        top = plan.baseline + GUIDE.table_gap
        header_rows = block.get('header_rows', 0)
        if isinstance(header_rows, bool) or not isinstance(header_rows, int) or not 0 <= header_rows <= len(rows):
            raise ValueError('Guide table header_rows must be an integer within its row count')
        y = top
        horizontal = [top]
        for index, row in enumerate(rows):
            cells = []
            for column, text in enumerate(row):
                atoms = measure(parse(str(text)), self.catalog, 11.3, self.section)
                tracking = 0 if index < header_rows or column else GUIDE.body_pitch - 11.31017
                dense = [replace(atom, width=atom.width + tracking * self.tracking_units(atom)) for atom in atoms]
                cell_rows = self.hanging_lines(str(text), 11.3, widths[column] - 11.3515,
                                              widths[column] - 11.3515, atoms=dense)
                cells.append((cell_rows, tracking))
            height = (17.007 if index < header_rows else 15.591) + (max(len(cell[0]) for cell in cells) - 1) * 15.591
            cell_x = x
            for column, (cell_rows, tracking) in enumerate(cells):
                for line, dense in enumerate(cell_rows):
                    atoms = [replace(atom, width=atom.width - tracking * self.tracking_units(atom)) for atom in dense]
                    extent = sum(atom.width for atom in dense) - (tracking if dense else 0)
                    text_x = cell_x + 5.67575 if column == 0 and index >= header_rows else cell_x + (widths[column] - extent) / 2
                    self._guide_add_row(plan, atoms, text_x, y + 12.0728 + line * 15.591,
                                        11.3, tracking=tracking)
                cell_x += widths[column]
            y += height
            horizontal.append(y)
        def horizontal_rule(border, split):
            segments = [(x - .177, x + width + .206)]
            if split and columns > 1:
                segments = [(x - .177, x + widths[0] - 1.388),
                            (x + widths[0], x + width + .206)]
            for start, end in segments:
                plan.operations.append(dict(kind='rule', x=start, y=border,
                                            width=end - start, stroke=.33))

        for index, border in enumerate(horizontal):
            horizontal_rule(border, 0 < index < len(horizontal) - 1)
        if 0 < header_rows < len(rows):
            horizontal_rule(horizontal[header_rows] - 1.417, True)
        edges = [x]
        for cell_width in widths:
            edges.append(edges[-1] + cell_width)
        if columns > 1:
            edges.append(x + widths[0] - 1.388)
        for edge in edges:
            segments = [(top, y)]
            if x < edge < x + width and 0 < header_rows < len(rows):
                segments = [(top, horizontal[header_rows] - 1.417),
                            (horizontal[header_rows], y)]
            for start, end in segments:
                plan.operations.append(dict(kind='vertical', x=edge, y=start, height=end - start, stroke=.33))
        plan.baseline = y

    def guide_document(self, block, x, width):
        plan = self.guide_plan(block, width)
        offset = x - self.left
        self.ensure(plan.height + 1.3532)
        x = self.left + offset - .017
        top = self.y + 1.3532
        previous = getattr(self, '_guide_glyph_style', None)
        try:
            for operation in plan.operations:
                kind = operation['kind']
                if kind == 'row':
                    self._guide_glyph_style = (operation['font_role'], operation['shear'])
                    cursor = x + operation['x']
                    atoms = operation['atoms']
                    for index, atom in enumerate(atoms):
                        self.line([atom], cursor, top + operation['baseline'] - operation['size'],
                                  operation['size'], tracking=operation['tracking'])
                        cursor += atom.width + operation['tracking'] * self.tracking_units(atom)
                        if index < len(operation['gaps']):
                            cursor += operation['gaps'][index]
                elif kind == 'rule':
                    self.rule(x + operation['x'], top + operation['y'],
                              x + operation['x'] + operation['width'], top + operation['y'], operation['stroke'],
                              operation.get('color', '.13725 .12157 .12549'))
                elif kind == 'vertical':
                    self.rule(x + operation['x'], top + operation['y'],
                              x + operation['x'], top + operation['y'] + operation['height'], operation['stroke'])
            self.rect(x, top, plan.width, plan.height, line_width=GUIDE.outer_stroke)
        finally:
            self._guide_glyph_style = previous
        self.y = top + plan.height
