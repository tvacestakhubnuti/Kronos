"""Kronos trading bot: decides once per closed candle, long/flat on spot, with Telegram control.

Run:  python -m bot.main          (configuration via environment / .env, see .env.example)
"""
import csv
import datetime as dt
import json
import logging
import os
import time

import ccxt
import pandas as pd

from .broker import ExchangeBroker, PaperBroker
from .config import Config
from .telegram import Telegram

log = logging.getLogger("bot")
MIN_ORDER_QUOTE = 10.0  # ignore dust below this value (most exchanges reject smaller orders)


class Bot:
    def __init__(self, cfg, exchange=None, strategy=None, telegram=None):
        self.cfg = cfg
        os.makedirs(cfg.state_dir, exist_ok=True)
        self.state_path = os.path.join(cfg.state_dir, "state.json")
        self.trades_path = os.path.join(cfg.state_dir, "trades.csv")
        self.state = self._load_state()

        self.ex = exchange or self._make_exchange()
        self.broker = (PaperBroker(cfg, os.path.join(cfg.state_dir, "paper_balance.json"))
                       if cfg.mode == "PAPER" else ExchangeBroker(cfg, self.ex))
        if strategy is None:
            from .strategy import KronosStrategy
            strategy = KronosStrategy(cfg)
        self.strategy = strategy
        self.tg = telegram or Telegram(cfg.telegram_token, cfg.telegram_chat_id)
        self.step = pd.Timedelta(seconds=int(self.ex.parse_timeframe(cfg.timeframe)))

    # ---------- setup ----------
    def _make_exchange(self):
        klass = getattr(ccxt, self.cfg.exchange)
        params = {"enableRateLimit": True}
        if self.cfg.mode != "PAPER":
            params.update(apiKey=self.cfg.api_key, secret=self.cfg.api_secret)
        ex = klass(params)
        if self.cfg.mode == "TESTNET":
            ex.set_sandbox_mode(True)
        ex.load_markets()
        return ex

    def _load_state(self):
        if os.path.exists(self.state_path):
            with open(self.state_path) as f:
                return json.load(f)
        return {"paused": False, "start_equity": None, "last_candle": None, "last_note": ""}

    def _save_state(self):
        with open(self.state_path, "w") as f:
            json.dump(self.state, f, indent=2)

    # ---------- market data ----------
    def closed_candles(self):
        raw = self.ex.fetch_ohlcv(self.cfg.symbol, self.cfg.timeframe, limit=self.cfg.lookback + 2)
        df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
        df["timestamps"] = pd.to_datetime(df["ts"], unit="ms")
        df = df[df["timestamps"] + self.step <= self.now()]           # drop the still-forming candle
        df["amount"] = df["volume"] * df["close"]                # approx. quote volume
        return df.tail(self.cfg.lookback).reset_index(drop=True)

    @staticmethod
    def now():
        return pd.Timestamp.now(tz="UTC").tz_localize(None)

    def price(self):
        return float(self.ex.fetch_ticker(self.cfg.symbol)["last"])

    def equity(self, price):
        base, quote = self.broker.balances()
        return base, quote, quote + base * price

    # ---------- commands ----------
    def status_text(self):
        try:
            p = self.price()
            base, quote, eq = self.equity(p)
            start = self.state.get("start_equity") or eq
            b, q = self.cfg.symbol.split("/")
            return (f"[{self.cfg.mode}] {self.cfg.symbol} {self.cfg.timeframe}\n"
                    f"Cena: {p:,.2f}\nZůstatek: {base:.6f} {b} + {quote:,.2f} {q}\n"
                    f"Celkem: {eq:,.2f} ({(eq/start-1)*100:+.2f} % od startu)\n"
                    f"Stav: {'POZASTAVEN' if self.state['paused'] else 'běží'}\n"
                    f"Poslední rozhodnutí: {self.state.get('last_note') or '—'}")
        except Exception as e:
            return f"Chyba při zjišťování stavu: {e}"

    def pause(self):
        self.state["paused"] = True
        self._save_state()
        return "⏸ Bot pozastaven. Otevřené pozice zůstávají. Pokračovat: /resume"

    def resume(self):
        self.state["paused"] = False
        self._save_state()
        return "▶️ Bot znovu běží."

    def sell_all(self):
        p = self.price()
        base, _, _ = self.equity(p)
        if base * p < MIN_ORDER_QUOTE:
            return "Žádná pozice k prodeji."
        amount, avg = self.broker.sell(base, p)
        self._log_trade("SELL", amount, avg, "ruční /sellall")
        self.state["paused"] = True
        self._save_state()
        return f"Prodáno {amount:.6f} za {avg:,.2f}. Bot pozastaven (/resume)."

    # ---------- core ----------
    def _log_trade(self, side, amount, price, reason):
        new = not os.path.exists(self.trades_path)
        with open(self.trades_path, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time_utc", "mode", "symbol", "side", "amount", "price", "value", "reason"])
            w.writerow([dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"), self.cfg.mode, self.cfg.symbol,
                        side, f"{amount:.8f}", f"{price:.2f}", f"{amount*price:.2f}", reason])

    def tick(self):
        """One decision on the latest closed candle. Returns a summary string (or None if nothing to do)."""
        df = self.closed_candles()
        last = str(df["timestamps"].iloc[-1])
        if last == self.state.get("last_candle"):
            return None
        idx = int(df["ts"].iloc[-1] // (self.step.total_seconds() * 1000))
        if (idx + 1) % self.cfg.horizon != 0:     # decide only every `horizon` candles
            self.state["last_candle"] = last
            self._save_state()
            return None

        p = self.price()
        base, quote, eq = self.equity(p)
        if self.state.get("start_equity") is None:
            self.state["start_equity"] = eq
        self.state["last_candle"] = last

        if eq < self.state["start_equity"] * (1 - self.cfg.max_drawdown) and not self.state["paused"]:
            self.state["paused"] = True
            self._save_state()
            return (f"🛑 Ztráta překročila limit {self.cfg.max_drawdown*100:.0f} % "
                    f"({eq:,.2f} z {self.state['start_equity']:,.2f}). Bot pozastaven, pozice ponechány. "
                    f"Zkontroluj a pokračuj /resume, nebo vše prodej /sellall.")
        if self.state["paused"]:
            self._save_state()
            return None

        want_long, note = self.strategy.decide(df, self.step)
        in_pos = base * p >= MIN_ORDER_QUOTE
        action = "drží" if in_pos else "čeká v hotovosti"
        if want_long and not in_pos and quote * self.cfg.position_fraction >= MIN_ORDER_QUOTE:
            amount, avg = self.broker.buy(quote * self.cfg.position_fraction, p)
            self._log_trade("BUY", amount, avg, note)
            action = f"🟢 KOUPIL {amount:.6f} za {avg:,.2f}"
        elif not want_long and in_pos:
            amount, avg = self.broker.sell(base, p)
            self._log_trade("SELL", amount, avg, note)
            action = f"🔴 PRODAL {amount:.6f} za {avg:,.2f}"

        self.state["last_note"] = f"{last}: {note} → {action}"
        self._save_state()
        _, _, eq = self.equity(p)
        return (f"[{self.cfg.mode}] {self.cfg.symbol} svíčka {last}\n{note}\n{action}\n"
                f"Celkem: {eq:,.2f} ({(eq/self.state['start_equity']-1)*100:+.2f} % od startu)")

    def run(self):
        self.tg.listen({
            "/status": self.status_text, "/pause": self.pause, "/stop": self.pause,
            "/resume": self.resume, "/sellall": self.sell_all,
            "/help": lambda: "Příkazy: /status /pause /resume /sellall",
        })
        self.tg.send(f"🤖 Bot spuštěn v režimu {self.cfg.mode}: {self.cfg.symbol} {self.cfg.timeframe}, "
                     f"strategie {self.strategy.name}.\n" + self.status_text())
        errors = 0
        while True:
            try:
                msg = self.tick()
                if msg:
                    self.tg.send(msg)
                errors = 0
            except Exception as e:
                errors += 1
                log.exception("tick failed")
                if errors in (1, 5) or errors % 30 == 0:
                    self.tg.send(f"⚠️ Chyba ({errors}×): {type(e).__name__}: {e}")
            time.sleep(60)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    Bot(Config.from_env()).run()


if __name__ == "__main__":
    main()
