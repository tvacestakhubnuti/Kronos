"""Order execution: PaperBroker (virtual money) and ExchangeBroker (testnet / live via ccxt)."""
import json
import os


class ExchangeBroker:
    def __init__(self, cfg, exchange):
        self.ex, self.symbol = exchange, cfg.symbol
        self.base, self.quote = cfg.symbol.split("/")

    def balances(self):
        b = self.ex.fetch_balance()
        return float(b.get(self.base, {}).get("free") or 0), float(b.get(self.quote, {}).get("free") or 0)

    def buy(self, cost, price):
        o = self.ex.create_market_buy_order_with_cost(self.symbol, float(self.ex.cost_to_precision(self.symbol, cost)))
        return o.get("filled") or cost / price, o.get("average") or price

    def sell(self, amount, price):
        o = self.ex.create_market_sell_order(self.symbol, float(self.ex.amount_to_precision(self.symbol, amount)))
        return o.get("filled") or amount, o.get("average") or price


class PaperBroker:
    """Simulated account with real market prices. Applies a 0.1 % fee per trade."""

    FEE = 0.001

    def __init__(self, cfg, path):
        self.path = path
        if os.path.exists(path):
            with open(path) as f:
                d = json.load(f)
        else:
            d = {"base": 0.0, "quote": cfg.paper_start_balance}
        self.base_bal, self.quote_bal = d["base"], d["quote"]

    def _save(self):
        with open(self.path, "w") as f:
            json.dump({"base": self.base_bal, "quote": self.quote_bal}, f)

    def balances(self):
        return self.base_bal, self.quote_bal

    def buy(self, cost, price):
        cost = min(cost, self.quote_bal)
        amount = cost * (1 - self.FEE) / price
        self.quote_bal -= cost
        self.base_bal += amount
        self._save()
        return amount, price

    def sell(self, amount, price):
        amount = min(amount, self.base_bal)
        self.base_bal -= amount
        self.quote_bal += amount * price * (1 - self.FEE)
        self._save()
        return amount, price
