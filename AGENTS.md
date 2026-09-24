# AGENTS.md

Guidance for coding agents working in this repository.

## What this is

Geodetic Sketch Generator — a PyQt6 desktop app that turns geodetic survey point files (TXT) into
DXF drawings: point/line/pipe/height/cable-mark plotting from coordinate data, a CAD-like DXF
viewer/editor with undo/redo and an AutoCAD-style command line, multi-sheet layout with a
configurable title-block table, and PDF export. The repo name (AutocadScriptGenerator) predates
the current scope.

## Commands

- Run the app: `python main.py`
- Run tests: `python -m pytest -q`
- Run a single test: `python -m pytest tests/test_commands.py::test_add_point_command_execute_and_undo -q`
- Install deps: `pip install -r requirements.txt`
- Pre-commit hooks (trailing-whitespace/EOF/yaml/toml checks + a full pytest run):
  `pre-commit run --all-files` (not installed into `.git/hooks` in a fresh checkout — run manually
  or `pre-commit install` first)

Tests cover only `core/` and `models/` (command execute/undo, parsing, geometry/pattern math,
plot math, project and table-template JSON round-tripping). There's no pytest-qt; the `ui/` PyQt6
layer isn't exercised by the suite.

## Architecture

Three layers, dependencies flow one way: `models` → `core` → `ui`. `models` and `core` never
import `ui` or PyQt6 — that boundary is what keeps `core/` testable headlessly.

**models/** — `Point`, plain data.

**core/** — all business logic:
- `parser.py` — `PointFileParser` reads a geodetic point TXT file (space/tab-delimited,
  auto-detected, optional header row) into `Dict[int, Point]`.
- `dxf_document.py` — `DXFDocument` wraps an `ezdxf` `Drawing`; every DXF mutation (entities,
  layers, colors) goes through it rather than touching `ezdxf` directly.
- `commands/` — undo/redo Command pattern. `base.Command` is the `execute(doc)`/`undo(doc)`
  protocol; `history.CommandHistory` holds the undo/redo stacks (capped at
  `DEFAULT_MAX_DEPTH = 200`); `composite.CompositeCommand` groups several commands into one undo
  step. Concrete commands: `draw.py` (add point/line/circle/text/polyline), `edit.py`
  (move/rotate/scale/delete/duplicate), `layers.py`, `text.py` (entity text/color edits),
  `survey.py` (a registry of point-set-to-drawing builders keyed by `DrawMode`, looked up via
  `get_survey_builder`; the four label-bearing builders — points/heights/cable-marks/measurements
  — stage `LabelRequest`s instead of computing their own offsets, see `label_placement.py` below).
- `survey_draw_service.py` — `SurveyDrawService.build_command()` (single mode) and
  `build_commands()` (several modes at once, needed so label classes get solved together) are the
  entry points from parsed points + `GenerationConfig`(s) to `Command`(s), dispatching through
  `commands/survey.py::build_survey_commands`. Every batch is bracketed by
  `commands/generated.py`: a leading `DeleteGeneratedCommand` clears what an earlier run drew for
  the modes being generated, and each mode's draw command is wrapped in `MarkGeneratedCommand` so
  its output is stamped for the run after that. Generating twice therefore updates the sketch
  instead of stacking a second copy on it; modes not in the batch keep their entities, and so does
  anything the user drew by hand.
- `generated.py` — the stamp itself: `GSG_GENERATED` xdata naming the `DrawMode` that drew an
  entity, in the same shape as `multileader.py`/`detail_view.py` metadata. It lives in the drawing
  rather than in memory because it has to outlive both the undo history and a project save/reopen.
  `DXFDocument.mark_generated()` writes it, `generated_handles()` reads it back.
- `label_placement.py` — `solve_label_positions(labels, obstacles, marker_radius)` is the label
  coordinate solver: given every pending `LabelRequest` (across all label classes) plus
  `Obstacles` (marker circles, route segments) it returns a centre point and a hard-collision
  count per label. Ring/direction candidates around each anchor, an iterated-conditional-modes
  sweep, and a Voronoi-cell constraint (never closer to another label's anchor than to your own)
  keep it from just drifting outward to "solve" collisions. Pure geometry — no `ezdxf`, no
  `DXFDocument`, no `DrawMode` awareness. `commands/survey.py` is the only caller.
- `geometry.py` / `patterns.py` — direction/angle math between consecutive survey points and
  routed-path recognition (boxes/wedges) used by the survey builders.
- `draw_modes.py` / `config.py` — the `DrawMode` enum and the per-mode `*Options` dataclasses
  (`PointsOptions`, `HeightsOptions`, `CableOptions`, ...) that feed the survey builders.
- `session.py` — `EditorSession` holds the loaded point file and its parse result; `AppState`
  (EMPTY/READY/APPLIED/ERROR) is derived from it, not stored separately.
- `project.py` — `ProjectState` (plus nested `*State` dataclasses, one per mode/tab) is the full
  serializable app state; `save_project`/`load_project` read/write `.gsgproj` JSON.
  `open_any()` also accepts a bare `.dxf`/`.txt` for import.
- `table_template.py` — the title-block table model (`TableTemplate`: columns/rows/cells/fields).
  `.gsgtable` files save/load one independently of a project; `project.py` mirrors the same shape
  as `TableTemplateState` for embedding in `.gsgproj`.
- `sheets.py`, `plot.py` — sheet/layout state (`SheetSet`) and print/plot math (page sizing,
  scale, stroke width) that feeds PDF export.
- `validation.py`, `exceptions.py` — `AppError` subclasses raised by `core/`; the UI catches these
  at its boundary and shows the message instead of letting anything raw surface.

**ui/** — PyQt6, built around two top-level windows swapped via `window_router.py::WindowRouter`
(closes the old window, shows the new one — never both open at once):
- `start_screen.py` — recent-projects launcher (new/import/open).
- `editor/window.py::MainWindow` — the main editor. It composes controllers rather than doing the
  work itself: `DocumentController` (point/DXF file I/O), `ProjectController` (`.gsgproj`
  save/load/rename), `LayoutController` (sheets), `TableTemplateController`. The left-side option
  tabs (`editor/tabs/`) are driven by `editor/mode_registry.py::MODE_SPECS` — one entry per
  `DrawMode`, mapping a tab widget ↔ its `project.py` state dataclass ↔ its `config.py` options
  dataclass. Add a new draw mode there rather than hand-wiring a tab into `MainWindow`.
- `dxf/viewer.py::DxfViewer` — the CAD canvas. Owns the live `DXFDocument` + `CommandHistory`,
  renders it into a `QGraphicsScene` via ezdxf's drawing add-on through a custom
  `backend.py::QtSceneBackend`, and hosts the AutoCAD-style command line
  (`dxf/command_line.py` + `dxf/interpreter.py::DxfCommandInterpreter`, e.g. `LINE`, `MOVE`,
  `ROTATE`, `ZOOM`) alongside click-driven tool sessions (`dxf/tools/`) for the same operations.
- `dxf/pdf_export.py` — renders sheets (page frame + title-block table) to PDF using the plot
  options from `core/plot.py`.
- `theme/` — design tokens (`tokens.py`), a qtawesome-based `IconManager`, and the app stylesheet;
  pull spacing/color from here rather than hardcoding values in widget code.

## Conventions

- New code is comment-free and docstring-free — an intentional, already-applied project-wide
  style. Match it; don't add comments or docstrings to new code.
- Every module starts with `from __future__ import annotations`.
- User-facing failures are raised as `AppError` subclasses (`core/exceptions.py`), not generic
  exceptions, so the UI boundary can catch and display them by type.
