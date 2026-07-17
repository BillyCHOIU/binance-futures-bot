from __future__ import annotations

import logging
import threading
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from app.config_loader import load_config, setup_logging
from app.exchange.binance_f import BinanceFutures, Position, positions_match
from app.news.sentiment import SentimentEngine
from app.paths import app_dir
from app.risk.manager import RiskManager
from app.storage.db import Store
from app.strategy.registry import build_strategy, list_strategy_choices, resolve_active_from_config

logger = logging.getLogger("fluxbot.engine")


@dataclass
class Bracket:
    side: str  # long / short
    stop: float
    tp: float
    amount: float


@dataclass
class BracketBook:
    """本地止损/止盈跟踪。"""

    items: dict[str, Bracket] = field(default_factory=dict)

    def set(self, symbol: str, side: str, stop: float, tp: float, amount: float) -> None:
        self.items[symbol] = Bracket(side=side, stop=stop, tp=tp, amount=amount)

    def pop(self, symbol: str) -> None:
        self.items.pop(symbol, None)

    def clear(self) -> None:
        self.items.clear()

    def __contains__(self, symbol: str) -> bool:
        return symbol in self.items

    def __bool__(self) -> bool:
        return bool(self.items)

    def keys(self):
        return self.items.keys()

    def check_hits(self, exchange: BinanceFutures, pos_map: dict[str, Position]) -> list[tuple[str, Bracket, Position, float]]:
        hits: list[tuple[str, Bracket, Position, float]] = []
        for sym, br in list(self.items.items()):
            pos = pos_map.get(sym)
            if not pos:
                self.pop(sym)
                continue
            try:
                t = exchange.fetch_ticker(sym)
                price = float(t.get("last") or t.get("close") or 0)
            except Exception:
                continue
            if price <= 0:
                continue
            hit = (
                (br.side == "long" and (price <= br.stop or price >= br.tp))
                or (br.side == "short" and (price >= br.stop or price <= br.tp))
            )
            if hit:
                hits.append((sym, br, pos, price))
        return hits


def _build_news(cfg: dict[str, Any], on_log: Callable[[str], None]) -> SentimentEngine:
    nc = cfg.get("news") or {}
    sources = nc.get("sources") or {}
    return SentimentEngine(
        bull_threshold=float(nc.get("bull_threshold", 0.25)),
        bear_threshold=float(nc.get("bear_threshold", -0.25)),
        refresh_seconds=int(nc.get("refresh_seconds", 120)),
        enable_binance=bool(sources.get("binance_announcement", True)),
        enable_rss=bool(sources.get("rss", True)),
        enable_reddit=bool(sources.get("reddit", True)),
        enable_x=bool(sources.get("x", True)),
        enable_cryptopanic=bool(sources.get("cryptopanic", True)),
        reddit_client_id=str(nc.get("reddit_client_id") or ""),
        reddit_client_secret=str(nc.get("reddit_client_secret") or ""),
        reddit_user_agent=str(nc.get("reddit_user_agent") or "FluxBot/0.1 by local-user"),
        x_bearer_token=str(nc.get("x_bearer_token") or ""),
        cryptopanic_token=str(nc.get("cryptopanic_token") or ""),
        http_proxy=str(nc.get("http_proxy") or ""),
        on_log=on_log,
    )


def _filter_watch_positions(all_positions: list[Position], symbols: list[str]) -> dict[str, Position]:
    watch = {p.symbol: p for p in all_positions if p.symbol in symbols}
    if watch or not all_positions:
        return watch
    bases = {s.split("/")[0] for s in symbols}
    for p in all_positions:
        base = p.symbol.split("/")[0] if "/" in p.symbol else p.symbol
        if base in bases:
            watch[p.symbol] = p
    return watch


