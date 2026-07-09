import MetaTrader5 as mt5
import config


def filling_candidates(symbol):
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


def close_position(p):
    tick = mt5.symbol_info_tick(p.symbol)
    info = mt5.symbol_info(p.symbol)

    if tick is None or info is None:
        print(f"{p.symbol}: missing tick/info. Skipping.")
        return False

    if p.type == mt5.POSITION_TYPE_BUY:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
        action = "SELL"
    else:
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
        action = "BUY"

    base_request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": p.symbol,
        "volume": p.volume,
        "type": order_type,
        "position": p.ticket,
        "price": price,
        "deviation": config.DEVIATION,
        "magic": config.MAGIC,
        "comment": "manual_close_bot_positions",
        "type_time": mt5.ORDER_TIME_GTC,
    }

    for filling in filling_candidates(p.symbol):
        request = dict(base_request)
        request["type_filling"] = filling

        result = mt5.order_send(request)

        if result is None:
            print(f"Close {p.symbol} ticket={p.ticket} via {action} fill={filling} -> None, {mt5.last_error()}")
            continue

        print(f"Close {p.symbol} ticket={p.ticket} via {action} fill={filling} -> retcode={result.retcode}, {result.comment}")

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return True

    # Final fallback: omit type_filling.
    result = mt5.order_send(base_request)

    if result is None:
        print(f"Close {p.symbol} ticket={p.ticket} via {action} fill=OMITTED -> None, {mt5.last_error()}")
        return False

    print(f"Close {p.symbol} ticket={p.ticket} via {action} fill=OMITTED -> retcode={result.retcode}, {result.comment}")
    return result.retcode == mt5.TRADE_RETCODE_DONE


if not mt5.initialize():
    print("MT5 initialize failed:", mt5.last_error())
    raise SystemExit

positions = mt5.positions_get()
if positions is None:
    print("No positions found")
    mt5.shutdown()
    raise SystemExit

bot_positions = [p for p in positions if p.magic == config.MAGIC]

if not bot_positions:
    print("No bot positions found for magic:", config.MAGIC)
    mt5.shutdown()
    raise SystemExit

print(f"Found {len(bot_positions)} bot position(s). Closing...")

closed = 0
failed = 0

for p in bot_positions:
    if close_position(p):
        closed += 1
    else:
        failed += 1

print(f"Done. Closed={closed}, Failed={failed}")

mt5.shutdown()
