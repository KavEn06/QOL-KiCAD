#!/usr/bin/env python3
"""Replace installed Homebrew kegs with their arm64_sequoia bottles (macOS 15 minimum)."""
import json, os, shutil, subprocess, sys, tarfile, tempfile, urllib.request

PREFIX = "/opt/homebrew"
CELLAR = f"{PREFIX}/Cellar"
TAG = os.environ.get("BOTTLE_TAG", "arm64_sequoia")
PLACEHOLDERS = {"@@HOMEBREW_PREFIX@@": PREFIX, "@@HOMEBREW_CELLAR@@": CELLAR,
                "@@HOMEBREW_REPOSITORY@@": PREFIX, "@@HOMEBREW_LIBRARY@@": f"{PREFIX}/Library"}

def sub(s):
    for k, v in PLACEHOLDERS.items():
        s = s.replace(k, v)
    return s

def is_macho(path):
    with open(path, "rb") as f:
        return f.read(4) in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe")

def fix_macho(path):
    os.chmod(path, os.stat(path).st_mode | 0o200)
    out = subprocess.run(["otool", "-l", path], capture_output=True, text=True).stdout.splitlines()
    args, cmd = [], None
    for i, line in enumerate(out):
        line = line.strip()
        if line.startswith("cmd "):
            cmd = line.split()[1]
        elif line.startswith(("name ", "path ")) and "@@HOMEBREW" in line:
            val = line.split(None, 1)[1].rsplit(" (offset", 1)[0]
            if cmd == "LC_ID_DYLIB":
                args += ["-id", sub(val)]
            elif cmd == "LC_RPATH":
                args += ["-rpath", val, sub(val)]
            elif cmd and cmd.startswith("LC_") and "DYLIB" in cmd:
                args += ["-change", val, sub(val)]
    if args:
        subprocess.run(["install_name_tool", *args, path], check=True, capture_output=True)
    subprocess.run(["codesign", "-f", "-s", "-", path], check=True, capture_output=True)

def pour(name):
    info = json.load(urllib.request.urlopen(f"https://formulae.brew.sh/api/formula/{name}.json"))
    files = info["bottle"]["stable"]["files"]
    bottle = files.get(TAG) or files.get("all")
    if not bottle:
        sys.exit(f"{name}: no {TAG} bottle")
    req = urllib.request.Request(bottle["url"], headers={"Authorization": "Bearer QQ=="})
    with tempfile.TemporaryDirectory() as tmp:
        tgz = os.path.join(tmp, "b.tar.gz")
        with urllib.request.urlopen(req) as r, open(tgz, "wb") as f:
            shutil.copyfileobj(r, f)
        with tarfile.open(tgz) as t:
            t.extractall(tmp)
        (version,) = os.listdir(os.path.join(tmp, name))
        new = os.path.join(tmp, name, version)
        old_kegs = os.listdir(os.path.join(CELLAR, name))
        if old_kegs != [version]:
            sys.exit(f"{name}: installed {old_kegs} != bottle {version}; upgrade first")
        keg = os.path.join(CELLAR, name, version)
        receipt = os.path.join(keg, "INSTALL_RECEIPT.json")
        if os.path.exists(receipt):
            shutil.copy2(receipt, new)
        shutil.rmtree(keg)
        shutil.move(new, keg)
    for root, _, fnames in os.walk(keg):
        for fn in fnames:
            p = os.path.join(root, fn)
            if os.path.islink(p) or not os.path.isfile(p):
                continue
            if is_macho(p):
                fix_macho(p)
            else:
                try:
                    data = open(p, "rb").read()
                except OSError:
                    continue
                if b"@@HOMEBREW" in data:
                    os.chmod(p, os.stat(p).st_mode | 0o200)
                    open(p, "wb").write(sub(data.decode("latin-1")).encode("latin-1"))
    print(f"{name} {version}: poured {TAG}")

for n in sys.argv[1:]:
    pour(n)
