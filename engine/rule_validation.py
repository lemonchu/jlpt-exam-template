"""Validate experimental editorial roles before measuring or drawing content.

These checks are rules-only: the legacy renderer does not interpret rule_style.
Unsupported combinations fail explicitly instead of measuring one layout and
drawing another, or silently omitting a child of a specialized document.
"""
from geometry import metric, require_number
from reference_rules import TEXT_ROLES


POSITIVE_DIMENSIONS = frozenset({
    'width', 'height', 'font_size', 'line_height', 'body_width', 'body_bottom',
    'heading_size', 'instruction_font_size', 'instruction_line_height',
    'instruction_width', 'instruction_cells', 'reference_font_size',
    'reference_line_height', 'compound_intro_width', 'compound_followup_width',
    'material_line_height', 'material_intro_line_height', 'material_title_line_height',
    'material_note_line_height', 'material_box_stroke', 'vertical_font_size',
    'vertical_width', 'vertical_column_height', 'column_height', 'image_max_width',
    'table_font_size', 'table_line_height',
})
NONNEGATIVE_DIMENSIONS = frozenset({
    'indent', 'margin_top', 'margin_bottom', 'margin_left', 'margin_right',
    'material_box_outset', 'material_box_padding', 'material_box_top_padding',
    'material_box_bottom_padding', 'table_cell_padding_x', 'table_cell_padding_top',
    'table_cell_padding_bottom', 'choice_prompt_max_negative_tracking',
    'choice_option_max_negative_tracking', 'word_order_blank_max_negative_tracking',
    'instruction_first_line_max_negative_tracking',
    'instruction_max_positive_tracking',
    'group_gap',
})
FINITE_DIMENSIONS = frozenset({
    'left_odd', 'left_even', 'reference_outset', 'question_gap',
    'material_question_gap', 'citation_question_gap', 'material_wrapped_note_gap',
    'compound_intro_first_line_tracking', 'compound_question_gap',
    'memo_center_offset', 'memo_baseline_gap',
})
PARAGRAPH_ROLES = frozenset({'dialogue', 'quotation', 'continuation'})


def validate_rule_dimensions(config):
    for name in config.keys() & POSITIVE_DIMENSIONS:
        metric(config, name, None)
    for name in config.keys() & NONNEGATIVE_DIMENSIONS:
        metric(config, name, None, allow_zero=True)
    for name in config.keys() & FINITE_DIMENSIONS:
        require_number(config[name], f'{name} must be a finite number')


def validate_rule_content(group):
    """Roles describe block semantics, never item identities or source positions."""
    reading = group.get('id', '').startswith('R')

    def visit_item(item, path):
        if 'rule_style' in item:
            raise ValueError(f'{path}: rule_style belongs on a material block')
        visit_blocks(item.get('stimulus', []), path + '/stimulus')
        for key in ('items', 'questions'):
            for index, child in enumerate(item.get(key, [])):
                visit_item(child, f'{path}/{key}/{index}')

    def visit_blocks(blocks, path, *, parent=None, nested=False):
        for index, block in enumerate(blocks):
            location = f'{path}/{index}'
            kind, role = block.get('type'), block.get('rule_style')
            validate_rule_dimensions(block)
            if parent == 'guide':
                allowed = (kind in ('paragraph', 'heading') and (role is None or role in TEXT_ROLES)
                           or kind == 'table' and role in (None, 'guide_table'))
                if not allowed:
                    raise ValueError(f'{location}: guide supports text roles and tables only')
            elif role in PARAGRAPH_ROLES:
                if kind != 'paragraph':
                    raise ValueError(f'{location}: {role} requires a paragraph')
            elif role in ('contact', 'contact_detail'):
                if kind != 'paragraph' or parent != 'notice':
                    raise ValueError(f'{location}: {role} requires a paragraph directly inside a notice')
            elif role in ('notice', 'guide'):
                if kind != 'box' or not reading or nested:
                    raise ValueError(f'{location}: {role} requires a top-level reading box')
            elif role == 'figure_caption':
                if kind != 'paragraph' or nested:
                    raise ValueError(f'{location}: figure_caption requires a top-level paragraph')
                if index + 1 >= len(blocks) or blocks[index + 1].get('type') != 'image':
                    raise ValueError(f'{location}: figure_caption must immediately precede an image')
            elif role is not None:
                raise ValueError(f'{location}: unknown rule_style {role!r}')
            if kind == 'box':
                children = block.get('blocks', [])
                if any(child.get('type') == 'vertical' for child in children):
                    if any(child.get('type') not in ('vertical', 'paragraph') for child in children):
                        raise ValueError(f'{location}: vertical quotation supports vertical text and paragraph citations only')
                visit_blocks(children, location + '/blocks', parent=role, nested=True)
            if kind == 'table':
                weights = block.get('column_widths')
                if weights is not None:
                    if not isinstance(weights, list) or not weights:
                        raise ValueError(f'{location}: column_widths must be a nonempty list')
                    for weight in weights:
                        metric({'weight': weight}, 'weight', None)

    visit_item(group, group.get('id', 'group'))
