from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import Configuration

from core.dxf_document import DXFDocument
from ui.dxf.backend import QtSceneBackend

_DXF_RENDER_PX = 512
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}


class StampCache:

    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[float, Optional[qg.QPixmap]]] = {}

    def get(self, path: str) -> Optional[qg.QPixmap]:
        if not path:
            return None
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return None
        cached = self._cache.get(path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        pixmap = self._load(path)
        self._cache[path] = (mtime, pixmap)
        return pixmap

    def _load(self, path: str) -> Optional[qg.QPixmap]:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".dxf":
            return self._load_dxf(path)
        if ext in _IMAGE_EXTENSIONS:
            pixmap = qg.QPixmap(path)
            return pixmap if not pixmap.isNull() else None
        return None

    @staticmethod
    def _load_dxf(path: str) -> Optional[qg.QPixmap]:
        try:
            document = DXFDocument.load(path)
            scene = qw.QGraphicsScene()
            backend = QtSceneBackend(scene)
            context = RenderContext(document.drawing)
            Frontend(context, backend, config=Configuration()).draw_layout(
                document.modelspace, finalize=True
            )
            bounds = scene.itemsBoundingRect()
            if bounds.isEmpty():
                return None
            scene.setBackgroundBrush(qg.QBrush(qc.Qt.BrushStyle.NoBrush))
            aspect = bounds.width() / bounds.height() if bounds.height() else 1.0
            if aspect >= 1.0:
                width, height = _DXF_RENDER_PX, max(1, round(_DXF_RENDER_PX / aspect))
            else:
                width, height = max(1, round(_DXF_RENDER_PX * aspect)), _DXF_RENDER_PX
            image = qg.QImage(width, height, qg.QImage.Format.Format_ARGB32)
            image.fill(qg.QColor(0, 0, 0, 0))
            painter = qg.QPainter(image)
            painter.setRenderHint(qg.QPainter.RenderHint.Antialiasing)
            # DXF world coordinates are Y-up (higher y = visually higher), while
            # QGraphicsScene.render() maps its source rect onto the target rect axis-for-axis
            # with no such flip, so without correction the rendered raster comes out upside
            # down. Flip the painter's Y axis first so the mapping comes out right-side up.
            painter.translate(0, height)
            painter.scale(1.0, -1.0)
            scene.render(painter, qc.QRectF(0.0, 0.0, width, height), bounds)
            painter.end()
            return qg.QPixmap.fromImage(image)
        except Exception:
            return None


stamp_cache = StampCache()
