from __future__ import annotations

import numpy as np

from app.strategy.base import (
    Sentiment,
    Signal,
    atr,
    gate_open_by_sentiment,
    ohlcv_to_df,
    rsi,
    stops_from_atr,
)


class RsiReversionStrategy:
    """RSI 超买超卖均值回归（震荡市更合适）。"""

    id = "rsi_reversion"
    name = "RSI回归"

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 30,
        overbought: float = 70,
        atr_period: int = 14,
        atr_stop_mult: float = 1.5,
        take_profit_rr: float = 1.5,
        **_kwargs,
    ):
        self.rsi_period = int(rsi_period)
        self.oversold = float(oversold)
        self.overbought = float(overbought)
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
        need = max(self.rsi_period, self.atr_period) + 5
        if not ohlcv or len(ohlcv) < need:
            return Signal(symbol, "hold", "K线不足")

        df = ohlcv_to_df(ohlcv)
        df["rsi"] = rsi(df["close"], self.rsi_period)
        df["atr"] = atr(df, self.atr_period)
        row = df.iloc[-1]
        price = float(row["close"])
        rv = float(row["rsi"]) if not np.isnan(row["rsi"]) else 50.0
        atr_v = float(row["atr"]) if not np.isnan(row["atr"]) else 0.0

        if has_position and position_side:
            # 回归到中性区域平仓
            if position_side == "long" and (rv >= 50 or sentiment == "BEAR"):
                return Signal(symbol, "close", f"RSI回归/舆情平多 rsi={rv:.1f}")
            if position_side == "short" and (rv <= 50 or sentiment == "BULL"):
                return Signal(symbol, "close", f"RSI回归/舆情平空 rsi={rv:.1f}")
            return Signal(symbol, "hold", f"持仓中 rsi={rv:.1f}")

        if rv <= self.oversold:
            block = gate_open_by_sentiment(sentiment, "long")
            if block:
                return Signal(symbol, "hold", block)
            stop, tp = stops_from_atr(price, atr_v, "long", self.atr_stop_mult, self.take_profit_rr)
            return Signal(
                symbol,
                "open_long",
                f"RSI超卖 {rv:.1f}<={self.oversold}",
                entry=price,
                stop=stop,
                take_profit=tp,
                strength=(self.oversold - rv) / 100,
            )

        if rv >= self.overbought:
            block = gate_open_by_sentiment(sentiment, "short")
            if block:
                return Signal(symbol, "hold", block)
            stop, tp = stops_from_atr(price, atr_v, "short", self.atr_stop_mult, self.take_profit_rr)
            return Signal(
                symbol,
                "open_short",
                f"RSI超买 {rv:.1f}>={self.overbought}",
                entry=price,
                stop=stop,
                take_profit=tp,
                strength=(rv - self.overbought) / 100,
            )

        return Signal(symbol, "hold", f"RSI中性 {rv:.1f}")
