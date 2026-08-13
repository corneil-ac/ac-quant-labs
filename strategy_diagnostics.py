from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from strategy_framework import SignalAction, StrategySignal
from trend_momentum_strategy import has_ema_pullback


@dataclass(frozen=True)
class StrategyDiagnostics:
    symbol: str
    h1_direction: str
    h1_trend: str
    m15_direction: str
    m15_momentum: str
    ema20_pullback: str
    confirmation_candle: str
    atr: float | None
    stop_loss: float | None
    take_profit: float | None
    final_decision: str
    reason: str
    entry_source: str | None = None
    module_results: Mapping[str, Mapping[str, object]] | None = None

    @staticmethod
    def _number(value: float | None) -> str:
        return "N/A" if value is None or pd.isna(value) else f"{value:.10g}"

    def format(self) -> str:
        lines = [
                f"{self.symbol} Strategy Decision Diagnostics",
                f"H1 Trend Direction      : {self.h1_direction}",
                f"H1 Trend                : {self.h1_trend}",
                f"M15 Momentum Direction  : {self.m15_direction}",
                f"M15 Momentum            : {self.m15_momentum}",
                f"EMA20 Pullback          : {self.ema20_pullback}",
                f"Confirmation Candle     : {self.confirmation_candle}",
                f"ATR(14)                 : {self._number(self.atr)}",
                f"Calculated Stop Loss    : {self._number(self.stop_loss)}",
                f"Calculated Take Profit  : {self._number(self.take_profit)}",
                f"Final Decision          : {self.final_decision}",
                "Reason:",
                self.reason,
        ]
        lines.insert(-2, f"Entry Source            : {self.entry_source or 'NONE'}")
        for name, result in (self.module_results or {}).items():
            lines.insert(-2, f"Entry Module {name:<25}: {result.get('status')} | {result.get('reason')}")
        return "\n".join(lines)


def diagnose_trend_momentum(
    signal: StrategySignal,
    candles: Mapping[str, pd.DataFrame],
    trend_ema_period: int = 200,
    fast_ema_period: int = 20,
    slow_ema_period: int = 50,
    atr_period: int = 14,
    pullback_lookback: int = 3,
) -> StrategyDiagnostics:
    """Describe the already-made strategy decision without affecting it."""
    h1 = candles.get("H1", pd.DataFrame()).copy()
    m15 = candles.get("M15", pd.DataFrame()).copy()
    required = {"time", "open", "high", "low", "close"}
    if (
        not required.issubset(h1.columns)
        or not required.issubset(m15.columns)
        or len(h1) < trend_ema_period
        or len(m15) < max(slow_ema_period, atr_period + 1)
    ):
        return StrategyDiagnostics(
            signal.symbol, "NEUTRAL", "FAIL", "NEUTRAL", "FAIL", "FAIL",
            "FAIL", None, signal.stop_loss, signal.take_profit,
            signal.action.value, "Insufficient closed candle data.", signal.entry_source,
            (signal.entry_details or {}).get("module_results", {}),
        )

    h1_ema = h1["close"].ewm(span=trend_ema_period, adjust=False).mean().iloc[-1]
    fast = m15["close"].ewm(span=fast_ema_period, adjust=False).mean()
    slow = m15["close"].ewm(span=slow_ema_period, adjust=False).mean()
    previous_close = m15["close"].shift(1)
    true_range = pd.concat(
        (
            m15["high"] - m15["low"],
            (m15["high"] - previous_close).abs(),
            (m15["low"] - previous_close).abs(),
        ),
        axis=1,
    ).max(axis=1)
    atr = float(true_range.ewm(alpha=1 / atr_period, adjust=False).mean().iloc[-1])
    trend_close = float(h1["close"].iloc[-1])
    candle = m15.iloc[-1]
    close, open_ = float(candle["close"]), float(candle["open"])
    fast_value, slow_value = float(fast.iloc[-1]), float(slow.iloc[-1])

    h1_direction = "BUY" if trend_close > h1_ema else "SELL" if trend_close < h1_ema else "NEUTRAL"
    buy_momentum = fast_value > slow_value and close > fast_value and close > slow_value
    sell_momentum = fast_value < slow_value and close < fast_value and close < slow_value
    m15_direction = "BUY" if buy_momentum else "SELL" if sell_momentum else "NEUTRAL"
    aligned = h1_direction != "NEUTRAL" and m15_direction == h1_direction
    pullback_direction = (
        SignalAction.BUY if h1_direction == "BUY" else SignalAction.SELL
    )
    pullback = aligned and has_ema_pullback(
        m15, fast, pullback_direction, pullback_lookback
    )
    confirmation = aligned and (
        (h1_direction == "BUY" and close > open_)
        or (h1_direction == "SELL" and close < open_)
    )

    if signal.action is not SignalAction.HOLD:
        reason = signal.reason.rstrip(".") + "."
    elif pd.isna(atr) or atr <= 0:
        reason = "ATR(14) is unavailable."
    elif h1_direction == "NEUTRAL":
        reason = "Waiting for H1 trend direction."
    elif not aligned:
        reason = f"Waiting for M15 momentum aligned with H1 {h1_direction} trend."
    else:
        reason = signal.reason.rstrip(".") + "."

    return StrategyDiagnostics(
        signal.symbol,
        h1_direction,
        "PASS" if h1_direction != "NEUTRAL" else "FAIL",
        m15_direction,
        "PASS" if aligned else "FAIL",
        "PASS" if pullback else "FAIL",
        "PASS" if confirmation else "FAIL",
        None if pd.isna(atr) else atr,
        signal.stop_loss,
        signal.take_profit,
        signal.action.value,
        reason,
        signal.entry_source,
        (signal.entry_details or {}).get("module_results", {}),
    )
