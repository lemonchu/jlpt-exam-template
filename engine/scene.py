"""Place a measured scene fragment relative to an anchor.

Callers use top-left bp coordinates. Runs and images in the stored PDF scene
use bottom-left coordinates; this is the one boundary that converts them.
"""
from copy import deepcopy


def place_fragment(commands, *, source_origin, target_origin, page_height,
                   clip, run_ids, include_images=False):
    """Copy selected text and clipped artwork to a new component origin.

    ``clip`` is (left, top, width, height) in the source page. Only artwork is
    clipped: selected text already belongs to the component and its ruby may
    extend above the frame. Vector chunks share one graphics-state scope,
    since a later chunk can rely on an earlier line width or dash setting.
    """
    dx = target_origin[0] - source_origin[0]
    dy = target_origin[1] - source_origin[1]
    left, top, width, height = clip
    vectors = '\n'.join(c['pdf'] for c in commands if c['type'] == 'vector')
    placed = []
    if vectors:
        placed.append({'type': 'vector', 'pdf': (
            f'q 1 0 0 1 {dx:.12g} {-dy:.12g} cm '
            f'{left:.12g} {page_height-top-height:.12g} {width:.12g} {height:.12g} re W n\n'
            + vectors + '\nQ'
        )})
    for source in commands:
        kind = source['type']
        if kind == 'ink':
            placed.append(deepcopy(source))
        elif ((kind == 'run' and source['run_id'] in run_ids)
              or (kind == 'image' and include_images)):
            command = deepcopy(source)
            command['x'] += dx
            command['y'] -= dy
            placed.append(command)
    return placed
