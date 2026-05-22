from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trend_trade.engine.models import Position
from trend_trade.strategy.indicators import add_trend_indicators, moving_average


@dataclass
class StrategyDecision:
    action: str
    reason: str
    stop_price: float | None = None
    next_add_price: float | None = None


class TrendStrategy:
    """Baseline long-only trend following strategy.

    Rules:
    - Market filter: benchmark above MA and fast MA rising.
    - Entry: close breaks prior N-day high.
    - Stop: entry minus ATR multiple.
    - Add: every configured ATR move in favor, up to max_adds.
    - Exit: close below prior N-day low, trailing stop, or trend MA.
    """

    def __init__(self, params: dict) -> None:
        self.params = params

    def prepare(self, bars: pd.DataFrame, benchmark: pd.DataFrame | None = None) -> pd.DataFrame:
        p = self.params
        df = add_trend_indicators(
            bars,
            fast_ma_window=int(p["fast_ma_window"]),
            trend_ma_window=int(p["trend_ma_window"]),
            entry_window=int(p["entry_window"]),
            exit_window=int(p["exit_window"]),
            atr_window=int(p["atr_window"]),
        )
        df["benchmark_ok"] = True
        if benchmark is not None and not benchmark.empty:
            bm = benchmark[["date", "close"]].copy()
            bm["benchmark_ma"] = moving_average(bm["close"], int(p["benchmark_ma_window"]))
            bm["benchmark_fast_ma"] = moving_average(bm["close"], int(p["fast_ma_window"]))
            bm["benchmark_ok"] = (bm["close"] > bm["benchmark_ma"]) & (
                bm["benchmark_fast_ma"] > bm["benchmark_fast_ma"].shift(1)
            )
            df = df.merge(bm[["date", "benchmark_ok"]], on="date", how="left", suffixes=("", "_bm"))
            if "benchmark_ok_bm" in df:
                df["benchmark_ok"] = df["benchmark_ok_bm"].ffill().fillna(False)
                df = df.drop(columns=["benchmark_ok_bm"])
        return df

    def decide(self, row: pd.Series, position: Position | None) -> StrategyDecision:
        if not self._has_required_values(row):
            return StrategyDecision("HOLD", "指标不足")
        if position is None:
            return self._entry_decision(row)
        return self._position_decision(row, position)

    def _has_required_values(self, row: pd.Series) -> bool:
        required = ["close", "atr", "entry_high", "exit_low", "ma_fast", "ma_trend"]
        return all(pd.notna(row.get(col)) for col in required)

    def _entry_decision(self, row: pd.Series) -> StrategyDecision:
        p = self.params
        volume_ok = True
        if p.get("use_volume_filter", True):
            volume_ok = pd.notna(row.get("volume_ma20")) and row["volume"] >= row["volume_ma20"]
        trend_ok = row["close"] > row["ma_trend"] and row["ma_fast"] >= row["ma_trend"]
        breakout_ok = row["close"] > row["entry_high"]
        market_ok = bool(row.get("benchmark_ok", True))
        if market_ok and trend_ok and volume_ok and breakout_ok:
            stop_price = row["close"] - float(p["atr_stop_multiple"]) * row["atr"]
            next_add_price = row["close"] + float(p["atr_add_multiple"]) * row["atr"]
            return StrategyDecision("BUY", "突破N日高点", stop_price, next_add_price)
        return StrategyDecision("HOLD", "无入场信号")

    def _position_decision(self, row: pd.Series, position: Position) -> StrategyDecision:
        p = self.params
        atr_stop = row["close"] - float(p["atr_stop_multiple"]) * row["atr"]
        trailing_stop = max(position.stop_price, atr_stop, row["exit_low"])
        position.stop_price = trailing_stop
        exit_reasons = []
        if row["close"] <= position.stop_price:
            exit_reasons.append("跌破移动止损")
        if row["close"] < row["exit_low"]:
            exit_reasons.append("跌破N日低点")
        if row["close"] < row["ma_trend"]:
            exit_reasons.append("跌破趋势均线")
        if exit_reasons:
            return StrategyDecision("SELL", "；".join(exit_reasons), trailing_stop, None)

        market_ok = bool(row.get("benchmark_ok", True))
        can_add = position.adds < int(p["max_adds"])
        next_add = position.next_add_price
        if market_ok and can_add and next_add is not None and row["close"] >= next_add:
            new_next = row["close"] + float(p["atr_add_multiple"]) * row["atr"]
            return StrategyDecision("ADD", "浮盈达到加仓间隔", trailing_stop, new_next)
        return StrategyDecision("HOLD", "持仓")
