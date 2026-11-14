"""Offline tests of the trading bot logic with a fake exchange and fake strategy."""
import os

import pandas as pd
import pytest

from bot.config import Config
from bot.main import Bot

DAY_MS = 86_400_000


class FakeExchange:
    def __init__(self, n=300, price=100.0):
        self.price = price
        now = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
        start = int((now - pd.Timedelta(days=n)).timestamp() * 1000)
        self.clock = pd.Timestamp.now(tz="UTC").tz_localize(None)
        self.ohlcv = [[start + i * DAY_MS, price, price, price, price, 1.0] for i in range(n + 1)]  # last = forming

    def parse_timeframe(self, tf):
        return 86400

    def fetch_ohlcv(self, symbol, tf, limit):
        return self.ohlcv[-limit:]

    def fetch_ticker(self, symbol):
        return {"last": self.price}

    def new_candle(self):
        """Simulate one day passing: the forming candle closes and a new one starts."""
        last = self.ohlcv[-1][0]
        self.ohlcv.append([last + DAY_MS, self.price, self.price, self.price, self.price, 1.0])
        self.clock += pd.Timedelta(days=1)


class FakeStrategy:
    name = "fake"

    def __init__(self):
        self.long = True

    def decide(self, df, step):
        assert len(df) == 256
        return self.long, f"fake {'long' if self.long else 'flat'}"


class SilentTelegram:
    def __init__(self):
        self.sent = []

    def send(self, t):
        self.sent.append(t)

    def listen(self, h):
        pass


@pytest.fixture
def bot(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.setenv("MODE", "PAPER")
    for k in ("HORIZON", "THRESHOLD", "LOOKBACK"):
        monkeypatch.delenv(k, raising=False)
    cfg = Config.from_env()
    ex = FakeExchange()
    b = Bot(cfg, exchange=ex, strategy=FakeStrategy(), telegram=SilentTelegram())
    b.now = lambda: ex.clock
    return b


def test_buy_then_hold_then_sell(bot):
    msg = bot.tick()
    assert "KOUPIL" in msg
    base, quote = bot.broker.balances()
    assert base > 0 and quote == pytest.approx(50.0)  # 95 % of 1000 spent
    assert bot.tick() is None                          # same candle -> no new decision
    bot.ex.new_candle()
    assert "drží" in bot.tick()
    bot.strategy.long = False
    bot.ex.new_candle()
    assert "PRODAL" in bot.tick()
    assert bot.broker.balances()[0] == 0
    rows = open(os.path.join(bot.cfg.state_dir, "trades.csv")).read().splitlines()
    assert len(rows) == 3  # header + buy + sell


def test_drawdown_pauses(bot):
    bot.tick()
    bot.ex.price = 50.0  # -50 %
    bot.ex.new_candle()
    assert "limit" in bot.tick()
    assert bot.state["paused"]
    bot.ex.new_candle()
    assert bot.tick() is None  # paused: no trading


def test_live_requires_confirmation(monkeypatch):
    monkeypatch.setenv("MODE", "LIVE")
    monkeypatch.setenv("API_KEY", "x")
    monkeypatch.setenv("API_SECRET", "y")
    monkeypatch.delenv("I_UNDERSTAND_LIVE_TRADING_RISK", raising=False)
    with pytest.raises(ValueError):
        Config.from_env()


def test_sellall_and_pause_commands(bot):
    bot.tick()
    assert "Prodáno" in bot.sell_all()
    assert bot.state["paused"]
    assert "běží" in bot.resume()
