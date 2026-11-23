# QOL-KiCAD

Quality-of-life tools for KiCad's PCB editor. The first set makes board outline (Edge.Cuts) editing closer to sketching in Fusion 360.

Requires KiCad 9 or newer with the IPC API enabled (Preferences > Plugins > Enable KiCad API). Developed and tested on KiCad 10.

## Tools

All buttons appear in the PCB editor's top toolbar and work on Edge.Cuts lines, arcs, circles and rectangles. Each one is a single undo step.

| Button | What it does |
|---|---|
| Sketch | Opens a sketch window to draw or import edges and puts them on the board as a group. See below. |
| Trim overhangs | Cuts the selected edges where other edges cross them and removes the overhanging ends. |
| Close & clean outline | Joins ends that nearly touch, removes duplicates and zero-length shapes, merges straight runs, and reports any remaining gaps. |
| Fillet all corners | Rounds every line-to-line corner of the outline (or the selection) with one radius. |
| Add outline shape | Adds a rounded rectangle or a slot (placed with the mouse), or a tab / notch on the selected edge. |
| Import DXF as outline | Reads a DXF onto Edge.Cuts and cleans it up: joins gaps, removes duplicates, turns runs of short segments back into arcs. |
| Live follow (toggle) | While on, edges joined to an edge or corner you move are re-attached when you release the mouse. |

Live follow reacts after the move, not during the drag: KiCad's plugin API has no access to the mouse. Undoing its step leaves the edges detached.

## Sketch

Sketch needs KiCad 10 or newer. It opens a separate drawing window. The board outline is shown as a dashed grey reference that you can snap to. **Insert as group** puts the sketch on the board as a group named `QOL sketch: <name>`, on the layer chosen in the window (Edge.Cuts by default).

To edit a group later, select it in the PCB editor and press Sketch. Its lines, arcs and circles open at their board position, and **Update group** replaces them in place. Any group of lines, arcs and circles can be opened this way, also one made by hand. Other members of the group (text, footprints, tracks) are left alone.

| Tool | Use |
|---|---|
| Select | Click or drag a box to select. Drag an edge or a corner to move it; joined edges follow. Delete removes the selection. |
| Line | Click points; click the first point to close. Type `25`, `25<30` (length<angle) or `10,-5` (dx,dy) and press Enter. |
| Arc, Tangent arc | Start, end, then a point on the arc. A tangent arc starts at the end of an existing edge. |
| Circle, Rectangle | Two clicks, or type the radius / `width,height`. |
| Trim, Extend | Click the piece to remove, or the end to lengthen to the next edge. |
| Fillet, Chamfer | Type the size in the Value box, then click a corner between two lines. |
| Offset, Mirror | Select edges first. Offset: type the distance and click the side. Mirror: click two points of the mirror line. |
| Dimension | Click a line or arc and type its new length or radius. |

**Import DXF** places a cleaned-up DXF in the sketch. **Add shape** places a rounded rectangle, slot or regular polygon. Points snap to ends, midpoints, centres, crossings, edges and the grid; hold Shift to lock horizontal or vertical. Scroll to zoom, drag with the right or middle button to pan, Ctrl/Cmd+Z to undo.

The sketch has no constraints: dimensions are applied when typed and not kept afterwards.

Undo in the PCB editor: a new group, or an edit that adds shapes, takes two undo steps (KiCad's plugin API cannot create shapes and group them in one step). Other edits are one step.

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
- `qol_kicad/sketch/`: the sketch window. `model.py` (shapes and edits) and `tools.py` (what clicks and typed values do) need no GUI; `window.py` is the wx canvas.
- `qol_kicad/kicad_io.py`, `actions.py`, `ui.py`: KiCad IPC bridge, the toolbar actions and their dialogs.
- `tests/test_smoke_pcbnew.py` needs KiCad's `pcbnew` module, so run the tests with the Python that KiCad uses (`/usr/bin/python3` on Linux); it is skipped otherwise.
- `tools/make_icons.py` regenerates `icons/`.
