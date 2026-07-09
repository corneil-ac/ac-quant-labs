from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Iterable
import MetaTrader5 as mt5


@dataclass
class OrderResult:
    ok: bool
    symbol: str
    action: str
    ticket: Optional[int]
    retcode: Optional[int]
    comment: str
    price: Optional[float]


class Broker:
    def __init__(self, logger, magic: int, deviation: int, dry_run: bool = False):
        self.logger = logger
        self.magic = magic
        self.deviation = deviation
        self.dry_run = dry_run

    def initialize(self) -> bool:
        if not mt5.initialize():
            self.logger.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False

        account = mt5.account_info()
        terminal = mt5.terminal_info()

        if account is None:
            self.logger.error(f"MT5 connected, but account_info() is None: {mt5.last_error()}")
            return False

        self.logger.info("Connected to MT5")
        self.logger.info(f"Account: {account.login} | Balance: {account.balance:.2f} | Equity: {account.equity:.2f}")

        if terminal:
            self.logger.info(f"Terminal trade allowed: {terminal.trade_allowed}")

        return True

    def shutdown(self) -> None:
        mt5.shutdown()
        self.logger.info("MT5 shutdown complete")

    def ensure_symbols(self, symbols: Iterable[str]) -> None:
        for symbol in sorted(set(symbols)):
            ok = mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)

            if not ok or info is None:
                self.logger.error(f"{symbol}: could not select symbol. Check broker suffix like EURUSDm/EURUSD.a")
            else:
                self.logger.info(
                    f"{symbol}: selected | visible={info.visible} | filling_mode={info.filling_mode} | trade_mode={info.trade_mode}"
                )

    def account_info(self):
        return mt5.account_info()

    def positions(self):
        positions = mt5.positions_get()
        if positions is None:
            return []
        return [p for p in positions if p.magic == self.magic]

    def positions_for_symbols(self, symbols: set[str]):
        return [p for p in self.positions() if p.symbol in symbols]

    def open_symbols(self) -> set[str]:
        return set(p.symbol for p in self.positions())

    def count_total_pairs(self) -> int:
        return len(self.positions()) // 2

    def pair_positions(self, symbol1: str, symbol2: str):
        return self.positions_for_symbols({symbol1, symbol2})

    def pair_profit(self, symbol1: str, symbol2: str) -> float:
        return sum(p.profit for p in self.pair_positions(symbol1, symbol2))

    def filling_candidates(self, symbol: str):
        """
        MT5 brokers are inconsistent here. Some reject symbol_info().filling_mode directly.
        So we try a safe fallback list until the broker accepts one.
        """
        info = mt5.symbol_info(symbol)

        candidates = []
        if info is not None:
            candidates.append(info.filling_mode)

        candidates.extend([
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_FOK,
            mt5.ORDER_FILLING_RETURN,
        ])

        unique = []
        for c in candidates:
            if c not in unique:
                unique.append(c)
        return unique

    def _send_market_order(self, symbol: str, action: str, volume: float, position_ticket: Optional[int] = None, comment: str = "") -> OrderResult:
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)

        if tick is None or info is None:
            msg = f"{symbol}: tick or symbol info unavailable"
            self.logger.error(msg)
            return OrderResult(False, symbol, action, None, None, msg, None)

        order_type = mt5.ORDER_TYPE_BUY if action.upper() == "BUY" else mt5.ORDER_TYPE_SELL
        price = tick.ask if action.upper() == "BUY" else tick.bid

        base_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
        }

        if position_ticket is not None:
            base_request["position"] = position_ticket

        if self.dry_run:
            self.logger.info(f"DRY RUN: {action} {symbol} volume={volume} price={price}")
            return OrderResult(True, symbol, action, 0, 0, "DRY_RUN", price)

        last_result = None

        for filling in self.filling_candidates(symbol):
            request = dict(base_request)
            request["type_filling"] = filling

            result = mt5.order_send(request)
            last_result = result

            if result is None:
                self.logger.error(f"{action} {symbol} fill={filling} -> order_send returned None | last_error={mt5.last_error()}")
                continue

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                ticket = getattr(result, "order", None)
                self.logger.info(f"{action} {symbol} -> DONE | ticket={ticket} | price={price} | filling={filling} | comment={result.comment}")
                return OrderResult(True, symbol, action, ticket, result.retcode, result.comment, price)

            self.logger.error(f"{action} {symbol} fill={filling} -> FAILED | retcode={result.retcode} | comment={result.comment}")

        # Final fallback: send without type_filling and let terminal/broker choose, if allowed.
        result = mt5.order_send(base_request)
        last_result = result

        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            ticket = getattr(result, "order", None)
            self.logger.info(f"{action} {symbol} -> DONE | ticket={ticket} | price={price} | filling=OMITTED | comment={result.comment}")
            return OrderResult(True, symbol, action, ticket, result.retcode, result.comment, price)

        if result is None:
            msg = f"all filling modes failed; omitted filling also returned None | last_error={mt5.last_error()}"
            self.logger.error(f"{action} {symbol} -> FAILED | {msg}")
            return OrderResult(False, symbol, action, None, None, msg, price)

        msg = f"all filling modes failed | last retcode={result.retcode} | comment={result.comment}"
        self.logger.error(f"{action} {symbol} -> FAILED | {msg}")
        return OrderResult(False, symbol, action, None, result.retcode, result.comment, price)

    def buy(self, symbol: str, volume: float, comment: str) -> OrderResult:
        return self._send_market_order(symbol, "BUY", volume, comment=comment)

    def sell(self, symbol: str, volume: float, comment: str) -> OrderResult:
        return self._send_market_order(symbol, "SELL", volume, comment=comment)

    def close_position(self, position, comment: str) -> OrderResult:
        action = "SELL" if position.type == mt5.POSITION_TYPE_BUY else "BUY"
        return self._send_market_order(
            symbol=position.symbol,
            action=action,
            volume=position.volume,
            position_ticket=position.ticket,
            comment=comment,
        )
