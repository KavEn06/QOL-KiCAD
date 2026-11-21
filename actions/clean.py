import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qol_kicad.actions import run  # noqa: E402

run("clean")
