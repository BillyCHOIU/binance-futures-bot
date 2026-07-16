from __future__ import annotations

import numpy as np

from app.strategy.base import (
    Sentiment,
    Signal,
    atr,
    ema,
    gate_open_by_sentiment,
    ohlcv_to_df,
    stops_from_atr,
)


class TrendStrategy:
    """舆情门控 + EMA 趋势 + ATR 止损止盈。"""

    id = "trend_ema"
    name = "EMA趋势"

    def __init__(
        self,
        ema_fast: int = 20,
        ema_slow: int = 60,
        atr_period: int = 14,
        atr_stop_mult: float = 1.5,
        take_profit_rr: float = 2.0,
        **_kwargs,
    ):
        self.ema_fast = int(ema_fast)
        self.ema_slow = int(ema_slow)
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
        need = max(self.ema_slow, self.atr_period) + 5
        if not ohlcv or len(ohlcv) < need:
            return Signal(symbol, "hold", "K线不足")

        df = ohlcv_to_df(ohlcv)
        df["ema_f"] = ema(df["close"], self.ema_fast)
        df["ema_s"] = ema(df["close"], self.ema_slow)
        df["atr"] = atr(df, self.atr_period)
        row, prev = df.iloc[-1], df.iloc[-2]
        price = float(row["close"])
        atr_v = float(row["atr"]) if not np.isnan(row["atr"]) else 0.0
        ef, es = float(row["ema_f"]), float(row["ema_s"])
        pef, pes = float(prev["ema_f"]), float(prev["ema_s"])
        trend_up = ef > es
        trend_down = ef < es
        cross_up = pef <= pes and ef > es
        cross_down = pef >= pes and ef < es

        if has_position and position_side:
            if position_side == "long" and (trend_down or sentiment == "BEAR"):
                return Signal(symbol, "close", f"平多: trend_down={trend_down} sent={sentiment}")
            if position_side == "short" and (trend_up or sentiment == "BULL"):
                return Signal(symbol, "close", f"平空: trend_up={trend_up} sent={sentiment}")
            return Signal(symbol, "hold", "持仓中，趋势未反转")

        if atr_v <= 0:
            return Signal(symbol, "hold", "ATR 无效")

        if trend_up or cross_up:
            block = gate_open_by_sentiment(sentiment, "long")
            if block:
                return Signal(symbol, "hold", block)
            stop, tp = stops_from_atr(price, atr_v, "long", self.atr_stop_mult, self.take_profit_rr)
            return Signal(
                symbol,
                "open_long",
                f"趋势多 EMA{self.ema_fast}/{self.ema_slow} + 舆情{sentiment}",
                entry=price,
                stop=stop,
                take_profit=tp,
                strength=abs(ef - es) / max(price, 1e-9),
            )

        if trend_down or cross_down:
            block = gate_open_by_sentiment(sentiment, "short")
            if block:
                return Signal(symbol, "hold", block)
            stop, tp = stops_from_atr(price, atr_v, "short", self.atr_stop_mult, self.take_profit_rr)
            return Signal(
                symbol,
                "open_short",
                f"趋势空 EMA{self.ema_fast}/{self.ema_slow} + 舆情{sentiment}",
                entry=price,
                stop=stop,
                take_profit=tp,
                strength=abs(ef - es) / max(price, 1e-9),
            )

        return Signal(symbol, "hold", f"无明确趋势 (up={trend_up}, down={trend_down})")
