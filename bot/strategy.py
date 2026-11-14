"""Trading strategies. A strategy turns closed candles into a target position (True = hold coin)."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class KronosStrategy:
    """Long when Kronos predicts the close `horizon` candles ahead to be > threshold above the last close."""

    name = "kronos"

    def __init__(self, cfg):
        import torch
        from model import Kronos, KronosPredictor, KronosTokenizer

        torch.set_num_threads(max(1, os.cpu_count() or 1))
        tok = KronosTokenizer.from_pretrained(cfg.tokenizer)
        mdl = Kronos.from_pretrained(cfg.model)
        self.predictor = KronosPredictor(mdl, tok, device="cpu", max_context=512)
        self.cfg = cfg

    def predicted_return(self, df: pd.DataFrame, step: pd.Timedelta) -> float:
        x = df.iloc[-self.cfg.lookback:].reset_index(drop=True)
        y_ts = pd.Series(x["timestamps"].iloc[-1] + step * np.arange(1, self.cfg.horizon + 1))
        pred = self.predictor.predict(
            df=x[["open", "high", "low", "close", "volume", "amount"]],
            x_timestamp=x["timestamps"], y_timestamp=y_ts,
            pred_len=self.cfg.horizon, T=1.0, top_p=0.9,
            sample_count=self.cfg.samples, verbose=False,
        )
        return float(pred["close"].iloc[-1]) / float(x["close"].iloc[-1]) - 1

    def decide(self, df, step):
        r = self.predicted_return(df, step)
        return r > self.cfg.threshold, f"Kronos předpověď {r*100:+.2f} % (hranice {self.cfg.threshold*100:.1f} %)"
