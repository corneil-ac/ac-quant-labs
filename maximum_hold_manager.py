from __future__ import annotations

import time


def process_entry_unless_expired(execution, signal, expired_symbols: set[str]) -> bool:
    """Prevent a forced-expiration symbol from being reopened in the same scan."""
    if signal.symbol in expired_symbols:
        return False
    return execution.process(signal)


class MaximumHoldManager:
    """Expire BULLET-owned positions once their configured lifetime is reached."""

    def __init__(self, logger, broker, max_hold_hours: float, enabled: bool = True):
        self.logger = logger
        self.broker = broker
        self.enabled = enabled
        self.max_hold_seconds = max_hold_hours * 60 * 60

    def expire_positions(self, now: float | None = None) -> set[str]:
        """Close expired positions and return symbols barred from entry this scan."""
        if not self.enabled:
            return set()

        current_time = time.time() if now is None else now
        expired = [
            position
            for position in self.broker.positions()
            if position.magic == self.broker.magic
            and current_time - position.time >= self.max_hold_seconds
        ]

        for position in expired:
            symbol = position.symbol
            age_hours = (current_time - position.time) / 3600
            if self.broker.dry_run:
                self.logger.info(
                    f"DRY RUN: maximum hold expired for {symbol} "
                    f"ticket={position.ticket} age={age_hours:.2f}h"
                )
                continue
            result = self.broker.close_position(position, "bullet_max_hold")
            if result.ok:
                self.logger.info(
                    f"{symbol}: maximum hold close submitted | "
                    f"ticket={position.ticket} age={age_hours:.2f}h"
                )
            else:
                # Broker emits the single detailed ERROR for the failed order;
                # keep the scan-level retry signal concise and non-duplicative.
                self.logger.warning(
                    f"{symbol}: maximum hold close failed | "
                    f"ticket={position.ticket} age={age_hours:.2f}h | retry=next_scan"
                )

        return {position.symbol for position in expired}
