"""Order-book imbalance recorder. Observation only: sends NO orders, needs NO account or API key.

Streams Kraken's public BTC/USD order book (top 10 levels) and trades, and once per second saves:
  best bid/ask, mid, OBI over top 5 and top 10 levels, and CVD (buy minus sell volume) over 60s.
analyze.py later finds every moment OBI crossed a threshold and measures what price did next.

  pip install websockets pandas
  python obi/recorder.py          # leave running 24/7 (Ctrl+C to stop; restarts resume the same DB)

~5 MB of data per day.
"""
import asyncio
import json
import logging
import os
import sqlite3
import time
from collections import deque

import websockets

URL = os.environ.get("OBI_WS_URL", "wss://ws.kraken.com/v2")
SYMBOL = "BTC/USD"
DEPTH = 10
CVD_WINDOW = 60.0
DB_PATH = os.environ.get("OBI_DB", os.path.join(os.path.dirname(__file__), "data", "obi.db"))

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger()


class Book:
    def __init__(self):
        self.bids, self.asks = {}, {}

    def reset(self):
        self.bids.clear(), self.asks.clear()

    def apply(self, side_levels, side):
        book = self.bids if side == "bids" else self.asks
        for lvl in side_levels:
            if float(lvl["qty"]) == 0:
                book.pop(float(lvl["price"]), None)
            else:
                book[float(lvl["price"])] = float(lvl["qty"])
        # keep only the subscribed depth
        keep = sorted(book, reverse=(side == "bids"))[:DEPTH]
        for p in list(book):
            if p not in keep:
                del book[p]

    def top(self, n):
        b = sorted(self.bids.items(), reverse=True)[:n]
        a = sorted(self.asks.items())[:n]
        return b, a

    def ready(self):
        return len(self.bids) >= 5 and len(self.asks) >= 5


def obi(bids, asks):
    bv, av = sum(q for _, q in bids), sum(q for _, q in asks)
    return (bv - av) / (bv + av) if bv + av else 0.0


class Recorder:
    def __init__(self):
        self.book = Book()
        self.trades = deque()  # (time, signed qty) ; + = aggressive buy
        self.db = sqlite3.connect(DB_PATH)
        self.db.execute("""CREATE TABLE IF NOT EXISTS snaps(ts REAL PRIMARY KEY, bid REAL, ask REAL, mid REAL,
                           obi5 REAL, obi10 REAL, cvd60 REAL, bidvol10 REAL, askvol10 REAL)""")
        self.db.commit()
        self.rows = 0

    def on_message(self, msg):
        ch, typ = msg.get("channel"), msg.get("type")
        if ch == "book" and typ in ("snapshot", "update"):
            for d in msg["data"]:
                if typ == "snapshot":
                    self.book.reset()
                self.book.apply(d.get("bids", []), "bids")
                self.book.apply(d.get("asks", []), "asks")
        elif ch == "trade" and typ in ("update", "snapshot"):
            now = time.time()
            if typ == "update":
                for t in msg["data"]:
                    self.trades.append((now, float(t["qty"]) * (1 if t["side"] == "buy" else -1)))

    def snapshot(self):
        if not self.book.ready():
            return
        now = time.time()
        while self.trades and self.trades[0][0] < now - CVD_WINDOW:
            self.trades.popleft()
        b10, a10 = self.book.top(10)
        b5, a5 = b10[:5], a10[:5]
        bid, ask = b10[0][0], a10[0][0]
        if bid >= ask:  # crossed book = stale state, skip
            return
        self.db.execute("INSERT OR REPLACE INTO snaps VALUES(?,?,?,?,?,?,?,?,?)",
                        (round(now, 3), bid, ask, (bid + ask) / 2, obi(b5, a5), obi(b10, a10),
                         sum(q for _, q in self.trades), sum(q for _, q in b10), sum(q for _, q in a10)))
        self.rows += 1
        if self.rows % 30 == 0:
            self.db.commit()
        if self.rows % 600 == 0:
            log.info(f"{self.rows:,} snapshots | mid ${(bid + ask) / 2:,.1f} | OBI10 {obi(b10, a10):+.2f}")

    async def ticker(self):
        while True:
            await asyncio.sleep(1.0)
            self.snapshot()

    async def stream(self):
        backoff = 1
        while True:
            try:
                async with websockets.connect(URL, ping_interval=20, max_size=2**22) as ws:
                    for ch, extra in (("book", {"depth": DEPTH}), ("trade", {"snapshot": False})):
                        await ws.send(json.dumps({"method": "subscribe",
                                                  "params": {"channel": ch, "symbol": [SYMBOL], **extra}}))
                    log.info(f"connected to {URL}, recording {SYMBOL} -> {DB_PATH}")
                    backoff = 1
                    async for raw in ws:
                        self.on_message(json.loads(raw))
                log.warning("stream closed by server; reconnecting")
                self.book.reset()
                await asyncio.sleep(1)
            except Exception as e:  # network drop etc.: reconnect with backoff, book rebuilt from snapshot
                log.warning(f"stream error: {e!r}; reconnecting in {backoff}s")
                self.book.reset()
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def run(self):
        await asyncio.gather(self.stream(), self.ticker())


if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))  # clean stop on kill / service stop
    rec = Recorder()
    try:
        asyncio.run(rec.run())
    except KeyboardInterrupt:
        rec.db.commit()
        log.info(f"stopped; {rec.rows:,} snapshots saved")
