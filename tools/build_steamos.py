"""Build dist/BL4Fix-SteamOS.zip on Linux or Windows; no installed game or pip needed."""

from __future__ import annotations

import hashlib
import argparse
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "installer"), str(REPO / "tools")]

import build
import catalog
import manual_zip


def package(out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        payload = Path(tmp)
        for info in catalog.MODS:
            build.build_sdkmod(REPO / info.source / info.id, payload / f"{info.id}.sdkmod",
                               catalog.license_files(info, REPO))
        manual = manual_zip.build(payload / "BL4Fix-Manual.zip", payload, build.fetch_sdk(), "SteamOS")
        shutil.copyfile(manual, out.parent / "BL4Fix-Manual.zip")
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, path in {"steamos.py": REPO / "installer/steamos.py",
                               "setup.py": REPO / "installer/steamos_gui.py",
                               "catalog.py": REPO / "installer/catalog.py",
                               "movies.py": REPO / "mods/bl4_skip_intro/movies.py",
                               "shared.py": REPO / "mods/bl4_direct/shared.py",
                               "BL4Fix-Manual.zip": manual, "STEAMOS.md": REPO / "docs/STEAMOS.md",
                               "LICENSE": REPO / "LICENSE", "LICENSE-AGPL": REPO / "LICENSE-AGPL"}.items():
                zf.writestr(manual_zip._entry(name), build.file_bytes(path))
            zf.writestr(manual_zip._entry("install.py"), "from steamos import main\nraise SystemExit(main())\n")
    out.with_suffix(".zip.sha256").write_text(f"{hashlib.sha256(out.read_bytes()).hexdigest()}  {out.name}\n", encoding="utf-8")
    return out


def native(out: Path) -> Path:
    if sys.platform != "linux":
        raise SystemExit("The native SteamOS executable must be built on Linux (or by the SteamOS workflow).")
    package(out / "BL4Fix-SteamOS.zip")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--noupx",
        "--name", "BL4FixSetup-SteamOS", "--distpath", str(out),
        "--workpath", str(REPO / "build/steamos-pyinstaller"), "--specpath", str(REPO / "build"),
        "--paths", str(REPO / "installer"), "--paths", str(REPO / "mods/bl4_direct"),
        "--paths", str(REPO / "mods/bl4_skip_intro"),
        "--add-data", f"{out / 'BL4Fix-Manual.zip'}:.",
        "--add-data", f"{REPO / 'docs/STEAMOS.md'}:.",
        str(REPO / "installer/steamos_gui.py"),
    ], check=True)
    archive = out / "BL4FixSetup-SteamOS.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for path in (out / "BL4FixSetup-SteamOS", REPO / "docs/STEAMOS.md", REPO / "LICENSE", REPO / "LICENSE-AGPL"):
            tf.add(path, arcname=f"BL4FixSetup-SteamOS/{path.name}")
    archive.with_suffix(".gz.sha256").write_text(
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n", encoding="utf-8")
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true", help="bundle a standalone graphical Linux executable (requires PyInstaller)")
    args = parser.parse_args()
    print(native(REPO / "dist") if args.native else package(REPO / "dist/BL4Fix-SteamOS.zip"))
