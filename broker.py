from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math
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
    failure_reason: Optional[str] = None


@dataclass(frozen=True)
class VolumeValidation:
    ok: bool
    symbol: str
    requested: float
    normalized: Optional[float]
    volume_min: Optional[float]
    volume_max: Optional[float]
    volume_step: Optional[float]
    reason: str = ""
    deterministic: bool = True


class Broker:
    def __init__(self, logger, magic: int, deviation: int, dry_run: bool = False):
        self.logger = logger
        self.magic = magic
        self.deviation = deviation
        self.dry_run = dry_run
        # A successful fill is better evidence than sometimes-inaccurate symbol
        # metadata.  This cache deliberately lasts only for this Broker runtime.
        self._successful_filling_modes: dict[str, int] = {}

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

    def validate_volume(
        self, symbol: str, requested: float, allow_normalization: bool = False
    ) -> VolumeValidation:
        """Validate a requested volume against the symbol's live MT5 contract."""
        selected = mt5.symbol_select(symbol, True)
        info = mt5.symbol_info(symbol)
        if not selected or info is None:
            return VolumeValidation(
                False, symbol, requested, None, None, None, None,
                "symbol is unavailable or could not be selected",
                False,
            )

        volume_min = getattr(info, "volume_min", None)
        volume_max = getattr(info, "volume_max", None)
        volume_step = getattr(info, "volume_step", None)
        try:
            requested_decimal = Decimal(str(requested))
            minimum = Decimal(str(volume_min))
            maximum = Decimal(str(volume_max))
            step = Decimal(str(volume_step))
        except (InvalidOperation, TypeError, ValueError):
            return VolumeValidation(
                False, symbol, requested, None, volume_min, volume_max, volume_step,
                "invalid MT5 volume contract",
            )

        if (
            not math.isfinite(float(requested_decimal))
            or requested_decimal <= 0
            or minimum <= 0
            or maximum < minimum
            or step <= 0
        ):
            return VolumeValidation(
                False, symbol, requested, None, volume_min, volume_max, volume_step,
                "invalid requested volume or MT5 volume contract",
            )

        clamped = min(max(requested_decimal, minimum), maximum)
        steps = ((clamped - minimum) / step).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        normalized_decimal = min(max(minimum + steps * step, minimum), maximum)
        normalized = float(normalized_decimal)
        valid_as_requested = requested_decimal == normalized_decimal

        if not valid_as_requested and not allow_normalization:
            return VolumeValidation(
                False, symbol, requested, normalized, float(minimum), float(maximum),
                float(step), "requested volume is outside the MT5 volume contract",
            )

        return VolumeValidation(
            True, symbol, requested, normalized, float(minimum), float(maximum),
            float(step), "normalized" if not valid_as_requested else "",
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

    @staticmethod
    def classify_rejection(retcode: Optional[int], comment: str = "") -> str:
        """Return a stable, operational classification for an MT5 rejection."""
        groups = (
            ("UNSUPPORTED_FILLING_MODE", ("TRADE_RETCODE_INVALID_FILL",), (10030,)),
            ("NO_PRICES", ("TRADE_RETCODE_PRICE_OFF",), (10021,)),
            ("MARKET_CLOSED", (
                "TRADE_RETCODE_MARKET_CLOSED", "TRADE_RETCODE_TRADE_DISABLED",
                "TRADE_RETCODE_SERVER_DISABLES_AT", "TRADE_RETCODE_CLIENT_DISABLES_AT",
            ), (10018, 10017, 10026, 10027)),
            ("INVALID_STOPS", ("TRADE_RETCODE_INVALID_STOPS",), (10016,)),
            ("INVALID_VOLUME", ("TRADE_RETCODE_INVALID_VOLUME",), (10014,)),
            ("INSUFFICIENT_MARGIN", ("TRADE_RETCODE_NO_MONEY",), (10019,)),
        )
        for classification, names, standard_values in groups:
            values = {getattr(mt5, name, None) for name in names}
            if retcode in values - {None} or retcode in standard_values:
                return classification

        # Some gateways provide useful text with a missing/nonstandard retcode.
        normalized = (comment or "").lower()
        if "unsupported filling" in normalized:
            return "UNSUPPORTED_FILLING_MODE"
        if "no prices" in normalized or "no price" in normalized:
            return "NO_PRICES"
        if "market closed" in normalized or "trade disabled" in normalized:
            return "MARKET_CLOSED"
        return "OTHER_MT5_REJECTION"

    def filling_candidates(self, symbol: str, info=None):
        """Build a deterministic, capability-aware list of (mode, source)."""
        info = info if info is not None else mt5.symbol_info(symbol)
        modes = {
            "FOK": getattr(mt5, "ORDER_FILLING_FOK", 0),
            "IOC": getattr(mt5, "ORDER_FILLING_IOC", 1),
            "RETURN": getattr(mt5, "ORDER_FILLING_RETURN", 2),
        }
        candidates = []
        cached = self._successful_filling_modes.get(symbol)
        if cached is not None:
            candidates.append((cached, "cache"))

        filling_flags = getattr(info, "filling_mode", None)
        fok_flag = getattr(mt5, "SYMBOL_FILLING_FOK", 1)
        ioc_flag = getattr(mt5, "SYMBOL_FILLING_IOC", 2)
        if filling_flags is not None:
            # Modern MT5 exposes a flag mask.  A zero value is also accepted for
            # compatibility with APIs/brokers exposing ORDER_FILLING_FOK itself.
            if filling_flags == modes["FOK"] or filling_flags & fok_flag:
                candidates.append((modes["FOK"], "capability"))
            if filling_flags & ioc_flag:
                candidates.append((modes["IOC"], "capability"))

        execution = getattr(info, "trade_exemode", getattr(info, "trade_execution", None))
        market_execution = getattr(mt5, "SYMBOL_TRADE_EXECUTION_MARKET", 2)
        if execution != market_execution:
            candidates.append((modes["RETURN"], "capability"))

        # Metadata is advisory.  Deterministic fallback probes the other modes,
        # except RETURN where MT5 explicitly prohibits it for Market Execution.
        for mode in (modes["IOC"], modes["FOK"]):
            candidates.append((mode, "fallback"))
        if execution != market_execution:
            candidates.append((modes["RETURN"], "fallback"))

        unique = []
        seen = set()
        for mode, source in candidates:
            if mode not in seen:
                seen.add(mode)
                unique.append((mode, source))
        return unique

    @staticmethod
    def _filling_name(mode: int) -> str:
        for name in ("FOK", "IOC", "RETURN"):
            if mode == getattr(mt5, f"ORDER_FILLING_{name}", object()):
                return name
        return str(mode)

    def _send_market_order(self, symbol: str, action: str, volume: float, position_ticket: Optional[int] = None, comment: str = "", stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> OrderResult:
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)

        if tick is None or info is None:
            msg = f"{symbol}: tick or symbol info unavailable"
            self.logger.error(msg)
            return OrderResult(False, symbol, action, None, None, msg, None, "NO_PRICES")

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
        if stop_loss is not None:
            base_request["sl"] = stop_loss
        if take_profit is not None:
            base_request["tp"] = take_profit

        if self.dry_run:
            self.logger.info(f"DRY RUN: {action} {symbol} volume={volume} price={price}")
            return OrderResult(True, symbol, action, 0, 0, "DRY_RUN", price)

        operation = "close" if position_ticket is not None else "entry"
        context = (
            f"{symbol} {action.upper()} | operation={operation} | ticket={position_ticket} | "
            f"volume={volume} | price={price} | bid={getattr(tick, 'bid', None)} | "
            f"ask={getattr(tick, 'ask', None)}"
        )
        last_result = None
        candidates = self.filling_candidates(symbol, info)
        for index, (filling, source) in enumerate(candidates):
            request = dict(base_request)
            request["type_filling"] = filling

            result = mt5.order_send(request)
            last_result = result

            if result is None:
                msg = f"order_send returned None | last_error={mt5.last_error()}"
                self.logger.error(f"{context} | fill={self._filling_name(filling)} | source={source} | FAILED | class=OTHER_MT5_REJECTION | {msg}")
                return OrderResult(False, symbol, action, None, None, msg, price, "OTHER_MT5_REJECTION")

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                ticket = getattr(result, "order", None)
                self._successful_filling_modes[symbol] = filling
                if index:
                    self.logger.warning(
                        f"{context} | fill={self._filling_name(filling)} | source=fallback | "
                        f"SUCCESS | order={ticket} | cached_fill={self._filling_name(filling)}"
                    )
                else:
                    self.logger.info(f"{symbol} {action.upper()} | operation={operation} | fill={self._filling_name(filling)} | source={source} | SUCCESS | order={ticket}")
                return OrderResult(True, symbol, action, ticket, result.retcode, result.comment, price)
            classification = self.classify_rejection(result.retcode, result.comment)
            if classification != "UNSUPPORTED_FILLING_MODE":
                self.logger.error(
                    f"{context} | fill={self._filling_name(filling)} | source={source} | FAILED | "
                    f"retcode={result.retcode} | comment={result.comment} | class={classification}"
                )
                return OrderResult(False, symbol, action, None, result.retcode, result.comment, price, classification)

            if self._successful_filling_modes.get(symbol) == filling:
                del self._successful_filling_modes[symbol]
            if index + 1 < len(candidates):
                self.logger.warning(
                    f"{context} | fill={self._filling_name(filling)} | source={source} | FAILED | "
                    f"retcode={result.retcode} | comment={result.comment} | class={classification}; trying fallback"
                )

        result = last_result
        retcode = getattr(result, "retcode", None)
        comment = getattr(result, "comment", "all filling modes rejected")
        classification = self.classify_rejection(retcode, comment)
        self.logger.error(
            f"{context} | FAILED | retcode={retcode} | comment={comment} | "
            f"class={classification} | attempted_fills={len(candidates)}"
        )
        return OrderResult(False, symbol, action, None, retcode, comment, price, classification)

    def buy(self, symbol: str, volume: float, comment: str, stop_loss=None, take_profit=None) -> OrderResult:
        return self._send_market_order(symbol, "BUY", volume, comment=comment, stop_loss=stop_loss, take_profit=take_profit)

    def sell(self, symbol: str, volume: float, comment: str, stop_loss=None, take_profit=None) -> OrderResult:
        return self._send_market_order(symbol, "SELL", volume, comment=comment, stop_loss=stop_loss, take_profit=take_profit)

    def close_position(self, position, comment: str) -> OrderResult:
        action = "SELL" if position.type == mt5.POSITION_TYPE_BUY else "BUY"
        return self._send_market_order(
            symbol=position.symbol,
            action=action,
            volume=position.volume,
            position_ticket=position.ticket,
            comment=comment,
        )
