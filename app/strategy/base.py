from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np
import pandas as pd

Sentiment = Literal["BULL", "BEAR", "NEUTRAL", "BOTH"]
Action = Literal["open_long", "open_short", "close", "hold"]



@dataclass
class Signal:
    symbol: str
    action: Action
    reason: str
    entry: float = 0.0
    stop: float = 0.0
    take_profit: float = 0.0
    strength: float = 0.0


class Strategy(Protocol):
    """所有策略统一接口。"""

    name: str
    id: str

    def evaluate(
        self,
        symbol: str,
        ohlcv: list,
        sentiment: Sentiment,
        has_position: bool,
        position_side: str | None = None,
    ) -> Signal: ...


def ohlcv_to_df(ohlcv: list) -> pd.DataFrame:
    return pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def stops_from_atr(
    price: float,
    atr_v: float,
    side: Literal["long", "short"],
    atr_stop_mult: float,
    take_profit_rr: float,
) -> tuple[float, float]:
    if atr_v <= 0:
        atr_v = price * 0.01
    if side == "long":
        stop = price - atr_stop_mult * atr_v
        tp = price + take_profit_rr * (price - stop)
    else:
        stop = price + atr_stop_mult * atr_v
        tp = price - take_profit_rr * (stop - price)
    return stop, tp


def gate_open_by_sentiment(
    sentiment: Sentiment,
    want: Literal["long", "short"],
) -> str | None:
    """返回 None 表示允许开仓；否则返回 hold 原因。"""
    if sentiment == "BOTH":
        return None
    if sentiment == "NEUTRAL":
        return "舆情中性，不开新仓"
    if want == "long" and sentiment == "BEAR":
        return "舆情偏空，禁止开多"
    if want == "short" and sentiment == "BULL":
        return "舆情偏多，禁止开空"
    return None
