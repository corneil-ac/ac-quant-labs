from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import MetaTrader5 as mt5


@dataclass(frozen=True)
class CampaignSnapshot:
    symbol: str
    direction: str
    position_count: int
    tickets: tuple[int, ...]
    total_volume: float
    weighted_entry: float
    combined_profit: float
    valid: bool = True
    reason: str = "ok"

    def to_dict(self) -> dict:
        data = asdict(self)
        data["tickets"] = list(self.tickets)
        return data


class CampaignManager:
    """Aggregate BULLET-owned same-symbol positions into one campaign view.

    P1.2B is observational only: it calculates campaign state and records it for
    diagnostics/journaling. It does not yet change stop-loss or exit behavior.
    """

    def __init__(self, logger) -> None:
        self.logger = logger

    def snapshot(self, symbol: str, positions: Iterable) -> CampaignSnapshot | None:
        owned = [p for p in positions if getattr(p, "symbol", None) == symbol]
        if not owned:
            return None

        sides = {getattr(p, "type", None) for p in owned}
        valid_sides = {mt5.POSITION_TYPE_BUY, mt5.POSITION_TYPE_SELL}
        if not sides.issubset(valid_sides) or len(sides) != 1:
            reason = "campaign contains mixed or unknown position directions"
            self.logger.warning("%s: invalid campaign -> %s", symbol, reason)
            return CampaignSnapshot(
                symbol=symbol,
                direction="MIXED",
                position_count=len(owned),
                tickets=tuple(self._ticket(p) for p in owned),
                total_volume=sum(self._nonnegative(getattr(p, "volume", 0.0)) for p in owned),
                weighted_entry=0.0,
                combined_profit=sum(float(getattr(p, "profit", 0.0) or 0.0) for p in owned),
                valid=False,
                reason=reason,
            )

        side = next(iter(sides))
        direction = "BUY" if side == mt5.POSITION_TYPE_BUY else "SELL"

        volumes = [self._positive(getattr(p, "volume", None)) for p in owned]
        entries = [self._positive(getattr(p, "price_open", None)) for p in owned]
        if any(v is None for v in volumes) or any(e is None for e in entries):
            reason = "campaign contains invalid volume or open price"
            self.logger.warning("%s: invalid campaign -> %s", symbol, reason)
            return CampaignSnapshot(
                symbol=symbol,
                direction=direction,
                position_count=len(owned),
                tickets=tuple(self._ticket(p) for p in owned),
                total_volume=sum(v or 0.0 for v in volumes),
                weighted_entry=0.0,
                combined_profit=sum(float(getattr(p, "profit", 0.0) or 0.0) for p in owned),
                valid=False,
                reason=reason,
            )

        total_volume = float(sum(volumes))
        weighted_entry = float(sum(v * e for v, e in zip(volumes, entries)) / total_volume)
        combined_profit = float(sum(float(getattr(p, "profit", 0.0) or 0.0) for p in owned))

        return CampaignSnapshot(
            symbol=symbol,
            direction=direction,
            position_count=len(owned),
            tickets=tuple(self._ticket(p) for p in owned),
            total_volume=total_volume,
            weighted_entry=weighted_entry,
            combined_profit=combined_profit,
        )

    @staticmethod
    def _ticket(position) -> int:
        try:
            return int(getattr(position, "ticket", 0) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _positive(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @staticmethod
    def _nonnegative(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, number)
