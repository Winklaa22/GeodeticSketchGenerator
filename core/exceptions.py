from __future__ import annotations


class AppError(Exception):
    """Base class for expected, user-facing application errors."""


class ParsingError(AppError):
    """Raised when the input point file cannot be parsed."""


class FileNotSelectedError(ParsingError):
    """Raised when no valid input file path was provided."""


class EmptyFileError(ParsingError):
    """Raised when the input file contains no non-blank lines."""


class NoValidPointsError(ParsingError):
    """Raised when no line in the input file could be parsed into a point."""


class ScriptGenerationError(AppError):
    """Raised when a script cannot be generated from the current inputs/config."""


class NoDataError(ScriptGenerationError):
    """Raised when script generation is attempted with no parsed points available."""


class InvalidLayerNameError(ScriptGenerationError):
    """Raised when the configured layer name is blank."""


class NoSelectionError(ScriptGenerationError):
    """Raised when no point numbers were selected for the script."""


class ProjectFileError(AppError):
    """Raised when a .gsgproj project file can't be read, written, or
    parsed (missing, corrupt, or an unsupported/future format version)."""
