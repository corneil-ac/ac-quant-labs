from __future__ import annotations


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

        if len(positions) != 2:
            self.logger.error(
                f"{symbol1}/{symbol2}: ORPHAN / INCOMPLETE PAIR detected | legs={len(positions)} | "
                f"profit={profit:.2f}. Closing immediately."
            )
            self.close_pair(symbol1, symbol2)
            return True

        z_display = f"{z:.2f}" if z is not None else "unavailable"
        self.logger.info(
            f"{symbol1}/{symbol2} OPEN | legs=2 | z={z_display} | profit={profit:.2f}"
        )

        should_close = False
        reason = ""

        exit_z = float(profile["exit_z"])
        if z is not None and abs(z) < exit_z:
            should_close = True
            reason = f"z-score exit | abs({z:.2f}) < {exit_z}"
        elif profit >= self.profit_target:
            should_close = True
            reason = f"profit target | {profit:.2f} >= {self.profit_target}"
        elif profit <= self.stop_loss:
            should_close = True
            reason = f"stop loss | {profit:.2f} <= {self.stop_loss}"

        if should_close:
            self.logger.info(f"{symbol1}/{symbol2}: closing pair -> {reason}")
            self.close_pair(symbol1, symbol2)

        return True

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

        self.logger.info(
            f"{symbol1}/{symbol2}: ENTRY {signal.action} | "
            f"mode={mode} | profile={signal.profile_name} | "
            f"threshold={signal.threshold_used} | z={signal.z:.2f} | "
            f"beta={signal.beta:.4f}"
        )

        if first_action == "BUY":
            first = self.broker.buy(
                symbol1,
                self.lot_size,
                comment=self.entry_comment,
            )
        else:
            first = self.broker.sell(
                symbol1,
                self.lot_size,
                comment=self.entry_comment,
            )

        if not first.ok:
            return

        if second_action == "BUY":
            second = self.broker.buy(
                symbol2,
                self.lot_size,
                comment=self.entry_comment,
            )
        else:
            second = self.broker.sell(
                symbol2,
                self.lot_size,
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
