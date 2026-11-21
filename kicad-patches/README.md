# KiCad patches: joined Edge.Cuts shapes follow live

Patches against KiCad **10.0.8** (tag `10.0.8`) that change KiCad itself, not the plugin.
While you drag a point of a line or arc, or move shapes with the Move tool, other lines and arcs
on the same layer joined to them keep their ends attached live, in one undo step. Following arcs
keep their included angle (not their tangency). Locked shapes and other layers never follow.

Tested on Linux (Ubuntu 22.04) only.

## Build (Linux)

```sh
git clone --branch 10.0.8 https://gitlab.com/kicad/code/kicad.git && cd kicad
git am /path/to/QOL-KiCAD-/kicad-patches/*.patch
sudo apt-get build-dep kicad   # needs deb-src enabled for the kicad-10.0-releases PPA
sudo apt-get install ninja-build
mkdir build && cd build
cmake -G Ninja -DCMAKE_BUILD_TYPE=Release -DKICAD_BUILD_QA_TESTS=OFF -DKICAD_BUILD_I18N=OFF ..
ninja
KICAD_RUN_FROM_BUILD_DIR=1 ./pcbnew/pcbnew
```
