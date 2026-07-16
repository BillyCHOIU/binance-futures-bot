from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import ccxt

logger = logging.getLogger("fluxbot.exchange")


@dataclass
class Position:
    symbol: str
    side: str  # long / short
    contracts: float
    entry_price: float
    unrealized_pnl: float
    leverage: float


class BinanceFutures:
    """U 本位永续封装（ccxt）。"""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = True,
        on_log: Callable[[str], None] | None = None,
    ):
        self.on_log = on_log or (lambda m: None)
        opts: dict[str, Any] = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        }
        self.exchange = ccxt.binanceusdm(opts)
        if testnet:
            self.exchange.set_sandbox_mode(True)
            self.on_log("已启用币安 U 本位 Testnet")
        else:
            self.on_log("警告：当前为实盘模式")
        self._markets_loaded = False

    def log(self, msg: str) -> None:
        logger.info(msg)
        self.on_log(msg)

    def load_markets(self) -> None:
        if not self._markets_loaded:
            self.exchange.load_markets()
            self._markets_loaded = True

    def fetch_balance_usdt(self) -> float:
        bal = self.exchange.fetch_balance()
        # USDT 权益优先 total / free
        usdt = bal.get("USDT") or {}
        for k in ("total", "free", "used"):
            if usdt.get(k) is not None:
                try:
                    return float(usdt[k] if k == "total" else usdt.get("total") or usdt.get("free") or 0)
                except (TypeError, ValueError):
                    pass
        # 部分返回在 info
        total = usdt.get("total")
        if total is not None:
            return float(total)
        free = usdt.get("free")
        return float(free or 0)

    def fetch_equity(self) -> float:
        """尽量取合约账户权益。"""
        try:
            bal = self.exchange.fetch_balance()
            usdt = bal.get("USDT") or {}
            if usdt.get("total") is not None:
                return float(usdt["total"])
            # info.totalWalletBalance / totalMarginBalance
            info = bal.get("info") or {}
            for key in ("totalMarginBalance", "totalWalletBalance", "availableBalance"):
                if info.get(key) is not None:
                    return float(info[key])
            return float(usdt.get("free") or 0)
        except Exception as e:
            self.log(f"读取权益失败: {e}")
            return 0.0

    def set_leverage(self, symbol: str, leverage: int) -> None:
        self.load_markets()
        try:
            self.exchange.set_leverage(leverage, symbol)
            self.log(f"{symbol} 杠杆设为 {leverage}x")
        except Exception as e:
            # 已是目标杠杆时可能报错，忽略
            self.log(f"设置杠杆提示 {symbol}: {e}")

    def set_margin_isolated(self, symbol: str) -> None:
        self.load_markets()
        try:
            if hasattr(self.exchange, "set_margin_mode"):
                self.exchange.set_margin_mode("isolated", symbol)
        except Exception as e:
            self.log(f"保证金模式 {symbol}: {e}")

    def fetch_ohlcv(self, symbol: str, timeframe: str = "15m", limit: int = 120) -> list:
        self.load_markets()
        return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)

    def fetch_ticker(self, symbol: str) -> dict:
        self.load_markets()
        return self.exchange.fetch_ticker(symbol)

    def fetch_positions(self, symbols: list[str] | None = None) -> list[Position]:
        self.load_markets()
        # symbols=None → 拉全账户，用于单仓限制
        try:
            raw = self.exchange.fetch_positions(symbols) if symbols else self.exchange.fetch_positions()
        except TypeError:
            raw = self.exchange.fetch_positions(symbols)
        out: list[Position] = []
        for p in raw:
            contracts = float(p.get("contracts") or 0)
            if abs(contracts) < 1e-12:
                continue
            side = (p.get("side") or "").lower()
            if not side:
                side = "long" if contracts > 0 else "short"
            out.append(
                Position(
                    symbol=p.get("symbol") or "",
                    side=side,
                    contracts=abs(contracts),
                    entry_price=float(p.get("entryPrice") or 0),
                    unrealized_pnl=float(p.get("unrealizedPnl") or 0),
                    leverage=float(p.get("leverage") or 0),
                )
            )
        return out

    def market_amount_to_precision(self, symbol: str, amount: float) -> float:
        self.load_markets()
        return float(self.exchange.amount_to_precision(symbol, amount))

    def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        reduce_only: bool = False,
        position_side: str | None = None,
    ) -> dict:
        """
        side: buy / sell
        单向持仓默认；若账户是对冲模式可传 position_side LONG/SHORT
        """
        self.load_markets()
        amount = self.market_amount_to_precision(symbol, amount)
        if amount <= 0:
            raise ValueError(f"下单数量无效: {amount}")

        params: dict[str, Any] = {}
        if reduce_only:
            params["reduceOnly"] = True
        if position_side:
            params["positionSide"] = position_side

        order = self.exchange.create_order(symbol, "market", side, amount, params=params)
        self.log(f"下单成功 {symbol} {side} amount={amount} reduceOnly={reduce_only}")
        return order

    def close_position(self, pos: Position) -> dict | None:
        if pos.contracts <= 0:
            return None
        # 平多卖，平空买
        side = "sell" if pos.side == "long" else "buy"
        return self.create_market_order(
            pos.symbol,
            side,
            pos.contracts,
            reduce_only=True,
        )

    def close_all(self, symbols: list[str] | None = None) -> int:
        positions = self.fetch_positions(symbols)
        n = 0
        for p in positions:
            try:
                self.close_position(p)
                n += 1
            except Exception as e:
                self.log(f"平仓失败 {p.symbol}: {e}")
        return n
