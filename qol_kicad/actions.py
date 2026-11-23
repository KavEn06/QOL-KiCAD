"""Toolbar actions. Each takes the board and optional parameters (in mm).

When ``params`` is None the user is asked through a dialog.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from typing import Any, Callable, Dict, List, Optional

from . import PLUGIN_ID, generators, outline, ui
from .follow import follow
from .geom import Line, Shape, bbox
from .kicad_io import EdgeSet, connect

MM = 1e6
TOUCH_TOL = 1000.0  # 1 um: ends closer than this count as touching

Params = Optional[Dict[str, Any]]


class UserError(Exception):
    """A problem the user can fix; shown as a message, not a crash."""


def _settings_file(kicad) -> str:
    folder = kicad.get_plugin_settings_path(PLUGIN_ID)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "settings.json")


def _ask(kicad, name: str, title: str, fields) -> Params:
    path = _settings_file(kicad)
    try:
        with open(path) as f:
            store = json.load(f)
    except (OSError, ValueError):
        store = {}
    values = ui.ask(title, fields, store.get(name))
    if values is not None:
        store[name] = values
        with open(path, "w") as f:
            json.dump(store, f, indent=2)
    return values


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def trim(kicad, board, params: Params = None) -> str:
    sel = EdgeSet.selected(board)
    if not sel.shapes:
        raise UserError("Select the Edge.Cuts lines or arcs to trim first.")
    everything = EdgeSet.all(board)
    others = [s for s in everything.shapes if s.ref not in sel.items]
    out, removed, split = outline.trim(sel.shapes, others, TOUCH_TOL)
    if not removed and not split:
        return "Nothing to trim: the selection does not cross any other board edge."
    sel.apply(out, "QOL: Trim")
    msg = f"Trimmed {_plural(removed, 'overhang')}."
    if split:
        msg += f" Split {_plural(split, 'shape')} at crossings; delete the piece you don't want."
    return msg


def clean(kicad, board, params: Params = None) -> str:
    if params is None:
        params = _ask(kicad, "clean", "Close & clean outline", [("tolerance", "Join gaps up to (mm)", 0.01)])
        if params is None:
            return ""
    edges = EdgeSet.selected_or_all(board)
    if not edges.shapes:
        raise UserError("There are no Edge.Cuts lines or arcs to clean.")
    out, rep = outline.clean(edges.shapes, params["tolerance"] * MM)
    edges.apply(out, "QOL: Close & clean outline")
    parts = [
        f"Joined {_plural(rep.joined, 'end')}, removed {_plural(rep.removed, 'duplicate or zero-length shape')}, "
        f"merged {_plural(rep.merged, 'continuation')}."
    ]
    if rep.is_closed:
        parts.append("The outline is closed.")
    else:
        if rep.open_ends:
            where = ", ".join(f"({x / MM:.3f}, {y / MM:.3f})" for x, y in rep.open_ends[:8])
            more = "" if len(rep.open_ends) <= 8 else f" and {len(rep.open_ends) - 8} more"
            parts.append(f"{_plural(len(rep.open_ends), 'open end')} at {where}{more} mm.")
        if rep.branches:
            parts.append(f"{_plural(len(rep.branches), 'point')} where more than two edges meet.")
    return "\n".join(parts)


def fillet(kicad, board, params: Params = None) -> str:
    if params is None:
        params = _ask(kicad, "fillet", "Fillet all corners", [("radius", "Radius (mm)", 1.0)])
        if params is None:
            return ""
    if params["radius"] <= 0:
        raise UserError("The radius must be greater than 0.")
    edges = EdgeSet.selected_or_all(board)
    out, done, skipped = outline.fillet_all(edges.shapes, params["radius"] * MM, TOUCH_TOL)
    if not done:
        return "No corners were filleted. Corners need two straight lines that are long enough for the radius."
    edges.apply(out, "QOL: Fillet all corners")
    msg = f"Filleted {_plural(done, 'corner')}."
    if skipped:
        msg += f" Skipped {skipped} (arc corners, or lines too short for the radius)."
    return msg


def _place(board, edges: EdgeSet, shapes: List[Shape], message: str, interactive: bool) -> None:
    created = edges.apply(edges.shapes + shapes, message)
    if interactive and created:
        board.interactive_move([item.id for item in created])


def _default_center(edges: EdgeSet):
    if edges.shapes:
        x0, y0, x1, y1 = bbox(edges.shapes)
        return ((x0 + x1) / 2, (y0 + y1) / 2)
    return (150 * MM, 100 * MM)


def generate(kicad, board, params: Params = None) -> str:
    if params is None:
        params = _ask(
            kicad,
            "generate",
            "Add outline shape",
            [
                ("shape", "Shape", ["Rounded rectangle", "Slot", "Tab / notch on selected line"]),
                ("width", "Width (mm)", 50.0),
                ("height", "Height / slot length / tab depth (mm)", 30.0),
                ("radius", "Corner radius (mm)", 2.0),
                ("vertical", "Slot: vertical", False),
                ("place", "Place with the mouse", True),
            ],
        )
        if params is None:
            return ""
    w, h, r = params["width"] * MM, params["height"] * MM, params.get("radius", 0) * MM
    kind = params["shape"]
    try:
        if kind.startswith("Tab"):
            sel = EdgeSet.selected(board)
            lines = [s for s in sel.shapes if isinstance(s, Line)]
            if len(sel.items) != 1 or len(lines) != 1:
                raise UserError("Select exactly one straight Edge.Cuts line for the tab.")
            everything = EdgeSet.all(board)
            index = next(i for i, s in enumerate(everything.shapes) if s.ref == lines[0].ref)
            tab = outline.add_tab(everything.shapes, index, w, h, tol=TOUCH_TOL)
            rest = [s for i, s in enumerate(everything.shapes) if i != index]
            everything.apply(rest + tab, "QOL: Add tab")
            return ""
        edges = EdgeSet.all(board)
        center = _default_center(edges)
        if kind == "Slot":
            shapes = generators.slot(center, h, w, params.get("vertical", False))
        else:
            shapes = generators.rounded_rect(center, w, h, r)
    except ValueError as e:
        raise UserError(str(e))
    _place(board, edges, shapes, f"QOL: Add {kind.lower()}", params.get("place", True))
    return ""


def import_dxf(kicad, board, params: Params = None) -> str:
    from .dxf import read_dxf

    if params is None:
        path = ui.pick_file("Import DXF as board outline", "DXF files (*.dxf)|*.dxf;*.DXF")
        if not path:
            return ""
        params = _ask(
            kicad,
            "import_dxf",
            "Import DXF as outline",
            [
                ("tolerance", "Join gaps up to (mm)", 0.01),
                ("fit", "Turn segment runs into arcs within (mm)", 0.005),
                ("unit", "If the file has no units, 1 unit = (mm)", 1.0),
                ("place", "Place with the mouse", True),
            ],
        )
        if params is None:
            return ""
        params["path"] = path
    try:
        raw, skipped = read_dxf(params["path"], params.get("unit", 1.0))
    except Exception as e:  # ezdxf raises several error types for bad files
        raise UserError(f"Could not read the DXF file:\n{e}")
    if not raw:
        raise UserError("The DXF has no lines, arcs, circles, polylines, splines or ellipses in model space.")
    tol = params.get("tolerance", 0.01) * MM
    shapes, _ = outline.clean(raw, tol)
    shapes, arcs = outline.refit_arcs(shapes, params.get("fit", 0.005) * MM, tol)
    shapes, rep = outline.clean(shapes, tol)
    edges = EdgeSet(board, [])
    _place(board, edges, shapes, "QOL: Import DXF as outline", params.get("place", True))
    msg = f"Imported {_plural(len(raw), 'DXF segment')} as {_plural(len(shapes), 'shape')}"
    msg += f" ({_plural(arcs, 'segment run')} turned into arcs)."
    if skipped:
        msg += f"\nSkipped {_plural(skipped, 'unsupported entity')} (text, hatches, dimensions...)."
    msg += "\nThe outline is closed." if rep.is_closed else (
        f"\nThe outline is not closed: {_plural(len(rep.open_ends), 'open end')}, "
        f"{_plural(len(rep.branches), 'branch point')}."
    )
    return msg


def _load_dxf(kicad):
    """Ask for a DXF file and its options. Returns (shapes, message), or None if cancelled."""
    from .dxf import read_dxf

    path = ui.pick_file("Import DXF into the sketch", "DXF files (*.dxf)|*.dxf;*.DXF")
    if not path:
        return None
    params = _ask(
        kicad,
        "sketch_dxf",
        "Import DXF",
        [
            ("tolerance", "Join gaps up to (mm)", 0.01),
            ("fit", "Turn segment runs into arcs within (mm)", 0.005),
            ("unit", "If the file has no units, 1 unit = (mm)", 1.0),
        ],
    )
    if params is None:
        return None
    try:
        raw, skipped = read_dxf(path, params["unit"])
    except Exception as e:  # ezdxf raises several error types for bad files
        ui.error(f"Could not read the DXF file:\n{e}")
        return None
    if not raw:
        ui.error("The DXF has no lines, arcs, circles, polylines, splines or ellipses in model space.")
        return None
    tol = params["tolerance"] * MM
    shapes, _ = outline.clean(raw, tol)
    shapes, _ = outline.refit_arcs(shapes, params["fit"] * MM, tol)
    shapes, _ = outline.clean(shapes, tol)
    message = f"Imported {_plural(len(shapes), 'shape')}. Click to place."
    if skipped:
        message += f" Skipped {_plural(skipped, 'unsupported entity')}."
    return shapes, message


def sketch(kicad, board, params: Params = None) -> str:
    """Open the sketch window on the selected group, or on a new sketch."""
    from .kicad_io import SketchTarget, drawing_layers, layer_name
    from .sketch.window import SketchFrame

    if kicad.get_version().major < 10:  # KiCad 9's API has no groups; shapes would be left ungrouped
        raise UserError("Sketch needs KiCad 10 or newer.")
    wx = ui._wx()
    target = SketchTarget.from_selection(board)
    layers = drawing_layers(board)
    if target.layer not in layers:
        layers.append(target.layer)

    def finish(shapes, layer_index, name) -> str:
        steps = target.write(shapes, layers[layer_index], name)
        if steps == 2:
            return "The sketch is on the board as a group.\nKiCad needed two undo steps for it: undo twice to take it back."
        return ""

    frame = SketchFrame(
        shapes=target.shapes,
        reference=target.reference(),
        layers=[layer_name(v) for v in layers],
        layer_index=layers.index(target.layer),
        name=target.name,
        editing=target.group is not None,
        on_finish=finish,
        ask=lambda key, title, fields: _ask(kicad, key, title, fields),
        read_dxf=lambda: _load_dxf(kicad),
    )
    frame.Show()
    frame.Raise()
    wx.CallAfter(ui.bring_to_front)
    wx.GetApp().MainLoop()
    return ""


def _ends(edges: EdgeSet):
    # rectangles expand to four shapes with one ref; live follow leaves them alone
    count = Counter(s.ref for s in edges.shapes)
    return {s.ref: (s.start, s.end) for s in edges.shapes if not s.closed and count[s.ref] == 1}


def follow_once(board, old, tol: float = TOUCH_TOL):
    """One live-follow step. Returns (ends as found, ends after following)."""
    edges = EdgeSet.all(board)
    found = _ends(edges)
    if old is None or found == old:
        return found, found
    fixes = follow(old, found, tol)
    if not fixes:
        return found, found
    edges.apply([s.with_ends(*fixes[s.ref]) if s.ref in fixes else s for s in edges.shapes], "QOL: Live follow")
    return found, _ends(EdgeSet.all(board))


def live_follow(kicad, board, params: Params = None) -> str:
    """Toggle a background loop that keeps joined board edges joined after you move one."""
    from kipy.errors import ApiError

    flag = os.path.join(os.path.dirname(_settings_file(kicad)), "live_follow.running")
    if os.path.exists(flag) and time.time() - os.path.getmtime(flag) < 5:
        os.remove(flag)  # the running loop sees this and stops
        return "Live follow is OFF."
    token = str(os.getpid())
    with open(flag, "w") as f:
        f.write(token)
    if params is None:
        ui.info(
            "Live follow is ON.\n\nMove a board edge or corner and the edges joined to it follow "
            "when you release the mouse. Click the button again to turn it off."
        )
    interval = (params or {}).get("interval", 0.25)
    old = None
    undone = None
    failures = 0
    try:
        while True:
            try:
                with open(flag) as f:
                    if f.read() != token:
                        break
            except OSError:
                break
            os.utime(flag)
            try:
                if undone is not None and _ends(EdgeSet.all(board)) == undone:
                    old, undone = undone, None  # the user undid our last step: leave it undone
                else:
                    found, old = follow_once(board, old)
                    if found != old:
                        undone = found
                failures = 0
            except ApiError:
                pass  # KiCad is busy (dragging, dialog open): try again shortly
            except Exception:
                failures += 1
                if failures > 20:
                    break  # KiCad has gone away
            time.sleep(interval)
    finally:
        try:
            with open(flag) as f:
                if f.read() == token:
                    os.remove(flag)
        except OSError:
            pass
    return ""


ACTIONS: Dict[str, Callable] = {
    "trim": trim,
    "clean": clean,
    "fillet": fillet,
    "generate": generate,
    "import_dxf": import_dxf,
    "live_follow": live_follow,
    "sketch": sketch,
}


def run(name: str) -> None:
    """Entry point used by the toolbar buttons."""
    try:
        kicad, board = connect()
        message = ACTIONS[name](kicad, board)
        if message:
            ui.info(message)
    except UserError as e:
        ui.error(str(e))
    except Exception as e:
        ui.error(f"{type(e).__name__}: {e}")
        raise
