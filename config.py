"""All settings in one place. Add a bot = add a dict to BOTS, then run `python train.py`."""

# ---- trading rules shared by all bots ----
START_CAPITAL = 1000.0     # paper dollars per bot
HOLD_HOURS = 24            # each trade ("slice") is held 24h
STEP_HOURS = 4             # a new slice can open every 4h -> up to 6 overlapping slices
FEE_PER_SIDE = 0.0005      # 0.05% per buy or sell (0.10% round trip)
SLIPPAGE_PER_SIDE = 0.0002 # 0.02% worse fill than the candle close
KILL_SWITCH_DRAWDOWN = 0.40  # bot halts if equity falls 40% below its peak

# ---- training ----
TRAIN_START = "2018-01-01"
VALIDATE_FROM = "2022-01-01"   # walk-forward scoreboard period

ALL = ["mom_1h", "mom_4h", "mom_24h", "mom_7d", "dist_ma20", "dist_ma50", "dist_ma200",
       "rsi_14", "bollinger_z", "volatility_24h", "vol_expansion", "volume_surge",
       "buy_pressure_24h", "range_position_48h", "breakout_48h"]
TREND = ["mom_24h", "mom_7d", "dist_ma20", "dist_ma50", "dist_ma200"]
OSCILLATORS = ["mom_1h", "mom_4h", "rsi_14", "bollinger_z", "range_position_48h", "breakout_48h"]
VOLUME_VOL = ["volatility_24h", "vol_expansion", "volume_surge", "buy_pressure_24h"]

# model: "ridge" = learns weights for the listed metrics; "single" = one metric, direction learned
# edge: trade only when the score is in the top/bottom `edge` share (0.10 = most selective)
BOTS = [
    dict(name="all_metrics_1x", metrics=ALL, model="ridge", edge=0.10, leverage=1),
    dict(name="all_metrics_2x", metrics=ALL, model="ridge", edge=0.10, leverage=2),
    dict(name="all_metrics_5x", metrics=ALL, model="ridge", edge=0.10, leverage=5),
    dict(name="trend_only_2x", metrics=TREND, model="ridge", edge=0.10, leverage=2),
    dict(name="oscillators_2x", metrics=OSCILLATORS, model="ridge", edge=0.10, leverage=2),
    dict(name="volume_vol_2x", metrics=VOLUME_VOL, model="ridge", edge=0.10, leverage=2),
    dict(name="dist_ma20_2x", metrics=["dist_ma20"], model="single", edge=0.10, leverage=2),
]

# ---- live data ----
PRODUCT = "BTC-USD"                     # Coinbase Exchange public market data, no API key needed
HISTORY_HOURS = 720                     # hours of candles fetched each cycle (metrics need ~370)
DB_PATH = "state/paper.db"
