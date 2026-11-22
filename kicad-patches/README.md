# KiCad patches: joined Edge.Cuts shapes follow live

Patches against KiCad **10.0.8** (tag `10.0.8`) that change KiCad itself, not the plugin.
While you drag a point of a line or arc, or move shapes with the Move tool, other lines and arcs
on the same layer joined to them keep their ends attached live, in one undo step. Following arcs
keep their included angle (not their tangency). Locked shapes and other layers never follow.

Tested on Linux (Ubuntu 22.04) and Windows x64 (built and GUI-tested on Windows Server 2022, build 20348).

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

## Build (Windows 11, x64)

Built natively on Windows with [MSYS2](https://www.msys2.org/) **UCRT64** (GCC 16, wxWidgets 3.2.11,
OpenCASCADE 7.9.3, nng 1.12, Python 3.14), the same toolchain and dependencies as MSYS2's own
`mingw-w64-ucrt-x86_64-kicad` 10.0.8 package, not MSVC/vcpkg (which builds every dependency from
source and takes hours longer). MSYS2's MinGW patches for that package are applied too. The result
is the full suite (KiCad, PCB Editor, Schematic Editor, GerbView, ...) for **x64**, runs on
**Windows 10 or 11** (64-bit; MSYS2 UCRT binaries need Windows 10+). Building takes ~45 min on 8 cores and ~15 GB.

Scripts are in `windows/`:

- `build.sh`: configures and builds KiCad (Release, `KICAD_BUILD_I18N=OFF`, no QA tests) in `$WORK/build`.
- `package.sh`: installs into a portable tree (`$WORK/dist/KiCad-10.0.8-qol-win64`), adds the stock
  symbol/footprint/template libraries, a trimmed Python 3.14 + wxPython, ngspice, and every MinGW
  DLL found by `ntldd`, then zips it. The 3D model library (multi-GB) is **not** included: the 3D
  viewer shows no component models.
  IPC-API (new-style) Python plugins cannot create their environment with this MSYS2 Python
  (its venvs use `bin\` but KiCad looks for `Scripts\pythonw.exe`); legacy SWIG plugins work.
- `kicad-qol.nsi`: optional NSIS installer around that tree (Start Menu shortcuts + uninstaller).

```sh
# 1. Install MSYS2 to C:\msys64, open "MSYS2 UCRT64", then:
pacman -Syu   # repeat until nothing is left to update
P=mingw-w64-ucrt-x86_64
pacman -S --needed git base-devel $P-toolchain $P-cmake $P-ninja $P-pkgconf $P-boost $P-doxygen $P-swig \
  $P-abseil-cpp $P-cairo $P-curl $P-freeglut $P-glew $P-glm $P-nng $P-protobuf $P-libgit2 $P-ngspice \
  $P-python $P-opencascade $P-openssl $P-wxPython $P-wxwidgets3.2-msw $P-wxwidgets3.2-msw-libs $P-zlib \
  $P-kicad-footprints $P-kicad-symbols $P-kicad-templates $P-ntldd $P-7zip $P-nsis

# 2. Patched source: KiCad 10.0.8 + these patches + MSYS2's MinGW patches
export WORK=/c/kb && mkdir -p $WORK && cd $WORK
git clone --depth 1 --branch 10.0.8 https://gitlab.com/kicad/code/kicad.git
git clone --depth 1 --filter=blob:none --sparse https://github.com/msys2/MINGW-packages.git
(cd MINGW-packages && git sparse-checkout set mingw-w64-kicad)
cd kicad
git am /path/to/QOL-KiCAD/kicad-patches/*.patch
for p in 002 003 004 006 007 009; do patch -Np1 -i ../MINGW-packages/mingw-w64-kicad/$p-*.patch; done
cd ..

# 3. Build, package (zip), optional installer
bash /path/to/QOL-KiCAD/kicad-patches/windows/build.sh
bash /path/to/QOL-KiCAD/kicad-patches/windows/package.sh
makensis -DSRC='C:\kb\dist\KiCad-10.0.8-qol-win64' \
  -DOUTFILE='C:\kb\dist\KiCad-10.0.8-qol-win64-setup.exe' /path/to/QOL-KiCAD/kicad-patches/windows/kicad-qol.nsi
```

MSYS2's patches 001 (Clang 23) and 010 (clangarm64) are only for the Clang environments and are
not needed for UCRT64 (GCC).

### Running it

Unzip `KiCad-10.0.8-qol-win64.zip` anywhere and run `bin\kicad.exe` (or `bin\pcbnew.exe`), or run
the installer. It is a separate install from an official KiCad and shares its user settings
(`%APPDATA%\kicad\10.0`).

The build is not code-signed, so Windows SmartScreen warns when you run the installer or a
downloaded exe: click **More info** > **Run anyway**. Windows may also mark files from a
downloaded zip as blocked; right-click the zip > **Properties** > **Unblock** before extracting.
