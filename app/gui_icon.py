from __future__ import annotations

import os
import sys
from pathlib import Path

from app.paths import app_dir, assets_dir


def resolve_icon_path() -> Path | None:
    candidates: list[Path] = [
        assets_dir() / "fluxbot.ico",
        assets_dir() / "fluxbot_icon.png",
        app_dir() / "assets" / "fluxbot.ico",
        Path(os.environ.get("LOCALAPPDATA", "")) / "FluxBot" / "assets" / "fluxbot.ico",
        Path(r"C:\Users\user\Desktop\FluxBot.ico"),
        Path(r"C:\Users\user\Desktop\FluxBot_icon_preview.png"),
    ]
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        candidates = [
            meipass / "assets" / "fluxbot.ico",
            meipass / "assets" / "fluxbot_icon.png",
            Path(sys.executable).resolve().parent / "assets" / "fluxbot.ico",
        ] + candidates
    else:
        root = Path(__file__).resolve().parents[1]
        candidates = [root / "assets" / "fluxbot.ico", root / "assets" / "fluxbot_icon.png"] + candidates

    seen: set[str] = set()
    for p in candidates:
        try:
            if not p.exists():
                continue
            key = str(p.resolve())
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        return p
    return None


def apply_window_icon(window) -> None:
    icon = resolve_icon_path()
    if not icon:
        return
    try:
        if icon.suffix.lower() == ".ico":
            window.iconbitmap(default=str(icon))
            window.iconbitmap(str(icon))
            return
    except Exception:
        pass
    try:
        from PIL import Image, ImageTk

        img = Image.open(icon).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
        window._icon_img = ImageTk.PhotoImage(img)
        window.iconphoto(True, window._icon_img)
    except Exception:
        pass
