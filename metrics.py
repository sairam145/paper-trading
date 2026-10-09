"""Step 2: candidate metrics. Every metric at hour t uses only data up to the close of hour t."""
import numpy as np
import pandas as pd


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def build_metrics(h: pd.DataFrame) -> pd.DataFrame:
    c, hi, lo, v = h["close"], h["high"], h["low"], h["volume"]
    r1 = np.log(c).diff()
    f = pd.DataFrame(index=h.index)

    # Momentum: how far price moved over recent windows
    for n, name in [(1, "mom_1h"), (4, "mom_4h"), (24, "mom_24h"), (168, "mom_7d")]:
        f[name] = np.log(c).diff(n)

    # Trend: distance from moving averages
    for n in (20, 50, 200):
        f[f"dist_ma{n}"] = c / c.rolling(n).mean() - 1

    # Oscillators
    f["rsi_14"] = rsi(c, 14)
    f["bollinger_z"] = (c - c.rolling(20).mean()) / c.rolling(20).std()

    # Volatility: level and whether it's expanding or contracting (squeeze)
    vol24 = r1.rolling(24).std()
    f["volatility_24h"] = vol24
    f["vol_expansion"] = vol24 / r1.rolling(168).std()

    # Volume: surge vs normal, and volume-weighted buying pressure
    f["volume_surge"] = v / v.rolling(168).mean()
    clv = ((c - lo) - (hi - c)) / (hi - lo).replace(0, np.nan)  # where the candle closed in its range
    f["buy_pressure_24h"] = (clv * v).rolling(24).sum() / v.rolling(24).sum()

    # Range and breakout
    hi48, lo48 = hi.rolling(48).max(), lo.rolling(48).min()
    f["range_position_48h"] = (c - lo48) / (hi48 - lo48)
    f["breakout_48h"] = c / hi.shift(1).rolling(48).max() - 1

    # Calendar
    f["hour_utc"] = h.index.hour
    f["weekday"] = h.index.dayofweek
    return f


def forward_returns(h: pd.DataFrame, horizons=(1, 4, 24)) -> pd.DataFrame:
    lc = np.log(h["close"])
    return pd.DataFrame({f"fwd_{n}h": lc.shift(-n) - lc for n in horizons}, index=h.index)
