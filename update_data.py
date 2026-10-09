"""Refresh data/btc_1h.parquet from Bitstamp 1-minute history on GitHub, then retrain with train.py."""
import os, urllib.request
import pandas as pd
REPO = "https://raw.githubusercontent.com/ff137/bitstamp-btcusd-minute-data/main/data"
os.makedirs("data", exist_ok=True)
for remote, local in [("historical/btcusd_bitstamp_1min_2012-2025.csv.gz", "data/hist.csv.gz"),
                      ("updates/btcusd_bitstamp_1min_latest.csv", "data/latest.csv")]:
    if remote.startswith("historical") and os.path.exists(local):
        continue  # bulk file never changes
    print("downloading", remote); urllib.request.urlretrieve(f"{REPO}/{remote}", local)
m = pd.concat([pd.read_csv("data/hist.csv.gz"), pd.read_csv("data/latest.csv")])
m = m.drop_duplicates("timestamp").sort_values("timestamp")
m["ts"] = pd.to_datetime(m["timestamp"], unit="s", utc=True)
h = m.set_index("ts").loc["2018-01-01":].resample("1h").agg(
    {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
h.to_parquet("data/btc_1h.parquet"); print(h.index.min(), "->", h.index.max(), len(h), "hours")
