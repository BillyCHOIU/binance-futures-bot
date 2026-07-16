"""
Build single-file FluxBot-Setup.exe for distribution to other PCs.
Requires: dist/FluxBot already built (run build.bat first).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST_APP = ROOT / "dist" / "FluxBot"
PAYLOAD = ROOT / "dist" / "fluxbot_payload.zip"
OUT_DIR = ROOT / "dist" / "installer"
SETUP_SRC = ROOT / "make_setup_src" / "setup_main.py"


def main() -> int:
    if not (DIST_APP / "FluxBot.exe").exists():
        print("ERROR: dist/FluxBot/FluxBot.exe missing. Run build.bat first.")
        return 1

    print("[1/3] Zipping application payload…")
    PAYLOAD.parent.mkdir(parents=True, exist_ok=True)
    if PAYLOAD.exists():
        PAYLOAD.unlink()
    with zipfile.ZipFile(PAYLOAD, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in DIST_APP.rglob("*"):
            if path.is_file():
                # skip logs/data noise if any
                rel = path.relative_to(DIST_APP)
                if any(p in ("logs", "data") for p in rel.parts):
                    if path.suffix in {".log", ".db"}:
                        continue
                zf.write(path, arcname=str(rel).replace("\\", "/"))
    print(f"  payload: {PAYLOAD} ({PAYLOAD.stat().st_size // 1024 // 1024} MB)")

    print("[2/3] Building FluxBot-Setup.exe with PyInstaller…")
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)

    # ensure pyinstaller
    subprocess.check_call([str(py), "-m", "pip", "install", "-q", "pyinstaller"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    icon = ROOT / "assets" / "fluxbot.ico"
    cmd = [
        str(py),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "FluxBot-Setup",
        "--distpath",
        str(OUT_DIR),
        "--workpath",
        str(ROOT / "build" / "setup_work"),
        "--specpath",
        str(ROOT / "build" / "setup_spec"),
        "--add-data",
        f"{PAYLOAD};.",
    ]
    if icon.exists():
        cmd.extend(["--icon", str(icon)])
    cmd.append(str(SETUP_SRC))
    print(" ", " ".join(cmd[-10:]))
    subprocess.check_call(cmd, cwd=str(ROOT))

    setup_exe = OUT_DIR / "FluxBot-Setup.exe"
    if not setup_exe.exists():
        print("ERROR: Setup exe not produced")
        return 1

    # copy to Desktop for easy send
    desktop = Path.home() / "Desktop"
    desk_copy = desktop / "FluxBot-Setup.exe"
    shutil.copy2(setup_exe, desk_copy)
    # also keep at project root dist
    shutil.copy2(setup_exe, ROOT / "dist" / "FluxBot-Setup.exe")

    print("[3/3] Done.")
    print(f"  Installer: {setup_exe}")
    print(f"  Desktop:   {desk_copy}")
    print(f"  Size:      {setup_exe.stat().st_size // 1024 // 1024} MB")
    print("Send FluxBot-Setup.exe to any Windows PC → double-click → Install.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
