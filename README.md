# Pair Trading Bot V2

This is a safer, cleaner V2 of your MT5 pair trading bot.

## What changed from V1

- Broker-compatible filling mode instead of hardcoded IOC.
- Exit logic is checked before new entries.
- Symbol lock prevents duplicate stacking.
- Cooldown prevents rapid re-entry.
- If second leg fails, bot immediately closes the first leg.
- Logs are written to the `logs/` folder.
- Live console dashboard.

## Install

Open CMD:

```cmd
cd "C:\Users\owner\Desktop"
mkdir pair_trading_bot_v2
```

Copy these files into that folder.

Then install requirements:

```cmd
py -m pip install -r requirements.txt
```

## Run

Make sure MT5 is open and logged into your new demo account.

Then:

```cmd
cd "C:\Users\owner\Desktop\pair_trading_bot_v2"
py main.py
```

## Stop

Press:

```cmd
CTRL+C
```

## First safe test

Before letting it trade, open `config.py` and set:

```python
DRY_RUN = True
```

Run the bot. It will print trades without placing real demo orders.

When the logs look correct, change:

```python
DRY_RUN = False
```

## Important

This is for demo testing and strategy development. Do not use on a live account until you have tested it heavily.
