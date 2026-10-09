"""Scoreboard for all paper bots.   python report.py  [--db state/replay.db]"""
import sqlite3
import sys
import pandas as pd
import config as C

db = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else C.DB_PATH
con = sqlite3.connect(db)
eq = pd.read_sql("SELECT * FROM equity", con, parse_dates=["hour"])
sl = pd.read_sql("SELECT * FROM slices", con)
acc = pd.read_sql("SELECT * FROM accounts", con).set_index("bot")
if eq.empty:
    sys.exit("No data yet - run run_live.py first.")

rows = []
for bot, g in eq.groupby("bot"):
    g = g.sort_values("hour")
    closed = sl[(sl.bot == bot) & (sl.status == "closed")]
    days = max((g.hour.iloc[-1] - g.hour.iloc[0]).total_seconds() / 86400, 1 / 24)
    rows.append({
        "bot": bot,
        "equity_$": g.equity.iloc[-1],
        "return_%": (g.equity.iloc[-1] / C.START_CAPITAL - 1) * 100,
        "per_30d_$": (g.equity.iloc[-1] - C.START_CAPITAL) / days * 30,
        "worst_drop_%": (1 - g.equity / g.equity.cummax()).max() * 100,
        "closed_trades": len(closed),
        "win_rate": (closed.pnl > 0).mean() if len(closed) else float("nan"),
        "open_slices": int(((sl.bot == bot) & (sl.status == "open")).sum()),
        "exposure_$": g.exposure.iloc[-1],
        "halted": bool(acc.at[bot, "halted"]),
    })
first, last = eq.hour.min(), eq.hour.max()
print(f"Paper trading {first:%Y-%m-%d %H:00} -> {last:%Y-%m-%d %H:00} UTC "
      f"({(last - first).total_seconds() / 86400:.1f} days) | BTC now ${eq.price.iloc[-1]:,.0f}")
pd.set_option("display.width", 200, "display.float_format", "{:,.2f}".format)
print(pd.DataFrame(rows).sort_values("equity_$", ascending=False).to_string(index=False))
