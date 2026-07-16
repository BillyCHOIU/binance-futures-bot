from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger("fluxbot.risk")


@dataclass
class RiskState:
    day_key: str = ""
    day_start_equity: float = 0.0
    peak_equity: float = 0.0
    halted: bool = False
    halt_reason: str = ""


@dataclass
class RiskManager:
    daily_loss_limit: float = 0.04
    max_drawdown: float = 0.12
    risk_per_trade: float = 0.02
    max_notional_pct: float = 0.5
    max_positions: int = 1
    reset_peak_on_start: bool = True
    on_log: Callable[[str], None] = field(default=lambda m: None)
    state: RiskState = field(default_factory=RiskState)

    def log(self, msg: str) -> None:
        logger.info(msg)
        self.on_log(msg)

    @staticmethod
    def _utc_day() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def on_equity(self, equity: float) -> None:
        if equity <= 0:
            return
        day = self._utc_day()
        if self.state.day_key != day:
            self.state.day_key = day
            self.state.day_start_equity = equity
            self.log(f"新交易日权益基准: {equity:.4f} USDT")

        if self.state.peak_equity <= 0 or (
            self.reset_peak_on_start and self.state.peak_equity == 0
        ):
            self.state.peak_equity = equity
        if equity > self.state.peak_equity:
            self.state.peak_equity = equity

        # 日亏
        if self.state.day_start_equity > 0:
            day_pnl_pct = (equity - self.state.day_start_equity) / self.state.day_start_equity
            if day_pnl_pct <= -abs(self.daily_loss_limit):
                self.halt(f"日亏损熔断 {day_pnl_pct:.2%} <= -{self.daily_loss_limit:.2%}")

        # 回撤
        if self.state.peak_equity > 0:
            dd = (self.state.peak_equity - equity) / self.state.peak_equity
            if dd >= abs(self.max_drawdown):
                self.halt(f"回撤熔断 {dd:.2%} >= {self.max_drawdown:.2%}")

    def halt(self, reason: str) -> None:
        if not self.state.halted:
            self.state.halted = True
            self.state.halt_reason = reason
            self.log(f"风控停机: {reason}")

    def resume(self) -> None:
        self.state.halted = False
        self.state.halt_reason = ""
        self.log("风控已手动恢复（请确认原因已处理）")

    def can_open(self, open_positions: int) -> tuple[bool, str]:
        limit = max(1, min(int(self.max_positions or 1), 10))
        if self.state.halted:
            return False, self.state.halt_reason or "已熔断"
        if open_positions >= limit:
            mode = "单仓" if limit == 1 else "多仓"
            return False, f"{mode}模式：已有 {open_positions} 仓，禁止新开（上限 {limit}）"
        return True, "ok"

    def set_max_positions(self, n: int) -> None:
        self.max_positions = max(1, min(int(n), 10))
        self.log(f"持仓上限已设为 {self.max_positions}")

    def position_size(
        self,
        equity: float,
        entry: float,
        stop: float,
        contract_size: float = 1.0,
    ) -> float:
        """
        按风险比例算合约张数（近似）：
        risk_usdt = equity * risk_per_trade
        qty = risk_usdt / |entry - stop|
        再限制名义不超过 equity * max_notional_pct * leverage 由上层再裁
        """
        if equity <= 0 or entry <= 0 or stop <= 0:
            return 0.0
        dist = abs(entry - stop)
        if dist < 1e-12:
            return 0.0
        risk_usdt = equity * self.risk_per_trade
        qty = risk_usdt / dist
        # 名义保护（不含杠杆放大的风险提示，仅限制保证金相关名义）
        max_notional = equity * self.max_notional_pct
        if entry * qty > max_notional and entry > 0:
            qty = max_notional / entry
        qty = qty / max(contract_size, 1e-12)
        return max(qty, 0.0)
