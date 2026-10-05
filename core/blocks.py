"""The block library: ready-made pieces of drawing, one DXF file per block.

A block file is an ordinary drawing whose modelspace is the block and whose $INSBASE is
its base point - exactly what AutoCAD's WBLOCK writes - so anything saved out of AutoCAD
can be dropped into a library folder as it is. The file name is the block's name.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from ezdxf import recover
from ezdxf.document import Drawing

from core.dxf_document import INSUNITS_MILLIMETERS

BLOCK_FILE_SUFFIX = ".dxf"


def file_is_paper_sized(drawing: Drawing) -> bool:
    """Whether a block file is drawn in millimetres - a symbol meant for the paper, to be
    sized by the sheet's scale, rather than something at its true size on the ground."""
    return int(drawing.header.get("$INSUNITS", 0)) == INSUNITS_MILLIMETERS


@dataclass(frozen=True)
class LibraryBlock:
    name: str
    path: str


def library_blocks(directories: Iterable[str]) -> List[LibraryBlock]:
    """Every block file across `directories`, by name.

    Earlier directories win a name clash, so the app's own blocks cannot be shadowed by
    a same-named file the user happens to add later.
    """
    found: Dict[str, LibraryBlock] = {}
    for directory in directories:
        if not directory or not os.path.isdir(directory):
            continue
        for entry in os.listdir(directory):
            stem, suffix = os.path.splitext(entry)
            if suffix.lower() != BLOCK_FILE_SUFFIX or stem in found:
                continue
            path = os.path.join(directory, entry)
            if os.path.isfile(path):
                found[stem] = LibraryBlock(stem, path)
    return sorted(found.values(), key=lambda block: block.name.casefold())


_cache: Dict[str, Tuple[float, Drawing]] = {}


def read_block_file(path: str) -> Drawing:
    """The drawing inside a block file, parsed once for as long as the file is unchanged."""
    modified = os.path.getmtime(path)
    cached = _cache.get(path)
    if cached is not None and cached[0] == modified:
        return cached[1]
    drawing, _auditor = recover.readfile(path)
    _cache[path] = (modified, drawing)
    return drawing


def add_to_library(source_path: str, directory: str) -> LibraryBlock:
    """Copy a DXF file into a library folder, renaming it rather than overwriting."""
    os.makedirs(directory, exist_ok=True)
    stem = os.path.splitext(os.path.basename(source_path))[0]
    name, attempt = stem, 2
    while os.path.exists(os.path.join(directory, name + BLOCK_FILE_SUFFIX)):
        name = f"{stem} ({attempt})"
        attempt += 1
    target = os.path.join(directory, name + BLOCK_FILE_SUFFIX)
    read_block_file(source_path)  # refuse anything that is not a readable drawing
    shutil.copyfile(source_path, target)
    return LibraryBlock(name, target)
