"""Run all bots on live Coinbase data with paper money. Leave it running (Ctrl+C to stop).

  python run_live.py          # loop forever, wakes ~1.5 min after every hour
  python run_live.py --once   # process the newest closed hour(s) and exit (for cron / Task Scheduler)

Paper trading starts from the first hour it sees; it never back-fills trades into the past.
After downtime it catches up on missed hours (up to 48h) in order.
"""
import os
import sys
import time
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
import config as C
from engine import PaperEngine
from feed import hourly_candles
from metrics import build_metrics

os.makedirs("state", exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.FileHandler("state/live.log"), logging.StreamHandler()])
log = logging.getLogger()


def cycle(engine):
    candles = hourly_candles(C.PRODUCT, C.HISTORY_HOURS)
    X = build_metrics(candles)
    last = engine.last_hour()
    if last is None:
        new_hours = candles.index[-1:]  # start paper trading now
    else:
        new_hours = candles.index[(candles.index > last)][-48:]
    for t in new_hours:
        engine.process_hour(t, float(candles.at[t, "close"]), X.loc[[t]])
        rows = engine.db.execute(
            "SELECT e.bot, e.equity, e.exposure, s.signal FROM equity e "
            "LEFT JOIN signals s ON s.bot=e.bot AND s.hour=e.hour WHERE e.hour=?", (str(t),)).fetchall()
        log.info(f"hour {t:%Y-%m-%d %H:00} UTC  BTC ${candles.at[t, 'close']:,.0f}")
        for bot, eq, expo, sig in rows:
            tag = {1: "OPEN LONG", -1: "OPEN SHORT", 0: "no trade"}.get(sig, "")
            log.info(f"   {bot:<16} equity ${eq:>9,.2f}  exposure ${expo:>+9,.0f}  {tag}")


def main():
    engine = PaperEngine()
    log.info(f"paper trader started: {len(engine.models)} bots, {C.PRODUCT}")
    while True:
        try:
            cycle(engine)
        except Exception as e:  # network hiccup etc. -> retry next cycle, never crash
            log.exception(f"cycle failed: {e}")
        if "--once" in sys.argv:
            break
        now = datetime.now(timezone.utc)
        wake = now.replace(minute=1, second=30, microsecond=0) + timedelta(hours=1)
        time.sleep(max(30, (wake - now).total_seconds()))


if __name__ == "__main__":
    main()
