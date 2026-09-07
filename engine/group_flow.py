"""Measure a group's opening unit without rendering a disposable page.

``minimum`` is the first hard keep; ``preferred`` also honors the renderer's
optional whole-question/frame keep. A caller may relax that optional keep only
when the heading and preferred unit cannot fit together on a fresh page.
"""
from contextlib import contextmanager

from inline import plain
from reading_rules import cloze_frame, notice_frame, row_ink_height


def keep(minimum=0.0, preferred=None, *, break_before=False, **details):
    return dict(minimum=minimum, preferred=minimum if preferred is None else max(minimum, preferred),
                break_before=break_before, **details)


def prefix_keep(height, plan):
    return {**plan, 'minimum': height + plan['minimum'],
            'preferred': height + plan['preferred']}


class GroupFlow:
    """Opening-only plans; no numbering, page, or scene state is advanced."""

    @contextmanager
    def _opening_context(self, **changes):
        missing = object()
        saved = {name: getattr(self, name, missing) for name in changes}
        try:
            for name, value in changes.items():
                setattr(self, name, value)
            yield
        finally:
            for name, value in saved.items():
                if value is missing:
                    delattr(self, name)
                else:
                    setattr(self, name, value)

    def first_item_keep(self, group, config):
        items = group.get('items', [])
        if not items:
            return keep()
        item = items[0]
        kind = group['kind']
        if config.get('layout') == 'facing_pages':
            # The orchestration layer must also retain the left-page parity.
            return keep(break_before=True)
        if kind == 'word_order':
            fixed = self.ordering_example_plan(item)
            if fixed is not None:
                return keep(fixed['advance'])
        if kind in ('choice', 'word_order'):
            return self._opening_choice_keep(item)
        if kind == 'listening_choice':
            if not item.get('is_example'):
                # Ordinary listening panels deliberately start a content page.
                return keep(break_before=True)
            return self._opening_listening_panel(item)
        if kind in ('listening_compound', 'listening_memo'):
            label = 40.8439 - 11.3 if item.get('label') and kind != 'listening_memo' else 0
            blocks = item.get('stimulus', [])
            if blocks:
                return prefix_keep(label, self.opening_blocks_keep(blocks, self.width, listening=True))
            questions = item.get('questions', [])
            if questions:
                return prefix_keep(label + float(config.get('compound_question_gap', 21.606)),
                                   self._opening_listening_panel(questions[0], compound=True))
            return keep(label)
        if kind not in ('reading', 'cloze'):
            raise ValueError('Unsupported group opening kind: ' + str(kind))
        label = (len(self.hanging_lines(str(item['label']), 11.3, self.width, self.width)) * 24.06
                 if item.get('label') else 0)
        with self._opening_context(_last_was_note=False, _last_note_wrapped=False,
                                   _last_material_kind=None, _contact_detail_inset=0.0,
                                   _rule_material_style=None, _cloze_material_depth=0,
                                   _rule_reading_block=None):
            blocks = item.get('stimulus', [])
            if blocks:
                return prefix_keep(label, self.opening_blocks_keep(blocks, self.width))
            questions = item.get('questions', [])
            if questions and config.get('questions_new_page', kind == 'cloze'):
                return keep(label, break_before=True)
            if questions:
                return prefix_keep(label + float(config.get('material_question_gap', 24.06)),
                                   self._opening_choice_keep(questions[0]))
        return keep(label)

    def _opening_choice_keep(self, item):
        plan = self.choice_metrics(item)
        label = item.get('label')
        if label is None and item.get('is_example'):
            label = '例'
        numeric = label is None or str(label).isascii() and str(label).isdigit()
        minimum = plan['lead'] * (1 if numeric else 2)
        preferred = plan['total'] if plan['total'] <= self.usable else minimum
        return keep(minimum, preferred, choice_plan=plan, choice_item=item)

    def _opening_listening_panel(self, item, compound=False):
        plan = self.listening_panel_metrics(item, compound=compound)
        return keep(max(plan['ink_height'], plan['advance']),
                    listening_plan=plan, listening_item=item)

    def opening_blocks_keep(self, blocks, width, *, listening=False):
        """Keep leading labels/blank separators with the first real material."""
        before = 0.0
        for index, block in enumerate(blocks):
            kind = block.get('type')
            if kind == 'separator':
                before += 24.06
                continue
            if kind in ('paragraph', 'heading') and not plain(block.get('text', '')).strip():
                before += 25.47 if listening else self.estimate_block(block, width)
                continue
            if block.get('rule_style') == 'figure_caption':
                if index + 1 == len(blocks) or blocks[index + 1].get('type') != 'image':
                    raise ValueError('figure_caption must immediately precede an image')
                plan = self.figure_plan(block, blocks[index + 1])
                return prefix_keep(before, keep(plan['total']))
            if (not listening and self._uses_reading_spacing() and kind == 'heading'
                    and index + 1 < len(blocks) and blocks[index + 1].get('type') == 'box'):
                frame = dict(blocks[index + 1], _reading_ab=True)
                return prefix_keep(before + 19.03, self.opening_block_keep(frame, width))
            if listening and kind in ('paragraph', 'heading'):
                return keep(before + 25.47)
            plan = self.opening_block_keep(block, width)
            if self._uses_reading_spacing() and kind == 'paragraph':
                if self._is_note(block):
                    end = index + 1
                    while end < len(blocks) and blocks[end].get('type') == 'paragraph' and self._is_note(blocks[end]):
                        end += 1
                    height = self.reading_sequence_height(blocks[index:end], width)
                    if height <= self.usable:
                        plan = keep(height)
                elif (index + 1 < len(blocks) and plan.get('row_count', 0) <= 2
                      and blocks[index + 1].get('style') == 'small'
                      and blocks[index + 1].get('align') == 'right'):
                    height = self.reading_sequence_height(blocks[index:index + 2], width)
                    if height <= self.usable:
                        plan = keep(height)
            return prefix_keep(before, plan)
        return keep(before)

    def opening_block_keep(self, block, width):
        """Reuse the actual block plans, distinguishing flowing and rigid units."""
        kind = block.get('type')
        if kind in ('paragraph', 'heading'):
            with self._opening_context(_rule_reading_block=block):
                if self._uses_reading_spacing():
                    _, inner = self._material_geometry(block, self.left, width)
                    size, leading, bold, _, _, align, indent, before = self.paragraph_spec(block, inner)
                    text = self.paragraph_body_text(block)
                    rows = self._reading_rows(text, inner, size, bold, align, indent)
                    ink = row_ink_height(rows[0], size) if rows else 0
                    if getattr(self, '_rule_material_style', None) == 'notice' and kind == 'heading':
                        ink = max(ink, size + 7.2)
                    return keep(before + ink, row_count=len(rows))
                _, leading, _, _, _, _, _, before = self.paragraph_spec(block, width)
                return keep(before + leading)
        if kind == 'memo':
            height = (self.listening_memo_height(block) if self.section == 'L'
                      else min(float(block.get('height', 260)), self.usable))
            return keep(height)
        if kind == 'table':
            _, inner = self.table_geometry(block, 0, width)
            plan = self.table_rows(block, inner)
            heights = plan[1]
            count = min(len(heights), int(block.get('header_rows', 0)) + 1)
            return keep(sum(heights[:count]))
        if kind == 'image':
            _, _, height = self.image_geometry(block, width)
            return keep(min(height, self.usable) + 4)
        if kind == 'box' and self._has_vertical(block):
            plan = self.vertical_plan(block)
            return keep(plan['before'] + plan['height'] + plan['after'])
        if kind == 'box' and block.get('rule_style') == 'guide':
            plan = self.guide_plan(block, width)
            return keep(plan.height + 1.3532)
        if kind == 'box':
            reading = self._uses_reading_spacing()
            special = self._is_cloze() or block.get('rule_style') == 'notice'
            if special:
                frame = cloze_frame(self.gc) if self._is_cloze() else notice_frame(self.gc)
                inner = width + frame.outset_left + frame.outset_right - frame.inset_left - frame.inset_right
                with self._opening_context(_cloze_material_depth=getattr(self, '_cloze_material_depth', 0) + int(self._is_cloze()),
                                           _rule_material_style=block.get('rule_style'),
                                           _contact_detail_inset=0.0):
                    child = self.opening_blocks_keep(block.get('blocks', []), inner)
                child_keep = child['preferred'] if child.get('split_block') is not None else child['minimum']
                minimum = frame.before + frame.top + max(2 * self.leading, child_keep)
            else:
                inner = self.box_width(block, width)
                inset, top, _, _ = self.reading_box_padding(block) if reading else (8, 8, 8, 6)
                child = self.opening_blocks_keep(block.get('blocks', []), inner - 2 * inset)
                child_keep = child['preferred'] if child.get('split_block') is not None else child['minimum']
                minimum = top + max(2 * self.leading + 8, child_keep)
            preferred = self.estimate_block(block, width)
            if preferred <= self.usable:
                minimum = min(minimum, preferred)
            else:
                preferred = minimum
            return keep(minimum, preferred, split_block=block, split_minimum=minimum)
        if kind == 'vertical':
            # Bare vertical columns use another renderer and are not a framed
            # quotation. Preserve its conservative first column-batch keep.
            return keep(self.estimate_block(block, width))
        raise ValueError('Unsupported opening material type: ' + str(kind))
