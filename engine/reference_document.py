"""Readable information sheets from text, tables and nested notice boxes.

The opt-in ``reference`` role shares one measured plan between page fitting
and drawing. Density depends on available space, never an exam or item ID.
Existing guide/notice styles retain their independently calibrated metrics.
"""
from dataclasses import dataclass, field


REFERENCE_TEXT_ROLES = frozenset({
    'reference_brand', 'reference_title', 'reference_intro',
    'reference_section', 'reference_subsection', 'reference_body',
    'reference_note', 'reference_contact', 'reference_subtitle', 'reference_caption',
})


@dataclass
class ReferencePlan:
    width: float
    body_size: float
    spacing: float
    operations: list = field(default_factory=list)
    height: float = 0


class ReferenceDocumentRules:
    def block(self, block, x=None, width=None):
        if block.get('type') == 'box' and block.get('rule_style') == 'reference':
            return self.reference_document(block, self.left if x is None else x,
                                           self.width if width is None else width)
        return super().block(block, x, width)

    def estimate_block(self, block, width=None):
        if block.get('type') == 'box' and block.get('rule_style') == 'reference':
            return self.reference_document_plan(block, self.width if width is None else width).height
        return super().estimate_block(block, width)

    def reference_document_plan(self, block, width):
        if width < 120:
            raise ValueError('Reference document width leaves too little room for text')
        if not block.get('blocks'):
            raise ValueError('Reference documents require text, tables or notice boxes')
        # First reduce optional whitespace. Smaller type is a last resort for
        # dense sheets; an overfull sheet fails rather than clipping content.
        for size, spacing in ((10.5, 1), (10.5, .8), (10, .8), (9.5, .75)):
            plan = ReferencePlan(width, size, spacing)
            plan.height = self._reference_blocks(plan, block['blocks'], 18, 20,
                                                 width - 36) + 18
            if plan.height <= self.usable:
                return plan
        raise ValueError(f'Reference document needs {plan.height:.1f} bp; '
                         f'available height is {self.usable:.1f} bp')

    def _reference_blocks(self, plan, blocks, x, y, width):
        previous = None
        for block in blocks:
            kind = block.get('type')
            role = block.get('rule_style', 'reference_body')
            if kind in ('paragraph', 'heading'):
                if role not in REFERENCE_TEXT_ROLES:
                    raise ValueError(f'Unknown reference text role: {role}')
                size = plan.body_size
                before, after, bold = 0, 1.5, False
                align = block.get('align', 'left')
                if role == 'reference_title':
                    size, after, bold, align = 14.5, 13, True, block.get('align', 'center')
                elif role == 'reference_brand':
                    size, after, bold = 11, 6, True
                elif role == 'reference_subtitle':
                    size, after, bold, align = 11.5, 7, True, block.get('align', 'center')
                elif role == 'reference_caption':
                    size, before, after, bold = 10, 4, 2, True
                elif role == 'reference_section':
                    size, before, after, bold = 11, 8, 3, True
                elif role == 'reference_subsection':
                    size, before, after, bold = 10.5, 4, 2, True
                elif role == 'reference_note':
                    size, before, after = max(9, size - .5), 3, 3
                elif role == 'reference_contact':
                    size = max(9.5, size - .5)
                    if previous not in ('reference_contact', 'reference_section'):
                        y += 7 * plan.spacing
                        plan.operations.append(dict(kind='rule', x=x, y=y, width=width))
                        before = 6
                if align not in ('left', 'center', 'right'):
                    raise ValueError('Reference text alignment must be left, center or right')
                y += before * plan.spacing
                leading = size * (1.4 if role != 'reference_title' else 1.45)
                inset = float(block.get('indent', 0))
                if inset < 0 or inset >= width:
                    raise ValueError('Reference paragraph indent must fit its line')
                rows = self.hanging_lines(block.get('text', ''), size, width - inset,
                                          width, bold=bold)
                for index, atoms in enumerate(rows):
                    dx = inset if index == 0 else 0
                    plan.operations.append(dict(kind='row', atoms=atoms, x=x + dx, y=y,
                                                size=size, align=align, width=width - dx))
                    y += leading
                if role == 'reference_title':
                    plan.operations.append(dict(kind='rule', x=x, y=y + 4, width=width))
                y += after * plan.spacing
            elif kind == 'table':
                y += 4 * plan.spacing
                y = self._reference_table(plan, block, x, y, width)
                y += 5 * plan.spacing
            elif kind == 'box':
                y += 5 * plan.spacing
                start = y
                y = self._reference_blocks(plan, block.get('blocks', []), x + 10,
                                            y + 8, width - 20) + 8
                plan.operations.append(dict(kind='rect', x=x, y=start, width=width,
                                            height=y - start, line_width=.4))
                y += 5 * plan.spacing
            else:
                raise ValueError('Reference documents support text, tables and nested boxes')
            previous = role
        return y

    def _reference_table(self, plan, block, x, y, width):
        table = {'table_font_size': plan.body_size - .5,
                 'table_line_height': (plan.body_size - .5) * 1.4,
                 'table_cell_padding_x': 5, 'table_cell_padding_top': 4 * plan.spacing,
                 'table_cell_padding_bottom': 4 * plan.spacing, **block}
        x, width = self.table_geometry(table, x, width)
        widths, heights, prepared, size, lead, align, header_align, pad, top = self.table_rows(table, width)
        headers = table.get('header_rows', 0)
        if isinstance(headers, bool) or not isinstance(headers, int) or not 0 <= headers <= len(prepared):
            raise ValueError('Reference table header_rows must be an integer within its row count')
        for i, (cells, height) in enumerate(zip(prepared, heights)):
            cell_x = x
            for lines, cell_width, alignment in zip(cells, widths, header_align if i < headers else align):
                fill = '.95 .95 .95' if i < headers and table.get('header_fill', True) else None
                if table.get('borders', True) or fill:
                    plan.operations.append(dict(kind='rect', x=cell_x, y=y, width=cell_width,
                                                height=height, fill=fill,
                                                stroke=table.get('borders', True), line_width=.35))
                for j, atoms in enumerate(lines):
                    plan.operations.append(dict(kind='row', atoms=atoms, x=cell_x + pad,
                                                y=y + top + j * lead, size=size,
                                                align=alignment, width=cell_width - 2 * pad))
                cell_x += cell_width
            y += height
        return y

    def reference_document(self, block, x, width):
        plan = self.reference_document_plan(block, width)
        if getattr(self, 'component_audit', None):
            self.component_audit[-1]['reference_document'] = {
                'body_size': plan.body_size, 'spacing_factor': plan.spacing,
                'height': round(plan.height, 3), 'available_height': round(self.usable, 3),
            }
        offset = x - self.left
        self.ensure(plan.height)
        x, top = self.left + offset, self.y
        for op in plan.operations:
            if op['kind'] == 'row':
                self.line(op['atoms'], x + op['x'], top + op['y'], op['size'],
                          align=op['align'], width=op['width'])
            elif op['kind'] == 'rule':
                self.rule(x + op['x'], top + op['y'], x + op['x'] + op['width'],
                          top + op['y'], .45)
            else:
                self.rect(x + op['x'], top + op['y'], op['width'], op['height'],
                          fill=op.get('fill'), stroke=op.get('stroke', True),
                          line_width=op['line_width'])
        self.rect(x, top, width, plan.height, line_width=.6)
        self.y = top + plan.height
        self._last_was_note = False
        self._last_note_wrapped = False
        self._last_material_kind = 'box'
