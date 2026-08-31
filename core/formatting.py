from __future__ import annotations

import os


def format_byte_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    kilobytes = num_bytes / 1024
    if kilobytes < 1024:
        return f"{kilobytes:.0f} KB"
    return f"{kilobytes / 1024:.1f} MB"


def format_file_size(path: str) -> str:
    try:
        return format_byte_size(os.path.getsize(path))
    except OSError:
        return ""
