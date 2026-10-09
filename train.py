"""Train every bot in config.BOTS.

1. Walk-forward scoreboard: each year from VALIDATE_FROM is predicted by a model trained only on
   earlier data (24h purge gap), traded with the bot's own leverage, fees and slippage.
2. Final model: retrained on all history, saved to models/<name>.json for the paper trader.

Usage: python train.py            (needs data/btc_1h.parquet; see README for how to refresh it)
"""
import numpy as np
import pandas as pd
import config as C
import model as M
from metrics import build_metrics

h = pd.read_parquet("data/btc_1h.parquet").loc[C.TRAIN_START:]
h = h[h.index < pd.Timestamp.now(tz="UTC").floor("h")]  # closed candles only
X = build_metrics(h)
lc = np.log(h["close"])
fwd = lc.shift(-C.HOLD_HOURS) - lc
r_next = (h["close"].shift(-1) / h["close"] - 1).fillna(0)
cost = 2 * (C.FEE_PER_SIDE + C.SLIPPAGE_PER_SIDE)
slices = C.HOLD_HOURS // C.STEP_HOURS


def walk_forward(bot):
    sig = pd.Series(0.0, index=h.loc[C.VALIDATE_FROM:].index)
    for yr in range(pd.Timestamp(C.VALIDATE_FROM).year, sig.index[-1].year + 1):
        start = pd.Timestamp(f"{yr}-01-01", tz="UTC")
        train_mask = X.index < start - pd.Timedelta(hours=C.HOLD_HOURS)
        m = M.fit(bot, X[train_mask], fwd[train_mask])
        idx = sig.index[(sig.index.year == yr) & (sig.index.hour % C.STEP_HOURS == 0)]
        s = M.score(m, X.loc[idx])
        sig.loc[idx] = [M.signal(m, v) for v in s]
    pos = sig.rolling(C.HOLD_HOURS, min_periods=1).sum() / slices
    ret = bot["leverage"] * (pos * r_next.loc[sig.index] - sig.abs() * cost / slices)
    eq = C.START_CAPITAL * (1 + ret).clip(lower=0).cumprod()
    months = (eq.index[-1] - eq.index[0]).days / 30.44
    trades = sig[sig != 0]
    wins = (trades * np.expm1(fwd.loc[trades.index]) - cost > 0).mean()
    yearly = eq.resample("YE").last()
    yearly_pct = yearly.pct_change().fillna(yearly.iloc[0] / C.START_CAPITAL - 1) * 100
    return {"bot": bot["name"], "trades/mo": len(trades) / months, "win_rate": wins,
            "final_$": eq.iloc[-1], "avg_$/mo": (eq.iloc[-1] - C.START_CAPITAL) / months,
            "worst_drop_%": (1 - eq / eq.cummax()).max() * 100,
            "hit_kill_switch": bool(((1 - eq / eq.cummax()) >= C.KILL_SWITCH_DRAWDOWN).any()),
            "by_year_%": " ".join(f"{t.year}:{v:+.0f}" for t, v in yearly_pct.items())}


rows = []
for bot in C.BOTS:
    rows.append(walk_forward(bot))
    final = M.fit(bot, X, fwd)
    final.update({k: bot[k] for k in ("model", "edge", "leverage")})
    M.save(final, f"models/{bot['name']}.json")

board = pd.DataFrame(rows).sort_values("avg_$/mo", ascending=False)
board.to_csv("models/scoreboard.csv", index=False)
pd.set_option("display.width", 220, "display.float_format", "{:.2f}".format)
print(f"Walk-forward scoreboard {C.VALIDATE_FROM} -> {h.index[-1]:%Y-%m-%d}, "
      f"${C.START_CAPITAL:,.0f} per bot, costs {cost*100:.2f}% round trip")
print(board.to_string(index=False))
print(f"\nSaved {len(C.BOTS)} trained models to models/")
