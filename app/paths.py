from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """只读资源目录（开发=项目根；打包= _MEIPASS）。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[1]


def app_dir() -> Path:
    """
    可写目录：.env / config.yaml / data / logs
    - 开发：项目根
    - 打包：exe 同目录（便携）；也可用 FLUXBOT_HOME 覆盖
    """
    env_home = os.getenv("FLUXBOT_HOME", "").strip()
    if env_home:
        p = Path(env_home).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def ensure_user_files() -> Path:
    """首次运行：把默认配置拷到可写目录。"""
    root = app_dir()
    root.mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    (root / "strategies").mkdir(exist_ok=True)

    bundled = bundle_dir()
    for name in (
        "config.yaml",
        "config.example.yaml",
        ".env.example",
        "NEWS_SOURCES.md",
        "README.md",
        "INSTALL.md",
    ):
        src = bundled / name
        dst = root / name
        if src.exists() and not dst.exists():
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass

    # 图标
    assets_dst = root / "assets"
    assets_dst.mkdir(exist_ok=True)
    for name in ("fluxbot.ico", "fluxbot_icon.png", "fluxbot_icon_256.png"):
        src = bundled / "assets" / name
        dst = assets_dst / name
        if src.exists() and (not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime):
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass
    # 开发模式：从项目 assets 同步
    if not getattr(sys, "frozen", False):
        proj_assets = Path(__file__).resolve().parents[1] / "assets"
        for name in ("fluxbot.ico", "fluxbot_icon.png", "fluxbot_icon_256.png"):
            src = proj_assets / name
            dst = assets_dst / name
            if src.exists():
                try:
                    shutil.copy2(src, dst)
                except Exception:
                    pass

    # 示例策略：仅在目录为空时拷贝
    strat_dst = root / "strategies"
    bundled_strat = bundled / "strategies"
    if bundled_strat.exists() and not any(strat_dst.glob("*.py")):
        for f in bundled_strat.glob("*"):
            try:
                shutil.copy2(f, strat_dst / f.name)
            except Exception:
                pass
    readme = strat_dst / "README.md"
    if not readme.exists() and (bundled_strat / "README.md").exists():
        try:
            shutil.copy2(bundled_strat / "README.md", readme)
        except Exception:
            pass

    env = root / ".env"
    if not env.exists():
        example = root / ".env.example"
        if example.exists():
            try:
                shutil.copy2(example, env)
            except Exception:
                env.write_text(
                    "BINANCE_API_KEY=\nBINANCE_API_SECRET=\nUSE_TESTNET=true\n",
                    encoding="utf-8",
                )
        else:
            env.write_text(
                "BINANCE_API_KEY=\nBINANCE_API_SECRET=\nUSE_TESTNET=true\n",
                encoding="utf-8",
            )
    return root
