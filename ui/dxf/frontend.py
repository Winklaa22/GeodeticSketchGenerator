from __future__ import annotations

from typing import Iterator

from ezdxf.addons.drawing import Frontend
from ezdxf.addons.drawing.config import TextPolicy
from ezdxf.addons.drawing.properties import Properties
from ezdxf.entities import DXFGraphic
from ezdxf.lldxf.const import MTEXT_BG_COLOR, MTEXT_BG_WINDOW_COLOR, MTEXT_TEXT_FRAME

_CANVAS_FILL = MTEXT_BG_WINDOW_COLOR & ~MTEXT_BG_COLOR


def _has_mask(entity: DXFGraphic) -> bool:
    mtext = entity.context.mtext
    return mtext is not None and bool(mtext.has_bg_fill)


def _decorated_parts(entity: DXFGraphic, framed: bool, masked: bool) -> Iterator[DXFGraphic]:
    for part in entity.virtual_entities():
        if part.dxftype() == "MTEXT":
            bg_fill = part.dxf.get("bg_fill", 0)
            if masked:
                bg_fill = (bg_fill & ~_CANVAS_FILL) | MTEXT_BG_COLOR
            if framed:
                bg_fill |= MTEXT_TEXT_FRAME
            part.dxf.bg_fill = bg_fill
            if not part.dxf.hasattr("box_fill_scale"):
                part.dxf.box_fill_scale = 1.5
        yield part


class GsgFrontend(Frontend):

    def draw_composite_entity(self, entity: DXFGraphic, properties: Properties) -> None:
        if entity.dxftype() == "MULTILEADER":
            framed = bool(entity.dxf.get("has_text_frame", 0))
            masked = _has_mask(entity)
            if framed or masked:
                self.draw_entities(_decorated_parts(entity, framed, masked))
                return
        super().draw_composite_entity(entity, properties)

    def draw_mtext_entity(self, entity: DXFGraphic, properties: Properties) -> None:
        if entity.dxf.get("bg_fill", 0) and self.config.text_policy != TextPolicy.IGNORE:
            self.draw_complex_mtext(entity, properties)
            return
        super().draw_mtext_entity(entity, properties)
