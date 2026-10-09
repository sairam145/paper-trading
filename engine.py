"""Paper-trading engine. Same code runs live (run_live.py) and on history (replay.py).

Each bot has its own paper account. Every STEP_HOURS it may open one "slice"
(equity x leverage / 6) long or short, held HOLD_HOURS. Fills = candle close +/- slippage,
fee charged on entry and exit. Kill switch closes everything and halts the bot.
Everything is persisted in SQLite so the bot survives restarts.
"""
import sqlite3
import pandas as pd
import config as C
import model as M

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts(bot TEXT PRIMARY KEY, cash REAL, peak REAL, halted INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS slices(id INTEGER PRIMARY KEY, bot TEXT, side INTEGER, opened TEXT,
    entry REAL, notional REAL, close_due TEXT, closed TEXT, exit REAL, pnl REAL, status TEXT);
CREATE TABLE IF NOT EXISTS equity(bot TEXT, hour TEXT, equity REAL, exposure REAL, price REAL,
    PRIMARY KEY(bot, hour));
CREATE TABLE IF NOT EXISTS signals(bot TEXT, hour TEXT, score REAL, signal INTEGER, PRIMARY KEY(bot, hour));
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""
SLICES = C.HOLD_HOURS // C.STEP_HOURS


class PaperEngine:
    def __init__(self, db_path=C.DB_PATH, bots=None, models_dir="models"):
        self.db = sqlite3.connect(db_path)
        self.db.executescript(SCHEMA)
        self.models = {b["name"]: M.load(f"{models_dir}/{b['name']}.json") for b in (bots or C.BOTS)}
        for name in self.models:
            self.db.execute("INSERT OR IGNORE INTO accounts VALUES(?,?,?,0)",
                            (name, C.START_CAPITAL, C.START_CAPITAL))
        self.db.commit()

    # ---- bookkeeping helpers ----
    def last_hour(self):
        r = self.db.execute("SELECT v FROM meta WHERE k='last_hour'").fetchone()
        return pd.Timestamp(r[0]) if r else None

    def _open_slices(self, bot):
        return self.db.execute("SELECT id, side, entry, notional, close_due FROM slices "
                               "WHERE bot=? AND status='open'", (bot,)).fetchall()

    def _close(self, sid, side, entry, notional, price, t):
        exit_px = price * (1 - side * C.SLIPPAGE_PER_SIDE)
        pnl = side * notional * (exit_px / entry - 1) - C.FEE_PER_SIDE * notional * (1 + exit_px / entry)
        self.db.execute("UPDATE slices SET closed=?, exit=?, pnl=?, status='closed' WHERE id=?",
                        (str(t), exit_px, pnl, sid))
        self.db.execute("UPDATE accounts SET cash=cash+? WHERE bot=?", (pnl, self.bot))
        return pnl

    def _equity(self, bot, price):
        cash = self.db.execute("SELECT cash FROM accounts WHERE bot=?", (bot,)).fetchone()[0]
        unreal, exposure = 0.0, 0.0
        for _, side, entry, notional, _ in self._open_slices(bot):
            unreal += side * notional * (price / entry - 1)
            exposure += side * notional
        return cash + unreal, exposure

    # ---- one closed hourly candle ----
    def process_hour(self, t: pd.Timestamp, price: float, metrics_row: pd.DataFrame):
        """t = candle open time; price = its close. metrics_row = 1-row DataFrame of metrics at t."""
        last = self.last_hour()
        if last is not None and t <= last:
            return
        for name, m in self.models.items():
            self.bot = name
            cash, peak, halted = self.db.execute(
                "SELECT cash, peak, halted FROM accounts WHERE bot=?", (name,)).fetchone()

            # 1) close slices whose 24h are up
            for sid, side, entry, notional, due in self._open_slices(name):
                if pd.Timestamp(due) <= t:
                    self._close(sid, side, entry, notional, price, t)

            # 2) mark to market, kill switch / wipe-out
            eq, _ = self._equity(name, price)
            peak = max(peak, eq)
            if not halted and (eq <= 0 or eq <= peak * (1 - C.KILL_SWITCH_DRAWDOWN)):
                for sid, side, entry, notional, _ in self._open_slices(name):
                    self._close(sid, side, entry, notional, price, t)
                halted = 1
                eq, _ = self._equity(name, price)

            # 3) maybe open a new slice
            if not halted and t.hour % C.STEP_HOURS == 0:
                s = float(M.score(m, metrics_row).iloc[0])
                sig = M.signal(m, s)
                self.db.execute("INSERT OR REPLACE INTO signals VALUES(?,?,?,?)", (name, str(t), s, sig))
                if sig != 0 and eq > 0:
                    notional = eq * m["leverage"] / SLICES
                    entry = price * (1 + sig * C.SLIPPAGE_PER_SIDE)
                    self.db.execute(
                        "INSERT INTO slices(bot, side, opened, entry, notional, close_due, status) "
                        "VALUES(?,?,?,?,?,?,'open')",
                        (name, sig, str(t), entry, notional, str(t + pd.Timedelta(hours=C.HOLD_HOURS))))

            eq, exposure = self._equity(name, price)
            self.db.execute("UPDATE accounts SET peak=?, halted=? WHERE bot=?", (max(peak, eq), halted, name))
            self.db.execute("INSERT OR REPLACE INTO equity VALUES(?,?,?,?,?)", (name, str(t), eq, exposure, price))
        self.db.execute("INSERT OR REPLACE INTO meta VALUES('last_hour', ?)", (str(t),))
        self.db.commit()
