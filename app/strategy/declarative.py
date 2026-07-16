from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from app.strategy.base import (
    Sentiment,
    Signal,
    atr,
    ema,
    gate_open_by_sentiment,
    ohlcv_to_df,
    rsi,
    stops_from_atr,
)
from app.strategy.breakout import BreakoutStrategy
from app.strategy.rsi import RsiReversionStrategy
from app.strategy.trend import TrendStrategy

# 声明式 type → 内置类
TYPE_MAP = {
    "trend_ema": TrendStrategy,
    "trend": TrendStrategy,
    "ema": TrendStrategy,
    "rsi_reversion": RsiReversionStrategy,
    "rsi": RsiReversionStrategy,
    "breakout": BreakoutStrategy,
    "通道突破": BreakoutStrategy,
}


def _parse_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    suf = path.suffix.lower()
    if suf in {".yaml", ".yml"}:
        data = yaml.safe_load(text) or {}
    elif suf == ".json":
        data = json.loads(text or "{}")
    elif suf == ".toml":
        try:
            import tomllib  # py3.11+
        except ImportError:
            import tomli as tomllib  # type: ignore
        data = tomllib.loads(text)
    elif suf in {".txt", ".ini", ".conf", ".cfg", ".md"}:
        data = _parse_simple_kv(text)
    else:
        # 尝试 yaml，再 json
        try:
            data = yaml.safe_load(text) or {}
            if not isinstance(data, dict):
                raise ValueError("not dict")
        except Exception:
            data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} 解析结果不是字典/对象")
    return data


def _parse_simple_kv(text: str) -> dict[str, Any]:
    """
    简单文本：
      id=my_s
      name=我的策略
      type=trend_ema
      ema_fast=12
      ema_slow=40
    或 markdown 里的 key: value 行
    """
    data: dict[str, Any] = {}
    params: dict[str, Any] = {}
    meta_keys = {"id", "name", "type", "desc", "description", "strategy_id", "strategy_name"}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        if ":" in line:
            k, v = line.split(":", 1)
        elif "=" in line:
            k, v = line.split("=", 1)
        else:
            continue
        k = k.strip().strip("-* ").lower().replace(" ", "_")
        v = v.strip().strip("`\"'")
        if not k:
            continue
        # 尝试数字
        parsed: Any = v
        try:
            if "." in v:
                parsed = float(v)
            else:
                parsed = int(v)
        except ValueError:
            if v.lower() in {"true", "yes", "on"}:
                parsed = True
            elif v.lower() in {"false", "no", "off"}:
                parsed = False
        if k in meta_keys:
            if k == "strategy_id":
                data["id"] = parsed
            elif k == "strategy_name":
                data["name"] = parsed
            elif k == "description":
                data["desc"] = parsed
            else:
                data[k] = parsed
        else:
            params[k] = parsed
    if params:
        data["params"] = {**(data.get("params") or {}), **params}
    if "type" not in data:
        data["type"] = "trend_ema"
    return data


