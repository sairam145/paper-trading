"""Fit / save / load / score a bot's model. Kept tiny and dependency-light (numpy + pandas)."""
import json
import numpy as np
import pandas as pd


def _z(X, mu, sd):
    return ((X - mu) / sd).clip(-3, 3)


def fit(bot, X: pd.DataFrame, fwd: pd.Series, alpha=10.0) -> dict:
    """X: metric rows, fwd: next-24h log return. Returns a JSON-serialisable model."""
    cols = bot["metrics"]
    d = X[cols].join(fwd.rename("fwd")).dropna()
    mu, sd = d[cols].mean(), d[cols].std()
    Z = _z(d[cols], mu, sd)
    if bot["model"] == "single":
        sign = float(np.sign(d[cols[0]].rank().corr(d["fwd"].rank())))
        coef, intercept = np.array([sign]), 0.0
    else:  # ridge regression, closed form
        A = Z.values
        y = d["fwd"].values - d["fwd"].mean()
        Zc = A - A.mean(0)
        coef = np.linalg.solve(Zc.T @ Zc + alpha * np.eye(len(cols)), Zc.T @ y)
        intercept = float(d["fwd"].mean() - A.mean(0) @ coef)
    insample = Z.values @ coef + intercept
    lo, hi = np.quantile(insample, [bot["edge"], 1 - bot["edge"]])
    return {"name": bot["name"], "metrics": cols, "mu": mu.tolist(), "sd": sd.tolist(),
            "coef": np.asarray(coef).tolist(), "intercept": intercept,
            "thr_lo": float(lo), "thr_hi": float(hi),
            "trained_until": str(d.index[-1])}


def score(model: dict, X: pd.DataFrame) -> pd.Series:
    cols = model["metrics"]
    Z = _z(X[cols], pd.Series(model["mu"], cols), pd.Series(model["sd"], cols))
    return pd.Series(Z.values @ np.array(model["coef"]) + model["intercept"], index=X.index)


def signal(model: dict, s: float) -> int:
    """+1 long, -1 short, 0 stay out."""
    if s is None or np.isnan(s):
        return 0
    return 1 if s >= model["thr_hi"] else (-1 if s <= model["thr_lo"] else 0)


def save(model, path):
    with open(path, "w") as f:
        json.dump(model, f, indent=1)


def load(path):
    with open(path) as f:
        return json.load(f)
