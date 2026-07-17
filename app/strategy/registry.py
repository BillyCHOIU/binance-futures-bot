from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Callable

from app.paths import strategies_dir as paths_strategies_dir
from app.strategy.breakout import BreakoutStrategy
from app.strategy.declarative import SUPPORTED_EXTS, load_declarative
from app.strategy.rsi import RsiReversionStrategy
from app.strategy.trend import TrendStrategy

logger = logging.getLogger("fluxbot.strategy")

BUILTIN: dict[str, dict[str, Any]] = {
    "trend_ema": {
        "name": "EMA趋势",
        "class": TrendStrategy,
        "defaults": {
            "ema_fast": 20,
            "ema_slow": 60,
            "atr_period": 14,
            "atr_stop_mult": 1.5,
            "take_profit_rr": 2.0,
        },
        "desc": "均线趋势跟踪，适合单边行情",
    },
    "rsi_reversion": {
        "name": "RSI回归",
        "class": RsiReversionStrategy,
        "defaults": {
            "rsi_period": 14,
            "oversold": 30,
            "overbought": 70,
            "atr_period": 14,
            "atr_stop_mult": 1.5,
            "take_profit_rr": 1.5,
        },
        "desc": "超买超卖回归，适合震荡",
    },
    "breakout": {
        "name": "通道突破",
        "class": BreakoutStrategy,
        "defaults": {
            "lookback": 20,
            "atr_period": 14,
            "atr_stop_mult": 1.5,
            "take_profit_rr": 2.0,
        },
        "desc": "N根K线高低点突破",
    },
}


def strategies_dir() -> Path:
    return paths_strategies_dir()


def list_plugin_files() -> list[Path]:
    files: list[Path] = []
    for p in strategies_dir().iterdir():
        if not p.is_file():
            continue
        if p.name.startswith("_") or p.name.upper().startswith("README"):
            continue
        if p.suffix.lower() in SUPPORTED_EXTS:
            files.append(p)
    return sorted(files)


def _load_plugin_module(path: Path):
    mod_name = f"fluxbot_user_strategy_{path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def discover_plugins() -> dict[str, dict[str, Any]]:
    """
    支持多种格式（任意常见策略文件）：
      .py / .yaml / .yml / .json / .toml / .txt / .ini / .conf / .cfg / .md
    """
    found: dict[str, dict[str, Any]] = {}
    for path in list_plugin_files():
        try:
            if path.suffix.lower() == ".py":
                mod = _load_plugin_module(path)
                sid = getattr(mod, "STRATEGY_ID", None) or f"plugin_{path.stem}"
                sname = getattr(mod, "STRATEGY_NAME", None) or path.stem
                cls = getattr(mod, "Strategy", None)
                factory = getattr(mod, "create_strategy", None)
                if cls is None and factory is None:
                    logger.warning("插件 %s 缺少 Strategy 类或 create_strategy", path.name)
                    continue
                defaults = getattr(mod, "DEFAULTS", {}) or {}
                desc = getattr(mod, "STRATEGY_DESC", f"Python插件 {path.name}")
                found[sid] = {
                    "name": f"{sname}",
                    "class": cls,
                    "factory": factory,
                    "defaults": dict(defaults),
                    "desc": desc,
                    "path": str(path),
                    "plugin": True,
                    "format": ".py",
                }
            else:
                meta = load_declarative(path)
                sid = None
                # id 在 factory 闭包里；从 path/name 再解析一次拿 id
                from app.strategy.declarative import _parse_file

                spec = _parse_file(path)
                sid = str(spec.get("id") or spec.get("strategy_id") or f"file_{path.stem}")
                # 避免与内置冲突
                if sid in BUILTIN:
                    sid = f"file_{sid}"
                display = meta["name"]
                ext = path.suffix.lower()
                found[sid] = {
                    **meta,
                    "name": f"{display} [{ext}]",
                }
        except Exception as e:
            logger.exception("加载策略文件失败 %s: %s", path, e)
    return found


def catalog() -> dict[str, dict[str, Any]]:
    out = {k: {**v, "plugin": False} for k, v in BUILTIN.items()}
    out.update(discover_plugins())
    return out


def list_strategy_choices() -> list[tuple[str, str, str]]:
    items = []
    for sid, meta in catalog().items():
        tag = ""
        if meta.get("plugin"):
            fmt = meta.get("format") or ""
            tag = f" [文件{fmt}]" if fmt and fmt != ".py" else " [插件]"
        # name 可能已带 [ext]
        name = meta["name"]
        if meta.get("plugin") and "[." not in name and not name.endswith("]"):
            name = f"{name}{tag}"
        items.append((sid, name, meta.get("desc") or ""))
    return items


def build_strategy(
    strategy_id: str,
    params: dict[str, Any] | None = None,
    on_log: Callable[[str], None] | None = None,
):
    log = on_log or (lambda m: None)
    cat = catalog()
    if strategy_id not in cat:
        log(f"未知策略 {strategy_id}，回退 trend_ema")
        strategy_id = "trend_ema"
    meta = cat[strategy_id]
    merged = {**meta.get("defaults", {}), **(params or {})}

    if meta.get("factory"):
        strat = meta["factory"](**merged)
    else:
        strat = meta["class"](**merged)

    if not getattr(strat, "id", None):
        strat.id = strategy_id
    if not getattr(strat, "name", None):
        strat.name = meta["name"]
    log(f"已加载策略: {strat.name} ({getattr(strat, 'id', strategy_id)}) params={merged}")
    return strat


def resolve_active_from_config(cfg: dict) -> tuple[str, dict[str, Any]]:
    sc = cfg.get("strategy") or {}
    active = str(sc.get("active") or "trend_ema")
    presets = sc.get("presets") or {}
    params: dict[str, Any] = {}
    if active in presets and isinstance(presets[active], dict):
        params.update(presets[active])
    if isinstance(sc.get("params"), dict):
        params.update(sc["params"])
    legacy_keys = (
        "ema_fast",
        "ema_slow",
        "atr_period",
        "atr_stop_mult",
        "take_profit_rr",
        "rsi_period",
        "oversold",
        "overbought",
        "lookback",
    )
    if active == "trend_ema" or not sc.get("active"):
        for k in legacy_keys:
            if k in sc and k not in params:
                params[k] = sc[k]
    return active, params
