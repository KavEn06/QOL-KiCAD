"""Small wx dialogs. KiCad's plugin environment provides wxPython."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

TITLE = "QOL-KiCAD"

# (key, label, default) where default is a float, bool, or list of choices (first is default)
Field = Tuple[str, str, Any]

_app = None


def _wx():
    global _app
    import wx

    if _app is None:
        _app = wx.App(False)
    return wx


def info(message: str) -> None:
    wx = _wx()
    wx.MessageBox(message, TITLE, wx.OK | wx.ICON_INFORMATION)


def error(message: str) -> None:
    wx = _wx()
    wx.MessageBox(message, TITLE, wx.OK | wx.ICON_ERROR)


def pick_file(message: str, wildcard: str) -> Optional[str]:
    wx = _wx()
    with wx.FileDialog(None, message, wildcard=wildcard, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
        return dlg.GetPath() if dlg.ShowModal() == wx.ID_OK else None


def ask(title: str, fields: Sequence[Field], saved: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Show a form and return {key: value}, or None if cancelled."""
    wx = _wx()
    saved = saved or {}
    dlg = wx.Dialog(None, title=f"{TITLE}: {title}")
    grid = wx.FlexGridSizer(cols=2, vgap=6, hgap=10)
    controls: List[Tuple[str, Any, Any]] = []
    for key, label, default in fields:
        grid.Add(wx.StaticText(dlg, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
        if isinstance(default, bool):
            ctrl = wx.CheckBox(dlg)
            ctrl.SetValue(bool(saved.get(key, default)))
        elif isinstance(default, list):
            ctrl = wx.Choice(dlg, choices=default)
            current = saved.get(key, default[0])
            ctrl.SetSelection(default.index(current) if current in default else 0)
        else:
            ctrl = wx.TextCtrl(dlg, value=f"{saved.get(key, default):g}")
        grid.Add(ctrl, 1, wx.EXPAND)
        controls.append((key, ctrl, default))
    outer = wx.BoxSizer(wx.VERTICAL)
    outer.Add(grid, 1, wx.ALL | wx.EXPAND, 12)
    outer.Add(dlg.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL | wx.EXPAND, 8)
    dlg.SetSizerAndFit(outer)
    dlg.CentreOnScreen()
    try:
        while dlg.ShowModal() == wx.ID_OK:
            try:
                out: Dict[str, Any] = {}
                for key, ctrl, default in controls:
                    if isinstance(default, bool):
                        out[key] = ctrl.GetValue()
                    elif isinstance(default, list):
                        out[key] = default[ctrl.GetSelection()]
                    else:
                        out[key] = float(ctrl.GetValue().replace(",", "."))
                return out
            except ValueError:
                error("Please enter numbers only.")
        return None
    finally:
        dlg.Destroy()
