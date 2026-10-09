"""Does order-book imbalance predict BTC's next 1-15 minutes well enough to beat costs?

Reads obi/data/obi.db (from recorder.py). For each threshold, an "event" is the first second |OBI| crosses
it (then a 60s cooldown). Direction = sign of OBI (buy-heavy book -> long).

Part A - raw prediction: did mid price move in the predicted direction after 1, 5, 15 minutes?
Part B - the actual trading rule: enter by crossing the spread (buy at ask / sell at bid),
          take profit +0.20%, stop -0.20%, give up after 15 min, minus round-trip fee.
Each is compared with the same rule fired at random seconds (baseline). An edge must beat both
the baseline and the ~63-67% win rate a 1:1 rule needs after costs.

  python obi/analyze.py [--fee-bps 7] [--db obi/data/obi.db]
"""
import argparse
import os
import sqlite3

import numpy as np
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--db", default=os.path.join(os.path.dirname(__file__), "data", "obi.db"))
ap.add_argument("--fee-bps", type=float, default=7.0, help="round-trip fee in basis points (7 = 0.07%%)")
ap.add_argument("--tp", type=float, default=0.0020)
ap.add_argument("--sl", type=float, default=0.0020)
ap.add_argument("--timeout", type=int, default=900)
ap.add_argument("--notional", type=float, default=5000.0)
args = ap.parse_args()

s = pd.read_sql("SELECT * FROM snaps ORDER BY ts", sqlite3.connect(args.db))
if len(s) < 3600:
    raise SystemExit(f"Only {len(s)} snapshots (~{len(s)/3600:.1f}h). Let the recorder run at least a day.")
ts, bid, ask, mid = (s[c].to_numpy() for c in ("ts", "bid", "ask", "mid"))
days = (ts[-1] - ts[0]) / 86400


def fwd_mid(idx, h):
    """mid price h seconds after each index (nearest snapshot at/after; NaN if a data gap > 5s)."""
    j = np.searchsorted(ts, ts[idx] + h)
    ok = (j < len(ts))
    out = np.full(len(idx), np.nan)
    jj = j[ok]
    good = ts[jj] - (ts[idx][ok] + h) <= 5
    out[np.where(ok)[0][good]] = mid[jj[good]]
    return out


def simulate(idx, side, one_at_a_time=True):
    """1:1 bracket trade per event, only one open position at a time (events during a trade are skipped).
    Returns net return per trade (fraction) after spread + fees."""
    res, busy_until = [], -1.0
    for i, d in zip(idx, side):
        if one_at_a_time and ts[i] < busy_until:
            continue
        entry = ask[i] if d > 0 else bid[i]
        end = np.searchsorted(ts, ts[i] + args.timeout)
        if end >= len(ts):
            continue
        exit_px = bid[i + 1:end + 1] if d > 0 else ask[i + 1:end + 1]  # price we could sell/buy back at
        r = d * (exit_px / entry - 1)
        hit = np.where((r >= args.tp) | (r <= -args.sl))[0]
        gross = (args.tp if r[hit[0]] >= args.tp else -args.sl) if len(hit) else r[-1]
        busy_until = ts[i + 1 + hit[0]] if len(hit) else ts[end]
        res.append(gross - args.fee_bps / 1e4)
    return np.array(res)


def events(col, thr, cooldown=60):
    x = s[col].to_numpy()
    out, last = [], -1e18
    for i in np.where(np.abs(x) >= thr)[0]:
        if ts[i] - last >= cooldown:
            out.append(i)
            last = ts[i]
    return np.array(out, dtype=int)


rows = []
rng = np.random.default_rng(0)
for col in ("obi10", "obi5"):
    for thr in (0.5, 0.6, 0.7, 0.8):
        ev = events(col, thr)
        for filt in ("OBI only", "OBI + CVD agrees"):
            idx = ev
            if filt != "OBI only":
                idx = ev[np.sign(s["cvd60"].to_numpy()[ev]) == np.sign(s[col].to_numpy()[ev])]
            if len(idx) < 10:
                continue
            side = np.sign(s[col].to_numpy()[idx])
            row = {"signal": col, "threshold": thr, "filter": filt, "events/day": len(idx) / days}
            for h in (60, 300, 900):
                mv = side * (fwd_mid(idx, h) / mid[idx] - 1) * 1e4
                row[f"right_{h // 60}m"] = np.nanmean(mv > 0)
                row[f"bps_{h // 60}m"] = np.nanmean(mv)
            pnl = simulate(idx, side)
            rnd = rng.choice(len(ts) - args.timeout - 1, size=min(len(idx) * 3, 3000), replace=False)
            base = simulate(np.sort(rnd), rng.choice([-1, 1], size=len(rnd)), one_at_a_time=False)
            row.update({"trades/day": len(pnl) / days, "win_rate": (pnl > 0).mean(), "random_win": (base > 0).mean(),
                        "net_$/trade": pnl.mean() * args.notional,
                        "net_$/day": pnl.mean() * args.notional * len(pnl) / days})
            rows.append(row)

pd.set_option("display.width", 250, "display.max_columns", 30, "display.float_format", "{:.2f}".format)
print(f"{len(s):,} snapshots, {days:.1f} days, BTC {mid[0]:,.0f} -> {mid[-1]:,.0f} | "
      f"rule: TP +{args.tp*100:.2f}% / SL -{args.sl*100:.2f}% / {args.timeout//60} min, "
      f"fee {args.fee_bps:.0f} bps round trip, spread crossed, ${args.notional:,.0f} position")
print("right_Xm = share of events where mid moved the predicted way after X min; bps_Xm = avg move (1 bp = 0.01%)")
print("win_rate vs random_win: the signal must clearly beat random entries AND exceed ~63-67% to profit at 1:1\n")
print(pd.DataFrame(rows).to_string(index=False) if rows else "Not enough events yet.")
