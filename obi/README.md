# Order-Book Imbalance (OBI) Research - observation only

Tests whether order-book imbalance (OBI) + cumulative volume delta (CVD) predict BTC's next 1-15 minutes
well enough to beat spread + fees. **No orders, no account, no API key** - Kraken public data only.

## Run (needs an always-on machine: your PC with sleep disabled, or any VPS)
    pip install websockets pandas
    python obi/recorder.py        # leave running; saves 1 snapshot/second to obi/data/obi.db (~5 MB/day)

Windows: Settings -> System -> Power -> Screen and sleep -> "When plugged in, put my device to sleep: Never".
Restarting the recorder is safe - it appends to the same database.

## Analyze (after >= 1 day; judge after 1-2 weeks)
    python obi/analyze.py                 # default 7 bps round-trip fee
    python obi/analyze.py --fee-bps 10    # stricter costs

What it reports for OBI thresholds 0.5-0.8 (top 5 / top 10 levels), with and without CVD agreeing:
- right_1m/5m/15m: how often mid price moved the predicted way, and by how much (bps)
- the actual rule: enter crossing the spread, TP +0.20% / SL -0.20% / 15-min timeout, fee deducted,
  one position at a time, $5,000 notional (5x on $1,000) -> win rate, $/trade, $/day
- random_win: the same rule at random times. A real edge must beat random AND clear ~63-67% win rate.

## Pass / fail (decided before seeing data)
Pass only if some setting shows win_rate >= 65% AND net_$/trade > 0 over >= 500 trades and >= 2 weeks,
holding in both weeks. Otherwise the signal is not tradable at retail speed and costs.
