# AutoCAD Script Generator PRO

A desktop tool that turns a plain-text list of surveyed points (number, X, Y, height) into an AutoCAD `.scr` script — ready to run inside AutoCAD to draw points, lines, polylines, height labels, and cable marks on a chosen layer.

## Features

- **Import** a whitespace/tab-delimited `.txt` file of points (`number  Y  X  H` — swapped to AutoCAD's `X  Y  H` on read), with auto-detected or manual delimiter and an optional header row.
- **Six drawing modes**, each a self-contained strategy:
  - `Points` — a `CIRCLE` per point, with optional point-number labels (offset away from the line of travel so labels don't overlap), plus a "cabinet mode" that shrinks the last 6 labels.
  - `Lines` — a `LINE` through the selected points.
  - `PLines` — a single 2D `PLINE` through the selected points.
  - `3DPOLY` — a single 3D polyline through the selected points.
  - `Heights marks` — a rounded elevation label placed near every Nth point.
  - `Cable marks` — a text mark placed at the midpoint of every Nth segment.
- **Point selection**: all points, a comma-separated list, or a numeric range.
- **Layer control**, with the last-used layer name remembered between sessions.
- **Live preview** of the generated script as options change.
- Copy the script to the clipboard, or save it directly as a `.scr` file.

## Project structure

```
main.py                 # entry point — launches the PyQt6 app
core/                    # UI-independent script-generation engine
  config.py              # GenerationConfig and per-mode option dataclasses
  parser.py              # PointFileParser — reads point files into Point objects
  selection.py           # SelectionParser — "all" / "1,2,3" / "1-7" selection syntax
  validation.py          # input validation (data, layer name, selection)
  geometry.py             # direction/angle math shared by several strategies
  draw_modes.py            # DrawMode enum and the ScriptDrawer strategy interface
  strategy_registry.py    # maps a DrawMode to its ScriptDrawer implementation
  script_builder.py        # assembles the final .scr text (header + strategy output)
  script_generator.py      # ScriptGenerator — orchestrates validation + building
  strategies/              # one ScriptDrawer per drawing mode
  exceptions.py            # user-facing AppError hierarchy
models/
  point.py                 # Point(x, y, h) value object
ui/                        # PyQt6 presentation layer, built on top of core/
  main_window.py           # MainWindow — wires widgets to core.ScriptGenerator
  style.py                 # application stylesheet
  tabs/                    # one tab widget per option group (delimiter, drawing
                            #   mode, points, heights, cable, selection, layer)
tests/                     # pytest suite for the core package
```

The split is deliberate: `core/` and `models/` have no PyQt import and no GUI dependency, so the whole generation pipeline (parsing → validation → strategy → script text) is unit-testable in isolation. `ui/` is a thin layer that collects input from widgets, builds a `GenerationConfig`, and calls `ScriptGenerator.generate(...)`.

## Requirements

- Python 3.10+ (developed/tested on 3.12)
- [PyQt6](https://pypi.org/project/PyQt6/)
- [pytest](https://pypi.org/project/pytest/) (for running tests)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running the app

```bash
python main.py
```

1. Click **Select input TXT file** and choose a points file (rows of `number Y X H`, space- or tab-delimited; a header row containing "numer"/"x"/"y" is auto-skipped).
2. Configure the **Delimiter & Source**, **Drawing**, **Points/Heights/Cable marks**, **Selection**, and **Layer** tabs as needed.
3. Click **Generate Script** (or let **Live preview** do it automatically).
4. **Copy** the script to the clipboard or **Save .scr** it, then run the resulting script inside AutoCAD (`SCRIPT` command) to draw the entities.

## Input file format

Each non-blank line is parsed as:

```
<number> <Y> <X> <H>
```

Commas are accepted as decimal separators and normalized to dots. Columns beyond the third (height) are optional and default to `0.0`. X and Y are swapped on read, since the source files store northing/easting in `(number, Y, X, H)` order while AutoCAD expects `(X, Y, H)`.

## Running tests

```bash
pytest
```

The suite covers `core/geometry.py`, `core/parser.py`, `core/script_generator.py`, `core/selection.py`, and `core/validation.py`.

## Extending with a new drawing mode

1. Add a value to `core.draw_modes.DrawMode`.
2. Implement a `ScriptDrawer` subclass in `core/strategies/` (see `point_list_drawer.py` for the simplest example, or `points_strategy.py` for one with its own options).
3. Register it in `core/strategy_registry.py`.
4. If it needs its own options, add a dataclass to `core/config.py`, wire it into `GenerationConfig`, and add a corresponding tab in `ui/tabs/` plus a radio button in `ui/tabs/draw_tab.py`.
