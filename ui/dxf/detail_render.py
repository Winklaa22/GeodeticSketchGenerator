from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from ezdxf.addons.drawing import Frontend, RenderContext, recorder
from ezdxf.addons.drawing.config import Configuration
from ezdxf.math import Vec2

from core.detail_view import (
    DetailViewSpec,
    bounds,
    detail_matrix,
    metadata_from_entity,
    rotation_matrix,
)
from core.dxf_document import DXFDocument

CROP_PRECISION = 1e-4


def source_player(document: DXFDocument, config: Configuration) -> recorder.Player:
    rec = recorder.Recorder()
    frontend = Frontend(RenderContext(document.drawing), rec, config=config)
    frontend.draw_entities(
        [entity for entity in document.modelspace if metadata_from_entity(entity) is None]
    )
    rec.finalize()
    return rec.player()


def detail_players(
    document: DXFDocument,
    config: Configuration,
    specs: Optional[Sequence[Tuple[str, DetailViewSpec]]] = None,
) -> List[Tuple[str, DetailViewSpec, recorder.Player]]:
    entries = list(specs) if specs is not None else document.iter_detail_views()
    if not entries:
        return []
    base = source_player(document, config)
    players: List[Tuple[str, DetailViewSpec, recorder.Player]] = []
    for handle, spec in entries:
        player = base.copy()
        player.transform(detail_matrix(spec))
        (min_x, min_y), (max_x, max_y) = bounds(spec)
        # crop_rect only understands axis-aligned rectangles, so the frame is cropped
        # while it is still upright and the rotation is applied to the result.
        player.crop_rect(Vec2(min_x, min_y), Vec2(max_x, max_y), CROP_PRECISION)
        if spec.rotation:
            player.transform(rotation_matrix(spec))
        players.append((handle, spec, player))
    return players
