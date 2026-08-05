from __future__ import annotations

import time


class TradeManager:
    def __init__(
        self,
        logger,
        broker,
        risk_manager,
        lot_size: float,
        profit_target: float,
        stop_loss: float,
        entry_comment: str,
        exit_comment: str,
        execution_modes: dict,
        close_first_leg_if_second_fails: bool = True,
        allow_volume_normalization: bool = False,
        enable_time_exit: bool = False,
        time_exit_hours: float = 0.0,
        time_exit_min_profit: float = 0.0,
        enable_max_hold: bool = False,
        max_hold_hours: float = 0.0,
        min_hold_minutes: float = 0.0,
        now_provider=time.time,
    ):
        self.logger = logger
        self.broker = broker
        self.risk = risk_manager
        self.lot_size = lot_size
        self.profit_target = profit_target
        self.stop_loss = stop_loss
        self.entry_comment = entry_comment
        self.exit_comment = exit_comment
        self.execution_modes = execution_modes
        self.close_first_leg_if_second_fails = close_first_leg_if_second_fails
        self.allow_volume_normalization = allow_volume_normalization
        self.enable_time_exit = enable_time_exit
        self.time_exit_hours = time_exit_hours
        self.time_exit_min_profit = time_exit_min_profit
        self.enable_max_hold = enable_max_hold
        self.max_hold_hours = max_hold_hours
        self.min_hold_minutes = min_hold_minutes
        self._now_provider = now_provider
        self._configuration_failures: set[tuple[str, str]] = set()

    def manage_existing_pair(
        self, symbol1: str, symbol2: str, z: float | None, profile: dict
    ) -> bool:
        """
        Returns True if the pair had open positions and was managed.

        Safety rule:
        A pair must have exactly 2 legs. If it has only 1 leg, that is an orphan/naked position.
        Close it immediately. No waiting for Z-score, target, or stop loss.
        """
        positions = self.broker.pair_positions(symbol1, symbol2)
        if not positions:
            return False

        profit = sum(p.profit for p in positions)
        holding_seconds = self._holding_seconds(positions)

        if len(positions) != 2:
            reason = f"orphan/incomplete pair | legs={len(positions)}"
            self._log_exit(symbol1, symbol2, holding_seconds, profit, z, reason, level="error")
            self.close_pair(symbol1, symbol2)
            return True

        z_display = self._format_z(z)
        self.logger.info(
            f"{symbol1}/{symbol2} OPEN | legs=2 | z={z_display} | "
            f"profit={profit:.2f} | holding={self._format_holding_duration(holding_seconds)}"
        )

        reason = self._exit_reason(profit, z, profile, holding_seconds)

        if reason:
            self._log_exit(symbol1, symbol2, holding_seconds, profit, z, reason)
            self.close_pair(symbol1, symbol2)

        return True

    def _exit_reason(
        self, profit: float, z: float | None, profile: dict, holding_seconds: float
    ) -> str:
        if profit <= self.stop_loss:
            return f"stop loss | {profit:.2f} <= {self.stop_loss}"

        if profit >= self.profit_target:
            return f"profit target | {profit:.2f} >= {self.profit_target}"

        exit_z = float(profile["exit_z"])
        if z is not None and abs(z) < exit_z:
            return f"mean reversion | abs({z:.2f}) < {exit_z}"

        holding_hours = holding_seconds / 3600
        holding_minutes = holding_seconds / 60

        if (
            self.enable_time_exit
            and holding_minutes >= self.min_hold_minutes
            and holding_hours >= self.time_exit_hours
            and profit >= self.time_exit_min_profit
        ):
            return (
                f"time exit | holding={self._format_holding_duration(holding_seconds)} >= "
                f"{self.time_exit_hours}h and profit={profit:.2f} >= {self.time_exit_min_profit}"
            )

        if self.enable_max_hold and holding_hours >= self.max_hold_hours:
            return (
                f"maximum hold | holding={self._format_holding_duration(holding_seconds)} >= "
                f"{self.max_hold_hours}h"
            )

        return ""

    def _holding_seconds(self, positions) -> float:
        oldest_open_time = min(float(p.time) for p in positions)
        return max(0.0, float(self._now_provider()) - oldest_open_time)

    @staticmethod
    def _format_holding_duration(seconds: float) -> str:
        total_seconds = int(seconds)
        hours, remainder = divmod(total_seconds, 3600)
        minutes, remaining_seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"

    @staticmethod
    def _format_z(z: float | None) -> str:
        return f"{z:.2f}" if z is not None else "unavailable"

    def _log_exit(
        self,
        symbol1: str,
        symbol2: str,
        holding_seconds: float,
        profit: float,
        z: float | None,
        reason: str,
        level: str = "info",
    ) -> None:
        log = getattr(self.logger, level)
        log(
            f"{symbol1}/{symbol2}: closing pair | pair={symbol1}/{symbol2} | "
            f"holding={self._format_holding_duration(holding_seconds)} | "
            f"profit={profit:.2f} | z={self._format_z(z)} | reason={reason}"
        )

    def close_pair(self, symbol1: str, symbol2: str) -> None:
        positions = self.broker.pair_positions(symbol1, symbol2)

        if not positions:
            self.logger.info(f"{symbol1}/{symbol2}: no positions to close")
            return

        for p in positions:
            self.broker.close_position(p, comment=self.exit_comment)

    def open_pair(self, signal) -> None:
        symbol1 = signal.symbol1
        symbol2 = signal.symbol2

        pair = (symbol1, symbol2)
        if pair in self._configuration_failures:
            return

        can_open, reason = self.risk.can_open_pair(symbol1, symbol2)
        if not can_open:
            self.logger.info(f"{symbol1}/{symbol2}: skipped -> {reason}")
            return

        mode = self.execution_modes.get((symbol1, symbol2), "HEDGED")

        if signal.action == "LONG":
            first_action = "BUY"
            second_action = "BUY" if mode == "SAME_DIRECTION" else "SELL"

        elif signal.action == "SHORT":
            first_action = "SELL"
            second_action = "SELL" if mode == "SAME_DIRECTION" else "BUY"

        else:
            return

        # Preflight both legs before either order is submitted. Volume contract
        # failures are deterministic configuration errors, so quarantine the pair
        # rather than retrying it on every scan.
        first_volume = self.broker.validate_volume(
            symbol1, self.lot_size, self.allow_volume_normalization
        )
        second_volume = self.broker.validate_volume(
            symbol2, self.lot_size, self.allow_volume_normalization
        )
        for validation in (first_volume, second_volume):
            self.logger.info(
                f"{validation.symbol}: volume preflight | "
                f"requested={validation.requested} | normalized={validation.normalized} | "
                f"min={validation.volume_min} | max={validation.volume_max} | "
                f"step={validation.volume_step} | valid={validation.ok}"
            )

        if not first_volume.ok or not second_volume.ok:
            failures = "; ".join(
                f"{v.symbol}: {v.reason}" for v in (first_volume, second_volume) if not v.ok
            )
            deterministic = any(
                not validation.ok and validation.deterministic
                for validation in (first_volume, second_volume)
            )
            if deterministic:
                self._configuration_failures.add(pair)
            self.logger.error(
                f"{symbol1}/{symbol2}: pair entry rejected before order submission; "
                f"future retries {'disabled' if deterministic else 'allowed'} -> {failures}"
            )
            return

        self.logger.info(
            f"{symbol1}/{symbol2}: ENTRY {signal.action} | "
            f"mode={mode} | profile={signal.profile_name} | "
            f"threshold={signal.threshold_used} | z={signal.z:.2f} | "
            f"beta={signal.beta:.4f}"
        )

        if first_action == "BUY":
            first = self.broker.buy(
                symbol1,
                first_volume.normalized,
                comment=self.entry_comment,
            )
        else:
            first = self.broker.sell(
                symbol1,
                first_volume.normalized,
                comment=self.entry_comment,
            )

        if not first.ok:
            return

        if second_action == "BUY":
            second = self.broker.buy(
                symbol2,
                second_volume.normalized,
                comment=self.entry_comment,
            )
        else:
            second = self.broker.sell(
                symbol2,
                second_volume.normalized,
                comment=self.entry_comment,
            )

        if not second.ok and self.close_first_leg_if_second_fails:
            self.logger.error(
                f"{symbol1}/{symbol2}: second leg failed; "
                "closing first leg immediately"
            )
            self._close_newest_position_for_symbol(symbol1)
            return

        if first.ok and second.ok:
            self.risk.mark_trade_time(symbol1, symbol2)

    def _close_newest_position_for_symbol(self, symbol: str) -> None:
        positions = [p for p in self.broker.positions() if p.symbol == symbol]
        if not positions:
            return

        newest = sorted(positions, key=lambda p: p.time, reverse=True)[0]
        self.broker.close_position(newest, comment=self.exit_comment)
