# Paper Trader v0.1 (BTC, live data, fake money)

Seven bots, each trained on a different set of metrics, trade BTC-USD on **live Coinbase prices**
with a **$1,000 paper account each**. No API key, no exchange account, no real money.

## Setup (laptop or any cloud VM, Python 3.10+)
    pip install -r requirements.txt
    python train.py          # trains all bots, prints walk-forward scoreboard, writes models/
    python run_live.py       # starts paper trading; leave it running

Check results any time (in a second terminal):
    python report.py

## Free 24/7 hosting: GitHub Actions ($0, no server, no card)
1. Push this folder to a **private** GitHub repo (branch `main`).
2. Actions tab -> enable workflows -> "paper-trader" -> **Run workflow** once to start.
3. It then runs every hour at :07 UTC (`.github/workflows/paper-trader.yml`).
4. Results: switch to the `state` branch on GitHub and open **REPORT.txt** (works on the GitHub phone app).
   The bot's database, report and log live only on that branch; it is overwritten each run, so the repo stays small.

Cost: ~1 runner-minute per hour = ~744 min/month, under the 2,000 free minutes for private repos.
GitHub may start a scheduled run a few minutes late; the bot trades on candle times, not run times, and
catches up missed hours (up to 48h). GitHub pauses schedules after 60 days without repo activity;
the hourly state push normally keeps it active, and re-enabling is one click.

Alternative: any always-on machine -> `nohup python run_live.py &` (or `--once` from cron / Task Scheduler).

## How a bot trades
- Every 4 hours it scores the market with its metrics -> long, short, or nothing.
- Each trade ("slice") = equity x leverage / 6, held 24h, so up to 6 overlap.
- Fill = candle close +/- 0.02% slippage, 0.05% fee on entry and exit.
- Kill switch: equity 40% below its peak -> close everything, bot halts.
- All state in state/paper.db (SQLite): trades, hourly equity, every signal. Survives restarts;
  catches up missed hours (up to 48h) after downtime. Log: state/live.log

## Add or change bots
Edit BOTS in config.py (pick metrics, leverage, selectivity `edge`), then `python train.py`.
New metrics: add a line in metrics.py build_metrics(), list its name in config.py.
Refresh training history: `python update_data.py` then `python train.py`.

## Verify the engine yourself
    python replay.py 2025-01-01   # pushes 2025->now through the live engine, out-of-sample, with checks

Files: config.py (settings) | metrics.py | model.py | train.py | feed.py (Coinbase) | engine.py |
run_live.py | report.py | replay.py | update_data.py
