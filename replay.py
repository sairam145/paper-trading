"""Replay test: push real history through the *live* engine, hour by hour, as if it were live.

Models are trained only on data before REPLAY_FROM, so the replay is out-of-sample.
Then checks: (1) engine equity matches an independent vectorised calculation,
(2) metrics computed on a 720h live-style window match metrics on full history.

  python replay.py [2025-01-01]
"""
import os
import sys
import numpy as np
import pandas as pd
import config as C
import model as M
from engine import PaperEngine
from metrics import build_metrics

os.makedirs("state", exist_ok=True)
REPLAY_FROM = sys.argv[1] if len(sys.argv) > 1 else "2025-01-01"
os.makedirs("state/replay_models", exist_ok=True)
DB = "state/replay.db"
if os.path.exists(DB):
    os.remove(DB)

h = pd.read_parquet("data/btc_1h.parquet").loc[C.TRAIN_START:].iloc[:-1]
X = build_metrics(h)
lc = np.log(h["close"])
fwd = lc.shift(-C.HOLD_HOURS) - lc
cut = pd.Timestamp(REPLAY_FROM, tz="UTC") - pd.Timedelta(hours=C.HOLD_HOURS)
for bot in C.BOTS:
    m = M.fit(bot, X[X.index < cut], fwd[X.index < cut])
    m.update({k: bot[k] for k in ("model", "edge", "leverage")})
    M.save(m, f"state/replay_models/{bot['name']}.json")

eng = PaperEngine(DB, models_dir="state/replay_models")
hours = h.loc[REPLAY_FROM:].index
for i, t in enumerate(hours):
    eng.process_hour(t, float(h.at[t, "close"]), X.loc[[t]])
print(f"Replayed {len(hours):,} hours {hours[0]:%Y-%m-%d} -> {hours[-1]:%Y-%m-%d}\n")
os.system(f"{sys.executable} report.py --db {DB}")

# ---- check 1: engine vs independent vectorised math (no kill switch case) ----
print("\nCheck 1 - engine vs independent calculation (final equity):")
r_next = (h["close"].shift(-1) / h["close"] - 1).fillna(0)
for bot in C.BOTS:
    m = M.load(f"state/replay_models/{bot['name']}.json")
    idx = hours[hours.hour % C.STEP_HOURS == 0]
    sig = pd.Series(0.0, index=hours)
    sig.loc[idx] = [M.signal(m, s) for s in M.score(m, X.loc[idx])]
    eng_eq = pd.read_sql(f"SELECT hour, equity FROM equity WHERE bot='{bot['name']}'", eng.db).equity
    halted = eng.db.execute("SELECT halted FROM accounts WHERE bot=?", (bot["name"],)).fetchone()[0]
    pos = sig.rolling(C.HOLD_HOURS, min_periods=1).sum() / (C.HOLD_HOURS // C.STEP_HOURS)
    cost = 2 * (C.FEE_PER_SIDE + C.SLIPPAGE_PER_SIDE)
    ret = bot["leverage"] * (pos.shift(1).fillna(0) * h["close"].pct_change().loc[hours].fillna(0)
                             - sig.abs() * cost / (C.HOLD_HOURS // C.STEP_HOURS))
    vec = C.START_CAPITAL * (1 + ret).cumprod()
    note = "(halted by kill switch - paths diverge after that, expected)" if halted else ""
    print(f"   {bot['name']:<16} engine ${eng_eq.iloc[-1]:>9,.2f}   independent ${vec.iloc[-1]:>9,.2f}  {note}")

# ---- check 2: live-style 720h window gives the same metrics as full history ----
print("\nCheck 2 - metrics from a 720h window vs full history (max abs difference):")
diffs = []
for t in hours[::500]:
    win = h.loc[:t].tail(C.HISTORY_HOURS)
    diffs.append((build_metrics(win).loc[t] - X.loc[t]).abs())
d = pd.concat(diffs, axis=1).max(axis=1)
print("   " + ", ".join(f"{k}:{v:.1e}" for k, v in d.items()))
