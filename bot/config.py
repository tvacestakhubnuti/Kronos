"""Bot configuration, read from environment variables (see .env.example)."""
import os
from dataclasses import dataclass


def _bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    mode: str                 # PAPER | TESTNET | LIVE
    exchange: str
    symbol: str
    timeframe: str
    horizon: int              # candles predicted ahead; a decision is made every `horizon` candles
    threshold: float          # buy only if predicted return > threshold (0.01 = 1 %)
    position_fraction: float  # share of quote balance used for one buy
    max_drawdown: float       # pause bot if equity falls this much below start equity
    paper_start_balance: float
    model: str
    tokenizer: str
    lookback: int
    samples: int
    api_key: str
    api_secret: str
    telegram_token: str
    telegram_chat_id: str
    state_dir: str
    live_confirm: bool

    @classmethod
    def from_env(cls):
        cfg = cls(
            mode=os.environ.get("MODE", "PAPER").upper(),
            exchange=os.environ.get("EXCHANGE", "binance").lower(),
            symbol=os.environ.get("SYMBOL", "BTC/USDT"),
            timeframe=os.environ.get("TIMEFRAME", "1d"),
            horizon=int(os.environ.get("HORIZON", "1")),
            threshold=float(os.environ.get("THRESHOLD", "0.01")),
            position_fraction=float(os.environ.get("POSITION_FRACTION", "0.95")),
            max_drawdown=float(os.environ.get("MAX_DRAWDOWN", "0.20")),
            paper_start_balance=float(os.environ.get("PAPER_START_BALANCE", "1000")),
            model=os.environ.get("KRONOS_MODEL", "NeoQuasar/Kronos-small"),
            tokenizer=os.environ.get("KRONOS_TOKENIZER", "NeoQuasar/Kronos-Tokenizer-base"),
            lookback=int(os.environ.get("LOOKBACK", "256")),
            samples=int(os.environ.get("SAMPLES", "5")),
            api_key=os.environ.get("API_KEY", ""),
            api_secret=os.environ.get("API_SECRET", ""),
            telegram_token=os.environ.get("TELEGRAM_TOKEN", ""),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
            state_dir=os.environ.get("STATE_DIR", "./state"),
            live_confirm=_bool("I_UNDERSTAND_LIVE_TRADING_RISK", False),
        )
        cfg.validate()
        return cfg

    def validate(self):
        if self.mode not in ("PAPER", "TESTNET", "LIVE"):
            raise ValueError("MODE must be PAPER, TESTNET or LIVE")
        if self.mode in ("TESTNET", "LIVE") and not (self.api_key and self.api_secret):
            raise ValueError(f"MODE={self.mode} needs API_KEY and API_SECRET")
        if self.mode == "TESTNET" and self.exchange != "binance":
            raise ValueError("TESTNET mode is supported only for EXCHANGE=binance")
        if self.mode == "LIVE" and not self.live_confirm:
            raise ValueError("LIVE mode requires I_UNDERSTAND_LIVE_TRADING_RISK=true")
        if not 0 < self.position_fraction <= 1:
            raise ValueError("POSITION_FRACTION must be in (0, 1]")
        if not 0 < self.max_drawdown < 1:
            raise ValueError("MAX_DRAWDOWN must be in (0, 1)")
        if self.horizon < 1 or self.lookback < 32:
            raise ValueError("HORIZON must be >= 1 and LOOKBACK >= 32")
