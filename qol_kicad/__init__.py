"""QOL-KiCAD: quality-of-life tools for KiCad's PCB editor."""

import site
import sys

PLUGIN_ID = "com.github.kaven06.qol-kicad"

if sys.prefix != sys.base_prefix:
    # KiCad launches plugins with a PYTHONPATH that puts system packages ahead of
    # the plugin's own environment, so older system copies (e.g. pyparsing) win.
    _user = site.getusersitepackages()
    _own = [p for p in sys.path if p.startswith(sys.prefix)] + [p for p in sys.path if p == _user]
    sys.path[:] = _own + [p for p in sys.path if p not in _own]
