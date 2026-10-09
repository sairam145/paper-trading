"""Live market data: Coinbase Exchange public candles (no API key, no account needed)."""
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import pandas as pd

BASE = "https://api.exchange.coinbase.com"


def _get(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "papertrader/0.1"})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))


def parse_candles(rows) -> pd.DataFrame:
    """Coinbase rows: [time, low, high, open, close, volume], newest first."""
    df = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"])
    df["ts"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.set_index("ts")[["open", "high", "low", "close", "volume"]].astype(float)


def hourly_candles(product="BTC-USD", hours=720) -> pd.DataFrame:
    """Last `hours` fully closed hourly candles, oldest first."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)  # start of current (open) hour
    frames, end = [], now
    while sum(len(f) for f in frames) < hours:
        start = end - timedelta(hours=300)
        url = (f"{BASE}/products/{product}/candles?granularity=3600"
               f"&start={start.isoformat()}&end={end.isoformat()}")
        rows = _get(url)
        if not rows:
            break
        frames.append(parse_candles(rows))
        end = start
        time.sleep(0.4)  # stay well under public rate limits
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated()]
    return df[df.index < pd.Timestamp(now)].tail(hours)  # drop the still-forming hour


def last_price(product="BTC-USD") -> float:
    return float(_get(f"{BASE}/products/{product}/ticker")["price"])
