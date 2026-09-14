from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from campaign_manager import CampaignManager, CampaignSnapshot


@dataclass(frozen=True)
class CampaignExitResult:
    symbol: str
    triggered: bool
    reason: str
    attempted_tickets: tuple[int, ...] = ()
    closed_tickets: tuple[int, ...] = ()
    failed_tickets: tuple[int, ...] = ()

    @property
    def complete(self) -> bool:
        return self.triggered and bool(self.attempted_tickets) and not self.failed_tickets


class CampaignExitManager:
    """Coordinate exits for two-entry BULLET campaigns.

    P1.2C v1 uses combined campaign P&L as the exit trigger. Single-position
    campaigns remain under their existing ticket-level stop/target/max-hold rules.
    A partial close failure is reported explicitly so the runtime can fail closed.
    """

    def __init__(
        self,
        logger,
        broker,
        campaign_manager: CampaignManager,
        enabled: bool = False,
        profit_target: float = 40.0,
        stop_loss: float = -20.0,
        min_positions: int = 2,
        close_comment: str = "bullet_campaign_exit",
    ) -> None:
        if profit_target <= 0:
            raise ValueError("campaign profit_target must be greater than zero")
        if stop_loss >= 0:
            raise ValueError("campaign stop_loss must be negative")
        if min_positions < 2:
            raise ValueError("campaign min_positions must be at least 2")
        self.logger = logger
        self.broker = broker
        self.campaign_manager = campaign_manager
        self.enabled = enabled
        self.profit_target = float(profit_target)
        self.stop_loss = float(stop_loss)
        self.min_positions = int(min_positions)
        self.close_comment = close_comment

    def evaluate_snapshot(self, snapshot: CampaignSnapshot | None) -> tuple[bool, str]:
        if not self.enabled:
            return False, "campaign exits disabled"
        if snapshot is None:
            return False, "no campaign"
        if not snapshot.valid:
            return False, f"invalid campaign: {snapshot.reason}"
        if snapshot.position_count < self.min_positions:
            return False, "campaign has fewer than two positions"
        if snapshot.combined_profit >= self.profit_target:
            return True, (
                f"combined profit target reached: {snapshot.combined_profit:.2f} "
                f">= {self.profit_target:.2f}"
            )
        if snapshot.combined_profit <= self.stop_loss:
            return True, (
                f"combined campaign stop reached: {snapshot.combined_profit:.2f} "
                f"<= {self.stop_loss:.2f}"
            )
        return False, "campaign P&L remains inside exit band"

    def process_symbol(self, symbol: str, positions: Iterable) -> CampaignExitResult:
        owned = [p for p in positions if getattr(p, "symbol", None) == symbol]
        snapshot = self.campaign_manager.snapshot(symbol, owned)
        trigger, reason = self.evaluate_snapshot(snapshot)
        if not trigger:
            return CampaignExitResult(symbol=symbol, triggered=False, reason=reason)

        # Snapshot tickets define the exact campaign we decided to close. Re-querying
        # and reconciliation happen in the runtime after submissions.
        by_ticket = {int(getattr(p, "ticket", 0) or 0): p for p in owned}
        tickets = tuple(snapshot.tickets) if snapshot else ()
        closed: list[int] = []
        failed: list[int] = []

        self.logger.warning(
            "%s: CAMPAIGN EXIT TRIGGERED | positions=%s | volume=%.2f | weighted_entry=%s | combined_profit=%.2f | reason=%s",
            symbol,
            snapshot.position_count,
            snapshot.total_volume,
            snapshot.weighted_entry,
            snapshot.combined_profit,
            reason,
        )

        for ticket in tickets:
            position = by_ticket.get(ticket)
            if position is None:
                failed.append(ticket)
                self.logger.error("%s: campaign exit ticket disappeared before close | ticket=%s", symbol, ticket)
                continue
            result = self.broker.close_position(position, self.close_comment)
            if result.ok:
                closed.append(ticket)
                self.logger.info("%s: campaign close submitted | ticket=%s", symbol, ticket)
            else:
                failed.append(ticket)
                self.logger.warning("%s: campaign close failed | ticket=%s", symbol, ticket)

        return CampaignExitResult(
            symbol=symbol,
            triggered=True,
            reason=reason,
            attempted_tickets=tickets,
            closed_tickets=tuple(closed),
            failed_tickets=tuple(failed),
        )
