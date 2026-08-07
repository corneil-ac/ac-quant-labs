from __future__ import annotations

import time


class PositionExitManager:
    """Manage strategy-neutral exits for current-magic BULLET positions."""

    def __init__(
        self,
        logger,
        broker,
        enable_max_hold: bool,
        max_hold_hours: float,
        exit_comment: str,
        now_provider=time.time,
    ) -> None:
        self.logger = logger
        self.broker = broker
        self.enable_max_hold = enable_max_hold
        self.max_hold_hours = max_hold_hours
        self.exit_comment = exit_comment
        self._now_provider = now_provider

    def manage_exits(self) -> None:
        now = float(self._now_provider())
        for position in self.broker.positions():
            holding_seconds = max(0.0, now - float(position.time))
            if not self.enable_max_hold or holding_seconds < self.max_hold_hours * 3600:
                continue

            reason = "Maximum hold exceeded"
            self.logger.info(
                f"AUTO EXIT | Symbol={position.symbol} | "
                f"Holding duration={self._format_duration(holding_seconds)} | "
                f"Profit={position.profit:.2f} | Reason={reason}"
            )
            if not self.broker.dry_run:
                self.broker.close_position(position, comment=self.exit_comment)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total_seconds = int(seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, remaining_seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"
