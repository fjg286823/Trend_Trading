from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from trend_trade.engine.broker import MockBroker
from trend_trade.strategy.trend_strategy import TrendStrategy


@dataclass
class BacktestResult:
    bars: pd.DataFrame
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    metrics: dict[str, float]


class BacktestEngine:
    def __init__(self, broker_config: dict, strategy_config: dict) -> None:
        self.broker_config = broker_config
        self.strategy_config = strategy_config

    def run(
        self,
        symbol: str,
        bars: pd.DataFrame,
        benchmark: pd.DataFrame | None = None,
    ) -> BacktestResult:
        broker = MockBroker(
            initial_cash=float(self.broker_config["initial_cash"]),
            commission_rate=float(self.broker_config["commission_rate"]),
            min_commission=float(self.broker_config["min_commission"]),
            stamp_tax_rate=float(self.broker_config["stamp_tax_rate"]),
            slippage_rate=float(self.broker_config["slippage_rate"]),
        )
        strategy = TrendStrategy(self.strategy_config)
        df = strategy.prepare(bars, benchmark)
        df["signal"] = ""
        df["trade_price"] = pd.NA
        df["position_shares"] = 0
        df["equity"] = pd.NA

        equity_rows = []
        for idx, row in df.iterrows():
            date = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")
            close = float(row["close"])
            position = broker.get_position(symbol)
            decision = strategy.decide(row, position)

            if decision.action == "BUY":
                shares = self._position_size(
                    equity=broker.equity({symbol: close}),
                    price=close,
                    stop_price=float(decision.stop_price),
                )
                trade = broker.buy(date, symbol, shares, close, float(decision.stop_price), decision.next_add_price, decision.reason)
                if trade:
                    df.at[idx, "signal"] = "BUY"
                    df.at[idx, "trade_price"] = trade.price

            elif decision.action == "ADD":
                shares = self._position_size(
                    equity=broker.equity({symbol: close}),
                    price=close,
                    stop_price=float(decision.stop_price),
                )
                trade = broker.buy(date, symbol, shares, close, float(decision.stop_price), decision.next_add_price, decision.reason)
                if trade:
                    df.at[idx, "signal"] = "ADD"
                    df.at[idx, "trade_price"] = trade.price

            elif decision.action == "SELL" and position:
                trade = broker.sell(date, symbol, position.shares, close, decision.reason)
                if trade:
                    df.at[idx, "signal"] = "SELL"
                    df.at[idx, "trade_price"] = trade.price

            current_pos = broker.get_position(symbol)
            shares_now = current_pos.shares if current_pos else 0
            equity = broker.equity({symbol: close})
            df.at[idx, "position_shares"] = shares_now
            df.at[idx, "equity"] = equity
            equity_rows.append({"date": row["date"], "equity": equity, "cash": broker.cash, "shares": shares_now})

        trades = pd.DataFrame(broker.trades_as_dicts())
        equity_curve = pd.DataFrame(equity_rows)
        metrics = self._metrics(equity_curve, trades)
        return BacktestResult(df, trades, equity_curve, metrics)

    def _position_size(self, equity: float, price: float, stop_price: float) -> int:
        risk_per_trade = float(self.strategy_config["risk_per_trade"])
        lot_size = int(self.strategy_config.get("lot_size", 100))
        risk_amount = equity * risk_per_trade
        risk_per_share = max(price - stop_price, 0.01)
        shares = int(math.floor(risk_amount / risk_per_share))
        shares = shares - shares % lot_size
        return max(shares, 0)

    def _metrics(self, equity_curve: pd.DataFrame, trades: pd.DataFrame) -> dict[str, float]:
        initial_cash = float(self.broker_config["initial_cash"])
        if equity_curve.empty:
            return {}
        final_equity = float(equity_curve["equity"].iloc[-1])
        ret = final_equity / initial_cash - 1
        curve = equity_curve["equity"].astype(float)
        rolling_peak = curve.cummax()
        drawdown = curve / rolling_peak - 1
        max_drawdown = float(drawdown.min())

        sell_trades = trades[trades["side"] == "SELL"] if not trades.empty else pd.DataFrame()
        trade_count = int(len(sell_trades))
        wins = sell_trades[sell_trades["pnl"] > 0] if not sell_trades.empty else pd.DataFrame()
        losses = sell_trades[sell_trades["pnl"] <= 0] if not sell_trades.empty else pd.DataFrame()
        win_rate = float(len(wins) / trade_count) if trade_count else 0.0
        avg_win = float(wins["pnl"].mean()) if len(wins) else 0.0
        avg_loss = float(losses["pnl"].mean()) if len(losses) else 0.0
        payoff = abs(avg_win / avg_loss) if avg_loss else 0.0
        avg_r = float(sell_trades["r_multiple"].mean()) if trade_count else 0.0

        return {
            "initial_cash": initial_cash,
            "final_equity": final_equity,
            "total_return": float(ret),
            "max_drawdown": max_drawdown,
            "trade_count": float(trade_count),
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "payoff_ratio": payoff,
            "avg_r": avg_r,
        }
