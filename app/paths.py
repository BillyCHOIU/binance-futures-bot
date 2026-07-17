from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

DEFAULT_ENV = "BINANCE_API_KEY=\nBINANCE_API_SECRET=\nUSE_TESTNET=true\n"

BUNDLED_DOCS = (
    "config.yaml",
    "config.example.yaml",
    ".env.example",
    "NEWS_SOURCES.md",
    "README.md",
    "INSTALL.md",
)

ICON_FILES = ("fluxbot.ico", "fluxbot_icon.png", "fluxbot_icon_256.png")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """源码树根（开发用）。"""
    return Path(__file__).resolve().parents[1]


def bundle_dir() -> Path:
    """只读资源：开发=项目根；打包=_MEIPASS。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return project_root()


def app_dir() -> Path:
    """
    可写目录：.env / config / data / logs / strategies
    FLUXBOT_HOME 可覆盖；打包默认=exe 同目录。
    """
    env_home = os.getenv("FLUXBOT_HOME", "").strip()
    if env_home:
        p = Path(env_home).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return project_root()


def _copy_if_absent(src: Path, dst: Path) -> None:
    if src.exists() and not dst.exists():
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        except Exception:
            pass


def _copy_newer(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    try:
        if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    except Exception:
        pass


def ensure_user_files() -> Path:
    """首次运行：目录 + 默认配置/图标/示例策略。"""
    root = app_dir()
    root.mkdir(parents=True, exist_ok=True)
    for sub in ("data", "logs", "strategies", "assets"):
        (root / sub).mkdir(exist_ok=True)

    bundled = bundle_dir()
    for name in BUNDLED_DOCS:
        _copy_if_absent(bundled / name, root / name)

    # 图标：打包资源 + 开发同步
    assets_dst = root / "assets"
    for name in ICON_FILES:
        _copy_newer(bundled / "assets" / name, assets_dst / name)
        if not is_frozen():
            _copy_newer(project_root() / "assets" / name, assets_dst / name)

    # 示例策略：目录尚空时拷贝
    strat_dst = root / "strategies"
    bundled_strat = bundled / "strategies"
    if bundled_strat.exists() and not any(strat_dst.glob("*")):
        for f in bundled_strat.iterdir():
            if f.is_file():
                _copy_if_absent(f, strat_dst / f.name)
    _copy_if_absent(bundled_strat / "README.md", strat_dst / "README.md")

    env = root / ".env"
    if not env.exists():
        example = root / ".env.example"
        if example.exists():
            _copy_if_absent(example, env)
        if not env.exists():
            env.write_text(DEFAULT_ENV, encoding="utf-8")
    return root


def strategies_dir() -> Path:
    d = ensure_user_files() / "strategies"
    d.mkdir(parents=True, exist_ok=True)
    return d


def assets_dir() -> Path:
    d = ensure_user_files() / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d
