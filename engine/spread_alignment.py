"""Keep a multi-page reading unit on an opening left-hand page.

Measure the whole passage and its questions using the real renderer.  The
preview owns its drawing state: it cannot consume question numbers or leave
glyphs behind in the final scene.  No text spacing is changed to fit a spread.
"""
import copy


class SpreadAlignment:
    def _aligns_reading_spreads(self):
        return (bool(getattr(self, 'reading_interleaf', None))
                and not getattr(self, '_pagination_preview', False)
                and self.section in ('G', 'R')
                and self.group.get('kind') in ('reading', 'cloze')
                and self.gc.get('layout') != 'facing_pages')

    def _spread_preview(self):
        probe = copy.copy(self)
        # Earlier pages are immutable during passage rendering. Keep their
        # indices without copying thousands of previously composed glyphs.
        probe.pages = [None] * (len(self.pages) - 1) + [copy.deepcopy(self.page)]
        probe.page = probe.pages[-1]
        probe.resolved = {}
        probe.semantic_glyphs = []
        probe.item_records = []
        probe.component_audit = []
        probe.material_spread_audit = []
        probe.assets = set(self.assets)
        probe.image_sizes = dict(self.image_sizes)
        probe._pagination_preview = True
        probe._first_group_item = True
        return probe

    @staticmethod
    def _first_new_ink(layout, page_index, command_count):
        for index in range(page_index, len(layout.pages)):
            commands = layout.pages[index]['commands']
            if index == page_index:
                commands = commands[command_count:]
            if any(c.get('type') in ('run', 'vector', 'image') for c in commands):
                return layout.start_page + index
        return layout.n()

    def _spread_extent(self, item, *, with_heading=False):
        probe = self._spread_preview()
        page_index, command_count = len(probe.pages) - 1, len(probe.page['commands'])
        if with_heading:
            probe.group_heading(self.group, self.gc)
            probe.y += float(self.gc.get('body_start_adjust', 0))
        probe.passage(item)
        return self._first_new_ink(probe, page_index, command_count), probe.n()

    def _reading_pattern(self):
        # A same-page group can follow existing content; never cover that
        # content with a filler. Its new left page needs no extra blank page.
        if self.page['commands']:
            return None
        page_number = self.n()
        scale = min(1, self.width / 452.41, (self.usable - 4) / 708.96)
        self.image({'asset': self.reading_interleaf,
                    'width': 452.41 * scale, 'height': 708.96 * scale},
                   self.left, self.width)
        return page_number

    def begin_group(self, group, config):
        previous_page = self.page
        previous_furniture = (copy.deepcopy((self.page['group_ids'], self.page['bands']))
                              if self.page is not None else None)
        self.prepare_group_page(group, config)
        self._group_pattern_page = None
        items = group.get('items', [])
        if self._aligns_reading_spreads() and items and self.n() % 2:
            start, end = self._spread_extent(items[0], with_heading=True)
            if end > start:
                self._group_pattern_page = self._reading_pattern()
                if self.page is previous_page and previous_furniture is not None:
                    # prepare_group_page may have registered a same-page group
                    # before the full-unit preview moved it to a new page.
                    self.page['group_ids'], self.page['bands'] = previous_furniture
                # Recompute the heading and its opening keep for the fresh page.
                # This runs before any heading ink has been emitted.
                self.prepare_group_page(group, dict(config, new_page=True))

    def begin_passage(self, item):
        super().begin_passage(item)
        first = getattr(self, '_first_group_item', False)
        self._passage_pattern_page = self._group_pattern_page if first else None
        if (not first and self._aligns_reading_spreads()
                and (self.n() % 2 or self.page['commands'])):
            start, end = self._spread_extent(item)
            if end > start and start % 2:
                # A same-page item may fit no ink on the current left page and
                # naturally begin on the next right page. Align that real
                # starting page, not the page preceding ensure().
                while self.n() < start:
                    self.new_page()
                self._passage_pattern_page = self._reading_pattern()
                self.new_page()
        self._passage_ink_start = len(self.pages) - 1, len(self.page['commands'])

    def passage(self, item):
        if (getattr(self, '_pagination_preview', False)
                or self.section not in ('G', 'R')):
            return super().passage(item)
        facing = self.gc.get('layout') == 'facing_pages'
        first = getattr(self, '_first_group_item', False)
        heading_page = self.n()
        super().passage(item)
        if not hasattr(self, 'material_spread_audit'):
            self.material_spread_audit = []
        self.material_spread_audit.append({
            'group': self.group['id'], 'item': item.get('id'),
            'start_page': (self.n() - 1 if facing else
                           heading_page if first else
                           self._first_new_ink(self, *self._passage_ink_start)),
            'end_page': self.n(),
            'pattern_page': None if facing else self._passage_pattern_page,
            'layout': 'facing_pages' if facing else 'flow',
        })