class TradingEngine:
    def __init__(self, on_log: Callable[[str], None] | None = None):
        self.on_log = on_log or (lambda m: None)
        self.cfg = load_config()
        setup_logging(app_dir() / "logs")
        self.store = Store(app_dir() / "data" / "fluxbot.db")
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.running = False
        self.last_status: dict = {}

        self.exchange: BinanceFutures | None = None
        self.risk = RiskManager.from_config(self.cfg, on_log=self._log)
        self.strategy_id, self.strategy_params = resolve_active_from_config(self.cfg)
        self.strategy = build_strategy(self.strategy_id, self.strategy_params, on_log=self._log)
        self.news = _build_news(self.cfg, self._log)
        self._log(f"舆情源状态: {self.news.source_status()}")
        self.news_enabled = bool((self.cfg.get("news") or {}).get("enabled", True))
        self.brackets = BracketBook()
        trading = self.cfg.get("trading") or {}
        self.leverage = max(1, min(int(trading.get("leverage", 5)), int(trading.get("max_leverage", 10))))
        self.max_leverage = int(trading.get("max_leverage", 10))

    # —— GUI API ——
    def set_position_limit(self, max_positions: int) -> None:
        self.risk.set_max_positions(max_positions)

    def set_leverage(self, leverage: int) -> None:
        try:
            lev = int(leverage)
        except (TypeError, ValueError):
            lev = 5
        self.leverage = max(1, min(lev, self.max_leverage))
        self._log(f"杠杆已设为 {self.leverage}x（上限 {self.max_leverage}x）")

    def list_strategies(self) -> list[tuple[str, str, str]]:
        return list_strategy_choices()

    def set_strategy(self, strategy_id: str, params: dict | None = None) -> None:
        if params is not None:
            self.strategy_params = dict(params)
        self.strategy_id = strategy_id
        self.strategy = build_strategy(strategy_id, self.strategy_params, on_log=self._log)
        self.cfg.setdefault("strategy", {})
        self.cfg["strategy"]["active"] = strategy_id
        self.cfg["strategy"]["params"] = dict(self.strategy_params)

    def reload_strategy(self) -> None:
        self.strategy = build_strategy(self.strategy_id, self.strategy_params, on_log=self._log)

    def _log(self, msg: str) -> None:
        logger.info(msg)
        self.store.log_event("info", msg)
        try:
            self.on_log(msg)
        except Exception:
            pass

    def connect(self, api_key: str, api_secret: str, testnet: bool) -> None:
        if not api_key or not api_secret:
            raise ValueError("请填写 API Key 和 Secret")
        self.exchange = BinanceFutures(api_key, api_secret, testnet=testnet, on_log=self._log)
        eq = self.exchange.fetch_equity()
        self.risk.on_equity(eq)
        self._log(f"连接成功 | testnet={testnet} | equity≈{eq:.4f} USDT")

    def start(self) -> None:
        if self.running:
            return
        if not self.exchange:
            raise RuntimeError("请先连接交易所")
        self._stop.clear()
        self.running = True
        self._thread = threading.Thread(target=self._loop, name="fluxbot-engine", daemon=True)
        self._thread.start()
        self._log("引擎已启动")

    def stop(self) -> None:
        self._stop.set()
        self.running = False
        self._log("引擎停止中…")

    def close_all(self) -> None:
        if not self.exchange:
            return
        n = self.exchange.close_all(self.cfg["trading"]["symbols"])
        self.brackets.clear()
        self._log(f"已请求平仓 {n} 个仓位")

    def _loop(self) -> None:
        tick = int((self.cfg.get("trading") or {}).get("tick_seconds", 30))
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                self._log(f"tick 异常: {e}")
                logger.error(traceback.format_exc())
            self._stop.wait(tick)
        self.running = False
        self._log("引擎已停止")

    def _tick(self) -> None:
        assert self.exchange is not None
        trading = self.cfg["trading"]
        symbols = list(trading["symbols"])
        tf = trading["timeframe"]
        leverage = max(1, min(int(self.leverage), int(self.max_leverage)))

        equity = self.exchange.fetch_equity()
        self.risk.on_equity(equity)
        self.store.snapshot_equity(equity, self.risk.state.peak_equity)

        all_positions = self.exchange.fetch_positions(None)
        pos_map = {p.symbol: p for p in all_positions}
        watch_pos = _filter_watch_positions(all_positions, symbols)

        self._apply_bracket_hits(pos_map)

        g_sent = self.news.global_sentiment() if self.news_enabled else "NEUTRAL"

        self.last_status = {
            "equity": equity,
            "peak": self.risk.state.peak_equity,
            "halted": self.risk.state.halted,
            "halt_reason": self.risk.state.halt_reason,
            "positions": len(all_positions),
            "global_sentiment": g_sent,
            "running": self.running,
            "max_positions": self.risk.max_positions,
            "single_position": int(self.risk.max_positions) <= 1,
        }
        mode = "单仓" if int(self.risk.max_positions) <= 1 else f"多仓≤{self.risk.max_positions}"
        self._log(
            f"tick equity={equity:.4f} peak={self.risk.state.peak_equity:.4f} "
            f"pos={len(all_positions)}/{self.risk.max_positions}({mode}) "
            f"sentiment={g_sent} halted={self.risk.state.halted}"
        )

        self._process_exits(watch_pos, tf)
        self._process_entries(symbols, all_positions, equity, leverage, tf)

    def _apply_bracket_hits(self, pos_map: dict[str, Position]) -> None:
        assert self.exchange is not None
        for sym, br, pos, price in self.brackets.check_hits(self.exchange, pos_map):
            try:
                self.exchange.close_position(pos)
                self.store.log_trade(sym, f"bracket_close_{br.side}", pos.contracts, price, "SL/TP")
                self._log(f"触发止损/止盈平仓 {sym} price={price}")
            except Exception as e:
                self._log(f"SL/TP 平仓失败 {sym}: {e}")
            finally:
                self.brackets.pop(sym)

    def _process_exits(self, watch_pos: dict[str, Position], tf: str) -> None:
        assert self.exchange is not None
        for sym, pos in list(watch_pos.items()):
            sent = self.news.sentiment_for_symbol(sym) if self.news_enabled else "NEUTRAL"
            ohlcv = self.exchange.fetch_ohlcv(sym, tf, limit=120)
            sig = self.strategy.evaluate(sym, ohlcv, sent, has_position=True, position_side=pos.side)
            if sig.action != "close":
                continue
            try:
                self.exchange.close_position(pos)
                self.store.log_trade(sym, f"close_{pos.side}", pos.contracts, pos.entry_price, sig.reason)
                self.brackets.pop(sym)
                self._log(f"平仓 {sym} {pos.side}: {sig.reason}")
            except Exception as e:
                self._log(f"平仓失败 {sym}: {e}")

    def _process_entries(
        self,
        symbols: list[str],
        all_positions: list[Position],
        equity: float,
        leverage: int,
        tf: str,
    ) -> None:
        assert self.exchange is not None
        can, reason = self.risk.can_open(len(all_positions))
        if not can:
            self._log(f"不可开仓: {reason}")
            return
        if int(self.risk.max_positions) <= 1 and self.brackets:
            self._log(f"不可开仓: 本地仍有未完结仓位记录 {list(self.brackets.keys())}")
            return

        best = None
        for sym in symbols:
            if any(positions_match(p.symbol, sym) for p in all_positions):
                continue
            if sym in self.brackets:
                continue
            sent = self.news.sentiment_for_symbol(sym) if self.news_enabled else "BOTH"
            ohlcv = self.exchange.fetch_ohlcv(sym, tf, limit=120)
            sig = self.strategy.evaluate(sym, ohlcv, sent, has_position=False)
            if sig.action in ("open_long", "open_short"):
                if best is None or sig.strength > best.strength:
                    best = sig
        if not best:
            return

        try:
            all_positions = self.exchange.fetch_positions(None)
            can2, reason2 = self.risk.can_open(len(all_positions))
            if not can2:
                self._log(f"拦截开仓: {reason2}")
                return
            if any(positions_match(p.symbol, best.symbol) for p in all_positions):
                self._log(f"拦截开仓: {best.symbol} 已有仓")
                return

            self.exchange.set_leverage(best.symbol, leverage)
            self.exchange.set_margin_isolated(best.symbol)
            qty = self.risk.position_size(equity, best.entry, best.stop)
            qty = self.exchange.market_amount_to_precision(best.symbol, qty)
            if qty * best.entry < 5.0:
                self._log(
                    f"跳过 {best.symbol}: 名义过小 qty={qty} notional≈{qty * best.entry:.2f}"
                )
                return

            side = "buy" if best.action == "open_long" else "sell"
            order = self.exchange.create_market_order(best.symbol, side, qty)
            avg = float(order.get("average") or order.get("price") or best.entry or 0)
            self.store.log_trade(best.symbol, best.action, qty, avg, best.reason)
            self.brackets.set(
                best.symbol,
                "long" if best.action == "open_long" else "short",
                best.stop,
                best.take_profit,
                qty,
            )
            mode = "单仓" if int(self.risk.max_positions) <= 1 else f"多仓≤{self.risk.max_positions}"
            self._log(
                f"开仓({mode}) {best.action} {best.symbol} qty={qty} entry≈{avg} "
                f"stop={best.stop:.4f} tp={best.take_profit:.4f} | {best.reason}"
            )
        except Exception as e:
            self._log(f"开仓失败 {best.symbol}: {e}")
