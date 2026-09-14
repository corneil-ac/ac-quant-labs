from __future__ import annotations

from dataclasses import replace
from typing import Iterable

import MetaTrader5 as mt5

from strategy_framework import SignalAction, StrategySignal


class ScaleInManager:
    """Authorize one deliberate second entry when an existing trade moves adverse.

    P1 keeps scale-in authorization separate from the strategy itself so an ordinary
    BUY/SELL signal can never become an additional same-symbol position by accident.
    The execution/risk layer still enforces the hard per-symbol position cap.
    """

    def __init__(
        self,
        logger,
        enabled: bool = True,
        max_entries_per_symbol: int = 2,
        min_adverse_atr: float = 1.0,
        min_adx: float = 20.0,
    ) -> None:
        if max_entries_per_symbol < 1:
            raise ValueError("max_entries_per_symbol must be at least 1")
        if min_adverse_atr <= 0:
            raise ValueError("min_adverse_atr must be greater than zero")
        self.logger = logger
        self.enabled = enabled
        self.max_entries_per_symbol = max_entries_per_symbol
        self.min_adverse_atr = float(min_adverse_atr)
        self.min_adx = float(min_adx)

    def authorize(self, signal: StrategySignal, positions: Iterable) -> StrategySignal:
        """Return a copy of *signal* carrying explicit scale-in authorization when safe."""
        if not self.enabled or signal.action is SignalAction.HOLD:
            return signal

        owned = [p for p in positions if getattr(p, "symbol", None) == signal.symbol]
        if not owned:
            return signal

        if len(owned) >= self.max_entries_per_symbol:
            self.logger.info(
                "%s: scale-in denied -> per-symbol entry cap reached: %s/%s",
                signal.symbol, len(owned), self.max_entries_per_symbol,
            )
            return signal

        # P1 v1 deliberately authorizes only the transition from one entry to two.
        if len(owned) != 1:
            return signal

        position = owned[0]
        expected_type = (
            mt5.POSITION_TYPE_BUY if signal.action is SignalAction.BUY
            else mt5.POSITION_TYPE_SELL
        )
        if getattr(position, "type", None) != expected_type:
            self.logger.info(
                "%s: scale-in denied -> strategy direction does not match existing position",
                signal.symbol,
            )
            return signal

        details = dict(signal.entry_details or {})
        atr = self._positive_float(details.get("atr"))
        adx = self._positive_float(details.get("adx"))
        current = self._positive_float(signal.entry_reference)
        entry = self._positive_float(getattr(position, "price_open", None))
        if atr is None or current is None or entry is None:
            self.logger.info(
                "%s: scale-in denied -> ATR/current/open price unavailable",
                signal.symbol,
            )
            return signal

        if adx is None or adx < self.min_adx:
            self.logger.info(
                "%s: scale-in denied -> ADX %.2f below minimum %.2f",
                signal.symbol, adx or 0.0, self.min_adx,
            )
            return signal

        adverse_move = (entry - current) if signal.action is SignalAction.BUY else (current - entry)
        adverse_atr = adverse_move / atr
        if adverse_atr < self.min_adverse_atr:
            self.logger.info(
                "%s: scale-in waiting -> adverse move %.3f ATR < %.3f ATR trigger",
                signal.symbol, adverse_atr, self.min_adverse_atr,
            )
            return signal

        details.update({
            "scale_in_authorized": True,
            "scale_in_existing_ticket": getattr(position, "ticket", None),
            "scale_in_existing_entry": entry,
            "scale_in_current_price": current,
            "scale_in_adverse_atr": adverse_atr,
            "scale_in_trigger_atr": self.min_adverse_atr,
            "scale_in_position_count_before": len(owned),
        })
        reason = (
            f"P1 scale-in authorized: existing {signal.action.value} moved "
            f"{adverse_atr:.3f} ATR adverse while strategy remains {signal.action.value}"
        )
        self.logger.warning("%s: %s", signal.symbol, reason)
        return replace(
            signal,
            reason=reason,
            entry_reason=reason,
            entry_details=details,
        )

    @staticmethod
    def _positive_float(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None
