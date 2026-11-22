# KiCad patches: joined Edge.Cuts shapes follow live

Patches against KiCad **10.0.8** (tag `10.0.8`) that change KiCad itself, not the plugin.
While you drag a point of a line or arc, or move shapes with the Move tool, other lines and arcs
on the same layer joined to them keep their ends attached live, in one undo step. Following arcs
keep their included angle (not their tangency). Locked shapes and other layers never follow.

Tested on Linux (Ubuntu 22.04), on macOS 26 (Apple Silicon; the macOS build targets macOS 15 and later),
and on Windows x64 (built and GUI-tested on Windows Server 2022, build 20348).

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

## Build (macOS, Apple Silicon)

Built with [kicad-mac-builder](https://gitlab.com/kicad/packaging/kicad-mac-builder) (`10.0` branch,
commit `0977c0f`) on macOS 26.6 / Xcode 26.6. The result is a full `KiCad.app` (KiCad, PCB Editor,
Schematic Editor, ...) for **arm64**, minimum **macOS 15.0** (Sequoia). The build takes a few hours and
needs ~40 GB free.

The app bundles Homebrew's libraries, and Homebrew installs the build for the Mac it runs on. To make
the app run on macOS 15 when building on macOS 26, `macos/pour-sequoia-bottles.py` swaps those kegs for
Homebrew's published `arm64_sequoia` bottles (installed and bottle versions must match). If you build
on macOS 15 itself, skip that step.

`macos/kicad-mac-builder-10.0.patch` fixes the builder for current Homebrew/Xcode:

- nng: KiCad 10.0 needs nng 1.x but Homebrew ships 2.x, so a local nng 1.x is used via `KMB_NNG_PREFIX`.
- ngspice: adds `-Wno-invalid-specialization` (newer Clang rejects ngspice's `is_compound` specialisation) and passes `-mmacosx-version-min` (otherwise it targets the build Mac's macOS).
- packages3D: skips the multi-GB 3D model library (3D viewer shows no models; everything else works).

```sh
# 1. Tools
xcode-select --install
sudo softwareupdate --install-rosetta --agree-to-license   # the bundled doxygen is x86_64
git clone -b 10.0 https://gitlab.com/kicad/packaging/kicad-mac-builder.git ~/kicad-mac-builder
cd ~/kicad-mac-builder
git apply /path/to/QOL-KiCAD/kicad-patches/macos/kicad-mac-builder-10.0.patch
ci/arm64-on-arm64/bootstrap-arm64-on-arm64.sh                # Homebrew deps
mkdir -p ~/kmb-tools && (cd ~/kmb-tools && ~/kicad-mac-builder/ci/src/get-wrangle-bundle.sh)
/path/to/QOL-KiCAD/kicad-patches/macos/pour-sequoia-bottles.py abseil boost brotli cairo fontconfig \
  freetype gettext glib graphite2 harfbuzz icu4c@79 libgit2 libpng libssh2 libtool libx11 libxau libxcb \
  libxdmcp libxext libxrender llhttp opencascade openssl@3 openssl@4 pcre2 pixman protobuf tbb unixodbc \
  zstd glew libomp

# 2. nng 1.x
git clone -b v1.11 https://github.com/nanomsg/nng.git ~/nng-src
cmake -S ~/nng-src -B ~/nng-src/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=$HOME/kmb-deps/nng -DBUILD_SHARED_LIBS=OFF \
  -DNNG_ENABLE_TLS=OFF -DNNG_TESTS=OFF -DNNG_TOOLS=OFF -DCMAKE_OSX_DEPLOYMENT_TARGET=15.0
cmake --build ~/nng-src/build --target install

# 3. Patched KiCad source
git clone --branch 10.0.8 https://gitlab.com/kicad/code/kicad.git ~/kicad
(cd ~/kicad && git am /path/to/QOL-KiCAD/kicad-patches/*.patch)

# 4. Build (KiCad.app ends up in ~/kmb-build/kicad-dest/)
cd ~/kicad-mac-builder
KMB_NNG_PREFIX=$HOME/kmb-deps/nng WX_SKIP_DOXYGEN_VERSION_CHECK=1 \
PATH=$HOME/kmb-tools/virtualenv/bin:/opt/homebrew/bin:$PATH \
python3 ./build.py --arch=arm64 --build-dir ~/kmb-build --kicad-source-dir ~/kicad \
  --build-type Release --macos-min-version 15.0 \
  --symbols-ref 10.0.8 --footprints-ref 10.0.8 --templates-ref 10.0.8 --packages3d-ref 10.0.8 \
  --skip-docs-update --target kicad
ditto -c -k --sequesterRsrc --keepParent ~/kmb-build/kicad-dest/KiCad.app ~/KiCad.zip
```

The `package-kicad-nightly` DMG target fails on macOS 26 (`hdiutil: resize: failed`), so zip the
app with `ditto` instead (keeps the bundle's symlinks and signatures).

### Opening the app

The app is only ad-hoc signed, not signed with a Developer ID or notarized (that needs a paid Apple
Developer account), so Gatekeeper blocks it when downloaded. Unzip, move `KiCad.app` to
`/Applications`, then either right-click it > **Open** > **Open**, or run:

```sh
xattr -dr com.apple.quarantine /Applications/KiCad.app
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
