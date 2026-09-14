from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path

from strategy_framework import SignalAction, StrategySignal


class ExecutionManager:
    """Strategy-neutral validation and single-symbol order execution."""

    def __init__(self, logger, broker, risk_manager, calendar_filter, volume: float,
                 entry_comment: str, allow_volume_normalization: bool = False,
                 journal_path: str = "data/trade_journal.csv", campaign_manager=None) -> None:
        self.logger = logger
        self.broker = broker
        self.risk = risk_manager
        self.calendar_filter = calendar_filter
        self.volume = volume
        self.entry_comment = entry_comment
        self.allow_volume_normalization = allow_volume_normalization
        self.journal_path = Path(journal_path)
        self.campaign_manager = campaign_manager
        self._handled_candles: set[tuple[str, object]] = set()
        self._configuration_failures: set[str] = set()
        self.safe_mode = False
        self.safe_mode_reason = ""

    def set_safe_mode(self, enabled: bool, reason: str = "") -> None:
        self.safe_mode = enabled
        self.safe_mode_reason = reason if enabled else ""
        if enabled:
            self.logger.critical("BULLET SAFE MODE ENABLED | new entries blocked | reason=%s", reason)
        else:
            self.logger.info("BULLET SAFE MODE CLEARED | new entries enabled")

    def process(self, signal: StrategySignal) -> bool:
        if signal.action is SignalAction.HOLD or signal.symbol in self._configuration_failures:
            return False

        if self.safe_mode:
            self.logger.warning(
                "%s: entry blocked by SAFE MODE | reason=%s",
                signal.symbol, self.safe_mode_reason,
            )
            return False

        key = (signal.symbol, signal.signal_candle_timestamp)
        if key in self._handled_candles:
            self.logger.info(f"{signal.symbol}: duplicate signal candle suppressed")
            return False
        self._handled_candles.add(key)

        allow_scale_in = bool((signal.entry_details or {}).get("scale_in_authorized", False))

        can_open, reason = self.risk.can_open_symbol(
            signal.symbol,
            allow_additional_position=allow_scale_in,
        )
        if not can_open:
            if reason.startswith("position state unavailable:"):
                self.set_safe_mode(True, reason)
            self.logger.info(f"{signal.symbol}: entry skipped -> {reason}")
            return False

        calendar_ok, reason = self.calendar_filter.can_open_symbol(signal.symbol)
        if not calendar_ok:
            self.logger.info(f"{signal.symbol}: entry blocked -> {reason}")
            return False

        validation = self.broker.validate_volume(
            signal.symbol, self.volume, self.allow_volume_normalization
        )
        self.logger.info(
            f"{signal.symbol}: volume preflight | requested={validation.requested} | "
            f"normalized={validation.normalized} | min={validation.volume_min} | "
            f"max={validation.volume_max} | step={validation.volume_step} | valid={validation.ok}"
        )
        if not validation.ok:
            if validation.deterministic:
                self._configuration_failures.add(signal.symbol)
            self.logger.error(f"{signal.symbol}: entry rejected -> {validation.reason}")
            return False

        # Final fail-closed duplicate gate immediately before order submission.
        can_open, reason = self.risk.can_open_symbol(
            signal.symbol,
            allow_additional_position=allow_scale_in,
        )
        if not can_open:
            if reason.startswith("position state unavailable:"):
                self.set_safe_mode(True, reason)
            self.logger.warning(f"{signal.symbol}: final entry gate blocked -> {reason}")
            return False

        self.logger.info(
            "%s: ENTRY %s | strategy=%s | source=%s | scale_in_authorized=%s | reason=%s | details=%s",
            signal.symbol, signal.action.value, signal.strategy_name,
            signal.entry_source or "UNSPECIFIED", allow_scale_in,
            signal.entry_reason or signal.reason, signal.entry_details or {},
        )

        order = (self.broker.buy if signal.action is SignalAction.BUY else self.broker.sell)(
            signal.symbol, validation.normalized, comment=self.entry_comment,
            stop_loss=signal.stop_loss, take_profit=signal.take_profit,
        )
        if not order.ok:
            return False

        self.risk.mark_trade_time(signal.symbol)
        journal_signal = self._attach_campaign_snapshot(signal)
        self._journal(journal_signal, validation.normalized, order)
        return True

    def _attach_campaign_snapshot(self, signal: StrategySignal) -> StrategySignal:
        if self.campaign_manager is None:
            return signal

        ok, positions, reason = self.broker.query_owned_positions()
        if not ok:
            self.set_safe_mode(True, f"post-entry campaign state unavailable: {reason}")
            return signal

        snapshot = self.campaign_manager.snapshot(signal.symbol, positions)
        if snapshot is None:
            self.logger.warning(
                "%s: post-entry campaign snapshot unavailable -> no owned position found",
                signal.symbol,
            )
            return signal

        details = dict(signal.entry_details or {})
        details["campaign_after_entry"] = snapshot.to_dict()
        self.logger.info(
            "%s: CAMPAIGN | direction=%s | positions=%s | volume=%.4f | weighted_entry=%.8f | pnl=%.2f | valid=%s",
            signal.symbol,
            snapshot.direction,
            snapshot.position_count,
            snapshot.total_volume,
            snapshot.weighted_entry,
            snapshot.combined_profit,
            snapshot.valid,
        )
        if not snapshot.valid:
            self.set_safe_mode(True, f"invalid post-entry campaign state: {snapshot.reason}")

        return replace(signal, entry_details=details)

    def _journal(self, signal, volume, order) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.journal_path.exists()
        if exists:
            with self.journal_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            if rows and rows[0] == ["signal_time", "symbol", "action", "volume", "entry",
                                    "stop_loss", "take_profit", "strategy", "ticket"]:
                upgraded = [rows[0][:-1] + ["entry_source", "entry_reason", "entry_details", "ticket"]]
                upgraded.extend(row[:-1] + ["", "", "", row[-1]] for row in rows[1:] if row)
                with self.journal_path.open("w", newline="", encoding="utf-8") as handle:
                    csv.writer(handle).writerows(upgraded)
        with self.journal_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if not exists:
                writer.writerow(["signal_time", "symbol", "action", "volume", "entry", "stop_loss", "take_profit", "strategy", "entry_source", "entry_reason", "entry_details", "ticket"])
            writer.writerow([signal.signal_candle_timestamp, signal.symbol, signal.action.value,
                             volume, signal.entry_reference, signal.stop_loss,
                             signal.take_profit, signal.strategy_name,
                             signal.entry_source, signal.entry_reason,
                             json.dumps(signal.entry_details or {}, default=str, sort_keys=True),
                             order.ticket])
