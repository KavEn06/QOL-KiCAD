# Run in an MSYS2 UCRT64 shell. Configures and builds patched KiCad into $WORK/build.
set -e
WORK=${WORK:-/c/kb}   # contains the patched source in $WORK/kicad
cd $WORK
export GIT_DIR=/dev/null
export CXXFLAGS="-O2 -w"
PY=/ucrt64/bin/python.exe
MSYS2_ARG_CONV_EXCL="-DCMAKE_INSTALL_PREFIX=;-DCMAKE_PREFIX_PATH=;-DDEFAULT_INSTALL_PATH=" \
/ucrt64/bin/cmake.exe -Wno-dev -Wno-author -GNinja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=$WORK/install \
  -DCMAKE_PREFIX_PATH=/ucrt64 \
  -DDEFAULT_INSTALL_PATH=/ucrt64 \
  -DwxWidgets_CONFIG_EXECUTABLE=/ucrt64/bin/wx-config-3.2 \
  -DOCC_INCLUDE_DIR=/ucrt64/include/opencascade \
  -DKICAD_SCRIPTING_WXPYTHON=ON \
  -DKICAD_BUILD_I18N=OFF \
  -DKICAD_BUILD_QA_TESTS=OFF \
  -DPYTHON_EXECUTABLE=$PY \
  -DPYTHON_INCLUDE_DIR=$($PY -c "from sysconfig import get_paths as gp; print(gp()['include'])") \
  -DPYTHON_ROOT_DIR=/ucrt64 \
  -DNGSPICE_ROOT_DIR=/ucrt64 \
  -S kicad -B build
/ucrt64/bin/cmake.exe --build build
echo BUILD_DONE
