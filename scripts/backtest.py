"""Simple offline backtest for built-in strategies on public OHLCV."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import ccxt

from app.strategy.registry import BUILTIN, build_strategy


@dataclass
class Trade:
    side: str
    entry: float
    exit: float
    pnl_pct: float
    reason_in: str
    reason_out: str


def fetch_ohlcv(symbol: str = "BTC/USDT:USDT", timeframe: str = "15m", limit: int = 500) -> list:
    ex = ccxt.binanceusdm({"enableRateLimit": True})
    return ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)


def run_backtest(
    strategy_id: str,
    ohlcv: list,
    sentiment: str = "BOTH",
    fee_bps: float = 4.0,
) -> dict[str, Any]:
    st = build_strategy(strategy_id, BUILTIN.get(strategy_id, {}).get("defaults") or {}, lambda m: None)
    pos = None  # {side, entry, i}
    trades: list[Trade] = []
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    fee = fee_bps / 10000.0

    # need enough bars; evaluate on expanding window min 80
    min_bars = 80
    for i in range(min_bars, len(ohlcv)):
        window = ohlcv[: i + 1]
        price = float(ohlcv[i][4])
        if pos is None:
            sig = st.evaluate("BTC/USDT:USDT", window, sentiment, False)  # type: ignore[arg-type]
            if sig.action in ("open_long", "open_short"):
                pos = {
                    "side": "long" if sig.action == "open_long" else "short",
                    "entry": price,
                    "i": i,
                    "reason": sig.reason,
                }
                equity *= 1 - fee
        else:
            sig = st.evaluate(
                "BTC/USDT:USDT",
                window,
                sentiment,
                True,
                position_side=pos["side"],
            )  # type: ignore[arg-type]
            # also SL/TP if strategy set them on open - approximate with last open levels not stored;
            # use strategy close only
            if sig.action == "close":
                entry = pos["entry"]
                if pos["side"] == "long":
                    pnl = (price - entry) / entry
                else:
                    pnl = (entry - price) / entry
                pnl -= fee  # exit fee
                equity *= 1 + pnl
                trades.append(
                    Trade(pos["side"], entry, price, pnl, pos["reason"], sig.reason)
                )
                pos = None
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)

    wins = [t for t in trades if t.pnl_pct > 0]
    return {
        "strategy": strategy_id,
        "bars": len(ohlcv),
        "trades": len(trades),
        "win_rate": (len(wins) / len(trades)) if trades else 0.0,
        "total_return": equity - 1.0,
        "max_drawdown": max_dd,
        "avg_trade": (sum(t.pnl_pct for t in trades) / len(trades)) if trades else 0.0,
    }


def main() -> None:
    print("Fetching BTC/USDT:USDT 15m OHLCV…")
    ohlcv = fetch_ohlcv(limit=500)
    print(f"bars={len(ohlcv)}")
    rows = []
    for sid in BUILTIN:
        r = run_backtest(sid, ohlcv, sentiment="BOTH")
        rows.append(r)
        print(
            f"{sid:16} trades={r['trades']:3d} win={r['win_rate']:.1%} "
            f"ret={r['total_return']:+.2%} mdd={r['max_drawdown']:.2%} avg={r['avg_trade']:+.3%}"
        )
    print("---")
    print("NOTE: 历史回测 ≠ 未来收益；仅用于策略相对对比与冒烟。")
    best = max(rows, key=lambda x: x["total_return"]) if rows else None
    if best:
        print(f"本段样本收益最高: {best['strategy']} ({best['total_return']:+.2%})")


if __name__ == "__main__":
    main()
