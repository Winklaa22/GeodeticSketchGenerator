from __future__ import annotations


class AppError(Exception):
    pass


class ParsingError(AppError):
    pass


class FileNotSelectedError(ParsingError):
    pass


class EmptyFileError(ParsingError):
    pass


class NoValidPointsError(ParsingError):
    pass


class ScriptGenerationError(AppError):
    pass


class NoDataError(ScriptGenerationError):
    pass


class InvalidLayerNameError(ScriptGenerationError):
    pass


class NoSelectionError(ScriptGenerationError):
    pass


class NoDrawModeError(ScriptGenerationError):
    pass


class ProjectFileError(AppError):
    pass
