"""
用户自定义策略示例 — 复制本文件改名后修改逻辑即可。

放在：程序目录 / strategies / 你的名字.py
然后在界面选择「[插件] …」或点「重载策略」。

约定：
  STRATEGY_ID / STRATEGY_NAME / STRATEGY_DESC / DEFAULTS
  class Strategy:
      def evaluate(self, symbol, ohlcv, sentiment, has_position, position_side=None) -> Signal
"""
from __future__ import annotations

# 从内置工具导入（打包/开发均可）
from app.strategy.base import (
    Sentiment,
    Signal,
    atr,
    ema,
    gate_open_by_sentiment,
    ohlcv_to_df,
    stops_from_atr,
)

STRATEGY_ID = "example_dual_ma"
STRATEGY_NAME = "示例双均线"
STRATEGY_DESC = "自定义示例：快慢均线 + 舆情门控（可复制改写）"
DEFAULTS = {
    "fast": 10,
    "slow": 30,
    "atr_period": 14,
    "atr_stop_mult": 1.5,
    "take_profit_rr": 2.0,
}


class Strategy:
    id = STRATEGY_ID
    name = STRATEGY_NAME

    def __init__(
        self,
        fast: int = 10,
        slow: int = 30,
        atr_period: int = 14,
        atr_stop_mult: float = 1.5,
        take_profit_rr: float = 2.0,
        **_kwargs,
    ):
        self.fast = int(fast)
        self.slow = int(slow)
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
        if not ohlcv or len(ohlcv) < self.slow + 5:
            return Signal(symbol, "hold", "K线不足")

        df = ohlcv_to_df(ohlcv)
        df["f"] = ema(df["close"], self.fast)
        df["s"] = ema(df["close"], self.slow)
        df["atr"] = atr(df, self.atr_period)
        row = df.iloc[-1]
        price = float(row["close"])
        fv, sv = float(row["f"]), float(row["s"])
        atr_v = float(row["atr"]) if row["atr"] == row["atr"] else price * 0.01

        bull = fv > sv
        bear = fv < sv

        if has_position and position_side:
            if position_side == "long" and (bear or sentiment == "BEAR"):
                return Signal(symbol, "close", "示例策略平多")
            if position_side == "short" and (bull or sentiment == "BULL"):
                return Signal(symbol, "close", "示例策略平空")
            return Signal(symbol, "hold", "示例策略持仓")

        if bull:
            block = gate_open_by_sentiment(sentiment, "long")
            if block:
                return Signal(symbol, "hold", block)
            stop, tp = stops_from_atr(
                price, atr_v, "long", self.atr_stop_mult, self.take_profit_rr
            )
            return Signal(
                symbol,
                "open_long",
                f"示例双均线多 fast{self.fast}>slow{self.slow}",
                entry=price,
                stop=stop,
                take_profit=tp,
                strength=abs(fv - sv) / max(price, 1e-9),
            )

        if bear:
            block = gate_open_by_sentiment(sentiment, "short")
            if block:
                return Signal(symbol, "hold", block)
            stop, tp = stops_from_atr(
                price, atr_v, "short", self.atr_stop_mult, self.take_profit_rr
            )
            return Signal(
                symbol,
                "open_short",
                f"示例双均线空 fast{self.fast}<slow{self.slow}",
                entry=price,
                stop=stop,
                take_profit=tp,
                strength=abs(fv - sv) / max(price, 1e-9),
            )

        return Signal(symbol, "hold", "示例策略无信号")
