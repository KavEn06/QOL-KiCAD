# Run in an MSYS2 UCRT64 shell after build.sh. Creates a portable KiCad tree + zip in $WORK/dist.
set -e
WORK=${WORK:-/c/kb}
cd $WORK
NAME=KiCad-10.0.8-qol-win64
OUT=$WORK/dist/$NAME
rm -rf $WORK/install "$OUT"; mkdir -p "$OUT"
/ucrt64/bin/cmake.exe --install build > $WORK/install.log
cp -a $WORK/install/. "$OUT/"

# Stock libraries (no 3D models)
mkdir -p "$OUT/share/kicad"
cp -a /ucrt64/share/kicad/footprints /ucrt64/share/kicad/symbols /ucrt64/share/kicad/template "$OUT/share/kicad/"

# Python runtime (stdlib + wxPython)
PYV=python3.14
mkdir -p "$OUT/lib/$PYV/site-packages"
(cd /ucrt64/lib/$PYV && tar cf - --exclude=./site-packages --exclude=./test --exclude=./idlelib \
   --exclude=./tkinter --exclude=./turtledemo --exclude=./ensurepip --exclude='__pycache__' .) \
   | (cd "$OUT/lib/$PYV" && tar xf -)
for p in wx six.py packaging; do cp -a /ucrt64/lib/$PYV/site-packages/$p "$OUT/lib/$PYV/site-packages/"; done
cp /ucrt64/bin/python.exe /ucrt64/bin/python3.exe /ucrt64/bin/pythonw.exe "$OUT/bin/"

# ngspice (loaded at runtime) + code models, fontconfig + TLS config
cp /ucrt64/bin/libngspice-0.dll "$OUT/bin/"
mkdir -p "$OUT/lib/ngspice" && cp -a /ucrt64/lib/ngspice/. "$OUT/lib/ngspice/"
mkdir -p "$OUT/etc" && cp -a /ucrt64/etc/fonts /ucrt64/etc/ssl "$OUT/etc/"

# Copy every MinGW DLL the binaries/modules depend on (until no new ones appear)
while :; do
  find "$OUT" \( -iname '*.exe' -o -iname '*.dll' -o -iname '*.kiface' -o -iname '*.pyd' -o -iname '*.cm' \) -print0 \
    | xargs -0 ntldd -R 2>/dev/null | tr -d '\r' \
    | awk 'tolower($3) ~ /msys64.ucrt64.bin/ {print $1}' | sort -fu > /tmp/deps.txt
  added=0
  while read -r b; do
    [ -e "$OUT/bin/$b" ] || { cp "/ucrt64/bin/$b" "$OUT/bin/"; added=1; }
  done < /tmp/deps.txt
  [ $added = 0 ] && break
done

# Zip
rm -f $WORK/dist/$NAME.zip
(cd $WORK/dist && 7z a -tzip -mx=7 -bso0 -bsp0 $NAME.zip $NAME)
du -sh "$OUT" $WORK/dist/$NAME.zip
