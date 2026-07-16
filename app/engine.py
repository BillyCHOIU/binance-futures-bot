from __future__ import annotations

import logging
import threading
import time
import traceback
from pathlib import Path
from typing import Callable

from app.config_loader import load_config, setup_logging
from app.exchange.binance_f import BinanceFutures
from app.news.sentiment import SentimentEngine
from app.paths import app_dir
from app.risk.manager import RiskManager
from app.storage.db import Store
from app.strategy.registry import build_strategy, list_strategy_choices, resolve_active_from_config

logger = logging.getLogger("fluxbot.engine")


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
        self.risk = RiskManager(
            daily_loss_limit=float(self.cfg["risk"]["daily_loss_limit"]),
            max_drawdown=float(self.cfg["risk"]["max_drawdown"]),
            risk_per_trade=float(self.cfg["trading"]["risk_per_trade"]),
            max_notional_pct=float(self.cfg["trading"]["max_notional_pct"]),
            max_positions=int(self.cfg["trading"]["max_positions"]),
            reset_peak_on_start=bool(self.cfg["risk"].get("reset_peak_on_start", True)),
            on_log=self._log,
        )
        sc = self.cfg.get("strategy") or {}
        self.strategy_id, self.strategy_params = resolve_active_from_config(self.cfg)
        self.strategy = build_strategy(self.strategy_id, self.strategy_params, on_log=self._log)
        nc = self.cfg.get("news") or {}
        sources = nc.get("sources") or {}
        self.news = SentimentEngine(
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
            on_log=self._log,
        )
        self._log(f"舆情源状态: {self.news.source_status()}")
        self.news_enabled = bool(nc.get("enabled", True))
        # 本地止损跟踪 {symbol: {side, stop, tp, amount}}
        self._brackets: dict[str, dict] = {}
        self.leverage = int(self.cfg["trading"].get("leverage", 5))
        self.max_leverage = int(self.cfg["trading"].get("max_leverage", 10))
        self.leverage = max(1, min(self.leverage, self.max_leverage))

    def set_position_limit(self, max_positions: int) -> None:
        """GUI 调用：1=单仓，>1=多仓上限。"""
        self.risk.set_max_positions(max_positions)

    def set_leverage(self, leverage: int) -> None:
        """GUI 调用：设置开仓杠杆（受 max_leverage 限制）。"""
        try:
            lev = int(leverage)
        except (TypeError, ValueError):
            lev = 5
        self.leverage = max(1, min(lev, self.max_leverage))
        self._log(f"杠杆已设为 {self.leverage}x（上限 {self.max_leverage}x）")

    def list_strategies(self) -> list[tuple[str, str, str]]:
        return list_strategy_choices()

    def set_strategy(self, strategy_id: str, params: dict | None = None) -> None:
        """切换策略（运行中也可换，下一 tick 生效）。"""
        if params is not None:
            self.strategy_params = dict(params)
        self.strategy_id = strategy_id
        self.strategy = build_strategy(strategy_id, self.strategy_params, on_log=self._log)
        # 写回内存 cfg
        self.cfg.setdefault("strategy", {})
        self.cfg["strategy"]["active"] = strategy_id
        self.cfg["strategy"]["params"] = dict(self.strategy_params)

    def reload_strategy(self) -> None:
        """重新扫描插件目录并按当前 id 重建。"""
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
        self._brackets.clear()
        self._log(f"已请求平仓 {n} 个仓位")

    def _loop(self) -> None:
        tick = int(self.cfg["trading"].get("tick_seconds", 30))
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
        symbols = list(self.cfg["trading"]["symbols"])
        tf = self.cfg["trading"]["timeframe"]
        leverage = max(1, min(int(self.leverage), int(self.max_leverage)))

        equity = self.exchange.fetch_equity()
        self.risk.on_equity(equity)
        self.store.snapshot_equity(equity, self.risk.state.peak_equity)

        # 单仓：统计账户全部持仓（不限白名单），避免漏算其它币
        all_positions = self.exchange.fetch_positions(None)
        positions = [p for p in all_positions if p.symbol in symbols] or [
            p for p in all_positions if any(p.symbol.startswith(s.split("/")[0]) for s in symbols)
        ]
        # 策略平仓/止损仍优先白名单内；计数用全部
        pos_map = {p.symbol: p for p in all_positions}
        # 白名单映射（用于策略遍历）
        watch_pos = {p.symbol: p for p in all_positions if p.symbol in symbols}
        if not watch_pos and all_positions:
            # 符号格式差异时尽量匹配 base
            bases = {s.split("/")[0] for s in symbols}
            for p in all_positions:
                base = p.symbol.split("/")[0] if "/" in p.symbol else p.symbol
                if base in bases:
                    watch_pos[p.symbol] = p

        # 本地止损/止盈检查
        self._check_brackets(pos_map)

        if self.news_enabled:
            self.news.refresh()
            g_sent = self.news.global_sentiment()
        else:
            g_sent = "NEUTRAL"

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

        # 先处理平仓信号（仅机器人关注的仓）
        for sym, pos in list(watch_pos.items()):
            sent = self.news.sentiment_for_symbol(sym) if self.news_enabled else "NEUTRAL"
            ohlcv = self.exchange.fetch_ohlcv(sym, tf, limit=120)
            sig = self.strategy.evaluate(
                sym, ohlcv, sent, has_position=True, position_side=pos.side
            )
            if sig.action == "close":
                try:
                    self.exchange.close_position(pos)
                    self.store.log_trade(sym, f"close_{pos.side}", pos.contracts, pos.entry_price, sig.reason)
                    self._brackets.pop(sym, None)
                    self._log(f"平仓 {sym} {pos.side}: {sig.reason}")
                except Exception as e:
                    self._log(f"平仓失败 {sym}: {e}")

        # 刷新全部持仓后再看开仓
        all_positions = self.exchange.fetch_positions(None)
        can, reason = self.risk.can_open(len(all_positions))
        if not can:
            self._log(f"不可开仓: {reason}")
            return
        # 单仓时：本地 bracket 未清也不新开；多仓时只挡「同标的」
        if int(self.risk.max_positions) <= 1 and self._brackets:
            self._log(f"不可开仓: 本地仍有未完结仓位记录 {list(self._brackets.keys())}")
            return

        # 每 tick 最多新开 1 个（最强信号），总仓数受 max_positions 限制
        best = None
        for sym in symbols:
            if any(
                p.symbol == sym or p.symbol.startswith(sym.split("/")[0])
                for p in all_positions
            ):
                continue
            if sym in self._brackets:
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
            # 下单前再扫全账户
            all_positions = self.exchange.fetch_positions(None)
            can2, reason2 = self.risk.can_open(len(all_positions))
            if not can2:
                self._log(f"拦截开仓: {reason2}")
                return
            if any(
                p.symbol == best.symbol or p.symbol.startswith(best.symbol.split("/")[0])
                for p in all_positions
            ):
                self._log(f"拦截开仓: {best.symbol} 已有仓")
                return

            self.exchange.set_leverage(best.symbol, leverage)
            self.exchange.set_margin_isolated(best.symbol)
            qty = self.risk.position_size(equity, best.entry, best.stop)
            qty = self.exchange.market_amount_to_precision(best.symbol, qty)
            min_cost_guard = 5.0
            if qty * best.entry < min_cost_guard:
                self._log(
                    f"跳过 {best.symbol}: 名义过小 qty={qty} notional≈{qty * best.entry:.2f} "
                    f"(账户太小或风险参数过低)"
                )
                return

            side = "buy" if best.action == "open_long" else "sell"
            order = self.exchange.create_market_order(best.symbol, side, qty)
            avg = float(order.get("average") or order.get("price") or best.entry or 0)
            self.store.log_trade(best.symbol, best.action, qty, avg, best.reason)
            self._brackets[best.symbol] = {
                "side": "long" if best.action == "open_long" else "short",
                "stop": best.stop,
                "tp": best.take_profit,
                "amount": qty,
            }
            mode = "单仓" if int(self.risk.max_positions) <= 1 else f"多仓≤{self.risk.max_positions}"
            self._log(
                f"开仓({mode}) {best.action} {best.symbol} qty={qty} entry≈{avg} "
                f"stop={best.stop:.4f} tp={best.take_profit:.4f} | {best.reason}"
            )
        except Exception as e:
            self._log(f"开仓失败 {best.symbol}: {e}")

    def _check_brackets(self, pos_map: dict) -> None:
        assert self.exchange is not None
        for sym, br in list(self._brackets.items()):
            pos = pos_map.get(sym)
            if not pos:
                self._brackets.pop(sym, None)
                continue
            try:
                t = self.exchange.fetch_ticker(sym)
                price = float(t.get("last") or t.get("close") or 0)
            except Exception:
                continue
            if price <= 0:
                continue
            hit = False
            if br["side"] == "long" and (price <= br["stop"] or price >= br["tp"]):
                hit = True
            if br["side"] == "short" and (price >= br["stop"] or price <= br["tp"]):
                hit = True
            if hit:
                try:
                    self.exchange.close_position(pos)
                    self.store.log_trade(sym, f"bracket_close_{br['side']}", pos.contracts, price, "SL/TP")
                    self._log(f"触发止损/止盈平仓 {sym} price={price}")
                except Exception as e:
                    self._log(f"SL/TP 平仓失败 {sym}: {e}")
                finally:
                    self._brackets.pop(sym, None)
