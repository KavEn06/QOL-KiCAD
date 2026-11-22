# KiCad patches: joined Edge.Cuts shapes follow live

Patches against KiCad **10.0.8** (tag `10.0.8`) that change KiCad itself, not the plugin.
While you drag a point of a line or arc, or move shapes with the Move tool, other lines and arcs
on the same layer joined to them keep their ends attached live, in one undo step. Following arcs
keep their included angle (not their tangency). Locked shapes and other layers never follow.

Tested on Linux (Ubuntu 22.04) and macOS 26 (Apple Silicon).

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
Schematic Editor, ...) for **arm64**, minimum **macOS 26.0**: it links Homebrew's prebuilt libraries,
which target the macOS version they were built on. The build takes a few hours and needs ~40 GB free.

`macos/kicad-mac-builder-10.0.patch` fixes the builder for current Homebrew/Xcode:

- nng: KiCad 10.0 needs nng 1.x but Homebrew ships 2.x, so a local nng 1.x is used via `KMB_NNG_PREFIX`.
- ngspice: adds `-Wno-invalid-specialization` (newer Clang rejects ngspice's `is_compound` specialisation).
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

# 2. nng 1.x
git clone -b v1.11 https://github.com/nanomsg/nng.git ~/nng-src
cmake -S ~/nng-src -B ~/nng-src/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=$HOME/kmb-deps/nng -DBUILD_SHARED_LIBS=OFF \
  -DNNG_ENABLE_TLS=OFF -DNNG_TESTS=OFF -DNNG_TOOLS=OFF -DCMAKE_OSX_DEPLOYMENT_TARGET=26.0
cmake --build ~/nng-src/build --target install

# 3. Patched KiCad source
git clone --branch 10.0.8 https://gitlab.com/kicad/code/kicad.git ~/kicad
(cd ~/kicad && git am /path/to/QOL-KiCAD/kicad-patches/*.patch)

# 4. Build (KiCad.app ends up in ~/kmb-build/kicad-dest/)
cd ~/kicad-mac-builder
KMB_NNG_PREFIX=$HOME/kmb-deps/nng WX_SKIP_DOXYGEN_VERSION_CHECK=1 \
PATH=$HOME/kmb-tools/virtualenv/bin:/opt/homebrew/bin:$PATH \
python3 ./build.py --arch=arm64 --build-dir ~/kmb-build --kicad-source-dir ~/kicad \
  --build-type Release --macos-min-version 26.0 \
  --symbols-ref 10.0.8 --footprints-ref 10.0.8 --templates-ref 10.0.8 --packages3d-ref 10.0.8 \
  --skip-docs-update --target kicad
ditto -c -k --sequesterRsrc --keepParent ~/kmb-build/kicad-dest/KiCad.app ~/KiCad.zip
```

The `package-kicad-nightly` DMG target failed on macOS 26 (`hdiutil: resize: failed`), so zip the
app with `ditto` instead (keeps the bundle's symlinks and signatures).

### Opening the app

The app is only ad-hoc signed, not signed with a Developer ID or notarized (that needs a paid Apple
Developer account), so Gatekeeper blocks it when downloaded. Unzip, move `KiCad.app` to
`/Applications`, then either right-click it > **Open** > **Open**, or run:

```sh
xattr -dr com.apple.quarantine /Applications/KiCad.app
```
