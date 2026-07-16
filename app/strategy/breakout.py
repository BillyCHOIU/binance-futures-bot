from __future__ import annotations

import numpy as np

from app.strategy.base import (
    Sentiment,
    Signal,
    atr,
    gate_open_by_sentiment,
    ohlcv_to_df,
    stops_from_atr,
)


class BreakoutStrategy:
    """N 根 K 线高低点突破。"""

    id = "breakout"
    name = "通道突破"

    def __init__(
        self,
        lookback: int = 20,
        atr_period: int = 14,
        atr_stop_mult: float = 1.5,
        take_profit_rr: float = 2.0,
        **_kwargs,
    ):
        self.lookback = int(lookback)
        self.atr_period = int(atr_period)
        self.atr_stop_mult = float(atr_stop_mult)
        self.take_profit_rr = float(take_profit_rr)

    def evaluate(
        self,
        symbol: str,
        ohlcv: list,
        sentiment: Sentiment,
        has_position: bool,
        position_side: str | None = None,
    ) -> Signal:
        need = max(self.lookback, self.atr_period) + 5
        if not ohlcv or len(ohlcv) < need:
            return Signal(symbol, "hold", "K线不足")

        df = ohlcv_to_df(ohlcv)
        df["atr"] = atr(df, self.atr_period)
        # 用前 lookback 根（不含当前）的高低
        window = df.iloc[-(self.lookback + 1) : -1]
        hi = float(window["high"].max())
        lo = float(window["low"].min())
        row = df.iloc[-1]
        price = float(row["close"])
        atr_v = float(row["atr"]) if not np.isnan(row["atr"]) else 0.0

        if has_position and position_side:
            if position_side == "long" and (price < lo or sentiment == "BEAR"):
                return Signal(symbol, "close", "跌破通道下沿/舆情空 → 平多")
            if position_side == "short" and (price > hi or sentiment == "BULL"):
                return Signal(symbol, "close", "升破通道上沿/舆情多 → 平空")
            return Signal(symbol, "hold", "持仓中，通道内")

        if price > hi:
            block = gate_open_by_sentiment(sentiment, "long")
            if block:
                return Signal(symbol, "hold", block)
            stop, tp = stops_from_atr(price, atr_v, "long", self.atr_stop_mult, self.take_profit_rr)
            return Signal(
                symbol,
                "open_long",
                f"向上突破 {self.lookback} 高点 {hi:.4f}",
                entry=price,
                stop=stop,
                take_profit=tp,
                strength=(price - hi) / max(price, 1e-9),
            )

        if price < lo:
            block = gate_open_by_sentiment(sentiment, "short")
            if block:
                return Signal(symbol, "hold", block)
            stop, tp = stops_from_atr(price, atr_v, "short", self.atr_stop_mult, self.take_profit_rr)
            return Signal(
                symbol,
                "open_short",
                f"向下突破 {self.lookback} 低点 {lo:.4f}",
                entry=price,
                stop=stop,
                take_profit=tp,
                strength=(lo - price) / max(price, 1e-9),
            )

        return Signal(symbol, "hold", f"通道内 {lo:.4f}~{hi:.4f}")
