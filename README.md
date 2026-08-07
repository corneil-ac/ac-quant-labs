# BULLET Strategy Runtime

BULLET is an MT5 trading runtime with a strategy-neutral execution pipeline. The
active MVP runs `TrendMomentumStrategy` independently on EURUSD, GBPUSD, USDJPY,
and XAUUSD. Legacy statistical-arbitrage modules remain in the repository for
reference, but `main.py` neither imports nor executes them.

## Strategy

The active strategy combines an H1 close versus EMA 200 trend bias with M15 EMA
20/50 momentum, an EMA 20 pullback within the latest three closed M15 candles,
and a directional confirmation candle. The short lookback lets confirmation
follow the pullback instead of requiring both events on one candle. Data requests
start at MT5 position 1, so the forming candle is excluded. Stops are 2 ATR(14),
and targets are two times the initial risk.

Select the registered strategy with `ACTIVE_STRATEGY` in `config.py`. Execution
only consumes the generic `StrategySignal` contract; it does not calculate EMA
or ATR values.

## Safety

- Calendar checks fail closed and happen before order validation/submission.
- A BULLET-owned position prevents another entry on the same symbol.
- A signal candle can be processed only once per symbol.
- Fixed volume is validated against each symbol's MT5 contract before ordering.
- `DRY_RUN = True` keeps the complete pipeline while preventing real orders.
- Successful submissions are appended to `data/trade_journal.csv`.

Install `requirements.txt`, start an authenticated MT5 terminal, and run:

```bash
python main.py
```

This project is intended for demo testing and strategy development, not
untested live-account use.
