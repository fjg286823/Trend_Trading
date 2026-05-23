from __future__ import annotations

import unittest

import pandas as pd

from trend_trade.engine.backtest import BacktestEngine
from trend_trade.data.providers import eastmoney_fqt, eastmoney_secid


def make_synthetic_bars() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=180, freq="D")
    prices = []
    price = 10.0
    for i in range(len(dates)):
        if i < 70:
            price += 0.01
        elif i < 130:
            price += 0.18
        else:
            price -= 0.25
        prices.append(max(price, 1.0))
    df = pd.DataFrame({"date": dates, "close": prices})
    df["open"] = df["close"].shift(1).fillna(df["close"]) * 0.995
    df["high"] = df["close"] * 1.01
    df["low"] = df["close"] * 0.99
    df["volume"] = 1_000_000
    df["amount"] = df["close"] * df["volume"]
    return df[["date", "open", "high", "low", "close", "volume", "amount"]]


class BacktestEngineTest(unittest.TestCase):
    def test_eastmoney_helpers(self) -> None:
        self.assertEqual(eastmoney_secid("600519", "stock"), "1.600519")
        self.assertEqual(eastmoney_secid("000001", "stock"), "0.000001")
        self.assertEqual(eastmoney_secid("510300", "etf"), "1.510300")
        self.assertEqual(eastmoney_secid("159915", "etf"), "0.159915")
        self.assertEqual(eastmoney_fqt("qfq"), "1")
        self.assertEqual(eastmoney_fqt("hfq"), "2")

    def test_baseline_strategy_runs(self) -> None:
        broker_config = {
            "initial_cash": 100000,
            "commission_rate": 0.0003,
            "min_commission": 5,
            "stamp_tax_rate": 0.0005,
            "slippage_rate": 0.0005,
        }
        strategy_config = {
            "benchmark_ma_window": 60,
            "fast_ma_window": 20,
            "trend_ma_window": 60,
            "entry_window": 55,
            "exit_window": 20,
            "atr_window": 20,
            "atr_stop_multiple": 2.0,
            "atr_add_multiple": 1.0,
            "risk_per_trade": 0.01,
            "max_adds": 3,
            "lot_size": 100,
            "use_volume_filter": True,
        }
        result = BacktestEngine(broker_config, strategy_config).run("TEST", make_synthetic_bars())
        self.assertFalse(result.bars.empty)
        self.assertFalse(result.equity_curve.empty)
        self.assertIn("total_return", result.metrics)
        self.assertGreaterEqual(len(result.trades), 1)


if __name__ == "__main__":
    unittest.main()
