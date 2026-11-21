# QOL-KiCAD

Quality-of-life tools for KiCad's PCB editor. The first set makes board outline (Edge.Cuts) editing closer to sketching in Fusion 360.

Requires KiCad 9 or newer with the IPC API enabled (Preferences > Plugins > Enable KiCad API). Developed and tested on KiCad 10.

## Tools

All buttons appear in the PCB editor's top toolbar and work on Edge.Cuts lines, arcs, circles and rectangles. Each one is a single undo step.

| Button | What it does |
|---|---|
| Trim overhangs | Cuts the selected edges where other edges cross them and removes the overhanging ends. |
| Close & clean outline | Joins ends that nearly touch, removes duplicates and zero-length shapes, merges straight runs, and reports any remaining gaps. |
| Fillet all corners | Rounds every line-to-line corner of the outline (or the selection) with one radius. |
| Add outline shape | Adds a rounded rectangle or a slot (placed with the mouse), or a tab / notch on the selected edge. |
| Import DXF as outline | Reads a DXF onto Edge.Cuts and cleans it up: joins gaps, removes duplicates, turns runs of short segments back into arcs. |
| Live follow (toggle) | While on, edges joined to an edge or corner you move are re-attached when you release the mouse. |

Live follow reacts after the move, not during the drag: KiCad's plugin API has no access to the mouse. Undoing its step leaves the edges detached.

## Install

Copy or symlink this folder into KiCad's plugin directory and restart KiCad:

- Linux: `~/.local/share/kicad/10.0/plugins/`
- macOS: `~/Documents/KiCad/10.0/plugins/`
- Windows: `Documents\KiCad\10.0\plugins\`

KiCad creates a Python environment for the plugin and installs `requirements.txt` on first start; the buttons appear when that finishes.

## Development

```
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```

- `qol_kicad/geom.py`, `outline.py`, `generators.py`, `follow.py`: pure geometry, no KiCad needed.
- `qol_kicad/dxf.py`: DXF reader (ezdxf).
- `qol_kicad/kicad_io.py`, `actions.py`, `ui.py`: KiCad IPC bridge, the toolbar actions and their dialogs.
- `tests/test_smoke_pcbnew.py` needs KiCad's `pcbnew` module, so run the tests with the Python that KiCad uses (`/usr/bin/python3` on Linux); it is skipped otherwise.
- `tools/make_icons.py` regenerates `icons/`.
