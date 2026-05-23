from __future__ import annotations

import pandas as pd


def moving_average(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def atr(df: pd.DataFrame, window: int = 20) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window=window, min_periods=window).mean()


def add_trend_indicators(
    df: pd.DataFrame,
    fast_ma_window: int,
    trend_ma_window: int,
    entry_window: int,
    exit_window: int,
    atr_window: int,
) -> pd.DataFrame:
    out = df.copy()
    out["ma5"] = moving_average(out["close"], 5)
    out["ma10"] = moving_average(out["close"], 10)
    out["ma20"] = moving_average(out["close"], 20)
    out["ma60"] = moving_average(out["close"], 60)
    out["ma_fast"] = moving_average(out["close"], fast_ma_window)
    out["ma_trend"] = moving_average(out["close"], trend_ma_window)
    out["entry_high"] = out["high"].rolling(entry_window, min_periods=entry_window).max().shift(1)
    out["exit_low"] = out["low"].rolling(exit_window, min_periods=exit_window).min().shift(1)
    out["atr"] = atr(out, atr_window)
    out["volume_ma20"] = moving_average(out["volume"], 20)
    return out