class RulesStrategy:
    """
    规则型声明式策略（type: rules）。

    open_long / open_short / close_long / close_short: 条件列表（全满足）
    条件键：
      rsi_below, rsi_above, ema_fast_above_slow, ema_fast_below_slow,
      price_above_sma, price_below_sma, breakout_high, breakout_low
    """

    def __init__(self, spec: dict[str, Any], sid: str, name: str):
        self.id = sid
        self.name = name
        self.spec = spec
        p = spec.get("params") or {}
        self.rsi_period = int(p.get("rsi_period", spec.get("rsi_period", 14)))
        self.ema_fast = int(p.get("ema_fast", spec.get("ema_fast", 20)))
        self.ema_slow = int(p.get("ema_slow", spec.get("ema_slow", 60)))
        self.sma_period = int(p.get("sma_period", spec.get("sma_period", 20)))
        self.lookback = int(p.get("lookback", spec.get("lookback", 20)))
        self.atr_period = int(p.get("atr_period", spec.get("atr_period", 14)))
        self.atr_stop_mult = float(p.get("atr_stop_mult", spec.get("atr_stop_mult", 1.5)))
        self.take_profit_rr = float(p.get("take_profit_rr", spec.get("take_profit_rr", 2.0)))
        self.open_long = list(spec.get("open_long") or [])
        self.open_short = list(spec.get("open_short") or [])
        self.close_long = list(spec.get("close_long") or [])
        self.close_short = list(spec.get("close_short") or [])

    def _ctx(self, ohlcv: list) -> dict[str, float] | None:
        need = max(self.ema_slow, self.rsi_period, self.lookback, self.atr_period, self.sma_period) + 5
        if not ohlcv or len(ohlcv) < need:
            return None
        df = ohlcv_to_df(ohlcv)
        df["ema_f"] = ema(df["close"], self.ema_fast)
        df["ema_s"] = ema(df["close"], self.ema_slow)
        df["rsi"] = rsi(df["close"], self.rsi_period)
        df["atr"] = atr(df, self.atr_period)
        df["sma"] = df["close"].rolling(self.sma_period).mean()
        window = df.iloc[-(self.lookback + 1) : -1]
        row = df.iloc[-1]
        price = float(row["close"])
        return {
            "price": price,
            "rsi": float(row["rsi"]) if not np.isnan(row["rsi"]) else 50.0,
            "ema_f": float(row["ema_f"]),
            "ema_s": float(row["ema_s"]),
            "sma": float(row["sma"]) if not np.isnan(row["sma"]) else price,
            "atr": float(row["atr"]) if not np.isnan(row["atr"]) else price * 0.01,
            "hh": float(window["high"].max()),
            "ll": float(window["low"].min()),
        }

    def _match(self, conds: list, ctx: dict[str, float]) -> bool:
        if not conds:
            return False
        for c in conds:
            if isinstance(c, str):
                # 简写
                key, _, val = c.partition("=")
                c = {key.strip(): val.strip()} if val else {c: True}
            if not isinstance(c, dict):
                continue
            for k, v in c.items():
                k = str(k).lower()
                try:
                    vf = float(v) if not isinstance(v, bool) else v
                except (TypeError, ValueError):
                    vf = v
                ok = True
                if k in ("rsi_below", "rsi<"):
                    ok = ctx["rsi"] < float(vf)
                elif k in ("rsi_above", "rsi>"):
                    ok = ctx["rsi"] > float(vf)
                elif k in ("ema_fast_above_slow", "ema_bull"):
                    ok = ctx["ema_f"] > ctx["ema_s"]
                elif k in ("ema_fast_below_slow", "ema_bear"):
                    ok = ctx["ema_f"] < ctx["ema_s"]
                elif k in ("price_above_sma",):
                    ok = ctx["price"] > ctx["sma"]
                elif k in ("price_below_sma",):
                    ok = ctx["price"] < ctx["sma"]
                elif k in ("breakout_high",):
                    ok = ctx["price"] > ctx["hh"]
                elif k in ("breakout_low",):
                    ok = ctx["price"] < ctx["ll"]
                elif k in ("true", "always"):
                    ok = bool(vf) if not isinstance(vf, bool) else vf
                else:
                    ok = False
                if not ok:
                    return False
        return True

    def evaluate(
        self,
        symbol: str,
        ohlcv: list,
        sentiment: Sentiment,
        has_position: bool,
        position_side: str | None = None,
    ) -> Signal:
        ctx = self._ctx(ohlcv)
        if not ctx:
            return Signal(symbol, "hold", "K线不足")
        price, atr_v = ctx["price"], ctx["atr"]

        if has_position and position_side:
            if position_side == "long":
                if self._match(self.close_long, ctx) or sentiment == "BEAR":
                    return Signal(symbol, "close", "规则平多")
            if position_side == "short":
                if self._match(self.close_short, ctx) or sentiment == "BULL":
                    return Signal(symbol, "close", "规则平空")
            return Signal(symbol, "hold", "规则持仓")

        if self._match(self.open_long, ctx):
            block = gate_open_by_sentiment(sentiment, "long")
            if block:
                return Signal(symbol, "hold", block)
            stop, tp = stops_from_atr(price, atr_v, "long", self.atr_stop_mult, self.take_profit_rr)
            return Signal(
                symbol, "open_long", "规则开多", entry=price, stop=stop, take_profit=tp, strength=0.5
            )
        if self._match(self.open_short, ctx):
            block = gate_open_by_sentiment(sentiment, "short")
            if block:
                return Signal(symbol, "hold", block)
            stop, tp = stops_from_atr(price, atr_v, "short", self.atr_stop_mult, self.take_profit_rr)
            return Signal(
                symbol, "open_short", "规则开空", entry=price, stop=stop, take_profit=tp, strength=0.5
            )
        return Signal(symbol, "hold", "规则无信号")


def load_declarative(path: Path) -> dict[str, Any]:
    """返回 registry 用的 meta 字典。"""
    spec = _parse_file(path)
    sid = str(spec.get("id") or spec.get("strategy_id") or f"file_{path.stem}")
    name = str(spec.get("name") or spec.get("strategy_name") or path.stem)
    desc = str(spec.get("desc") or spec.get("description") or f"文件策略 {path.name}")
    stype = str(spec.get("type") or "trend_ema").lower().strip()
    params = dict(spec.get("params") or {})
    # 顶层非 meta 字段并入 params
    for k, v in list(spec.items()):
        if k in {
            "id",
            "name",
            "type",
            "desc",
            "description",
            "params",
            "open_long",
            "open_short",
            "close_long",
            "close_short",
            "strategy_id",
            "strategy_name",
        }:
            continue
        if k not in params:
            params[k] = v

    if stype in ("rules", "rule", "条件", "规则"):
        def factory(**_kw):
            merged = {**spec, "params": {**params, **(_kw or {})}}
            return RulesStrategy(merged, sid, name)

        return {
            "name": name,
            "class": None,
            "factory": factory,
            "defaults": params,
            "desc": desc,
            "path": str(path),
            "plugin": True,
            "format": path.suffix.lower(),
        }

    cls = TYPE_MAP.get(stype)
    if cls is None:
        # 未知 type 当 rules 空壳 / 回退 trend
        cls = TrendStrategy
        desc = f"{desc} (未知type={stype}→trend_ema)"

    def factory(**kw):
        merged = {**params, **(kw or {})}
        return cls(**merged)

    return {
        "name": name,
        "class": cls,
        "factory": factory,
        "defaults": params,
        "desc": desc,
        "path": str(path),
        "plugin": True,
        "format": path.suffix.lower(),
    }


SUPPORTED_EXTS = {".py", ".yaml", ".yml", ".json", ".toml", ".txt", ".ini", ".conf", ".cfg", ".md"}
