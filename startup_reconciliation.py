from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import MetaTrader5 as mt5


@dataclass(frozen=True)
class ReconciliationResult:
    ok: bool
    reason: str
    owned_positions: tuple


def reconcile_startup(logger, broker, configured_symbols, max_positions_per_symbol: int = 2) -> ReconciliationResult:
    """Fail closed unless BULLET can prove its owned-position state is coherent."""
    ok, positions, reason = broker.query_owned_positions()
    if not ok:
        message = f"position query failed during startup reconciliation: {reason}"
        logger.critical("P0 RECONCILIATION FAILED | %s", message)
        return ReconciliationResult(False, message, tuple())

    configured = set(configured_symbols)
    counts = Counter()
    problems = []

    for position in positions:
        symbol = getattr(position, "symbol", None)
        ticket = getattr(position, "ticket", None)
        volume = getattr(position, "volume", None)
        position_type = getattr(position, "type", None)

        if symbol not in configured:
            problems.append(f"owned position ticket={ticket} uses unconfigured symbol={symbol}")
            continue
        if not isinstance(ticket, int) or ticket <= 0:
            problems.append(f"owned position has invalid ticket={ticket} symbol={symbol}")
        if volume is None or volume <= 0:
            problems.append(f"owned position ticket={ticket} has invalid volume={volume}")
        if position_type not in (mt5.POSITION_TYPE_BUY, mt5.POSITION_TYPE_SELL):
            problems.append(f"owned position ticket={ticket} has invalid type={position_type}")
        counts[symbol] += 1

    for symbol, count in counts.items():
        if count > max_positions_per_symbol:
            problems.append(
                f"owned positions exceed per-symbol safety cap: {symbol}={count}/{max_positions_per_symbol}"
            )

    if problems:
        message = "; ".join(problems)
        logger.critical("P0 RECONCILIATION FAILED | %s", message)
        return ReconciliationResult(False, message, tuple(positions))

    logger.info(
        "P0 reconciliation passed | owned_positions=%s | by_symbol=%s",
        len(positions), dict(sorted(counts.items())),
    )
    for position in positions:
        logger.info(
            "P0 reconciled position | ticket=%s | symbol=%s | type=%s | volume=%s | price_open=%s | profit=%s",
            getattr(position, "ticket", None), getattr(position, "symbol", None),
            getattr(position, "type", None), getattr(position, "volume", None),
            getattr(position, "price_open", None), getattr(position, "profit", None),
        )
    return ReconciliationResult(True, "ok", tuple(positions))
