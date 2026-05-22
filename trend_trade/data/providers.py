from __future__ import annotations

from pathlib import Path

import pandas as pd

from trend_trade.storage.db import SQLiteStore


CN_COLUMN_MAP = {
    "日期": "date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
    "成交额": "amount",
}


def normalize_bars(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.rename(columns=CN_COLUMN_MAP).copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in out.columns]
    if missing:
        raise ValueError(f"Missing required bar columns: {missing}")
    if "amount" not in out.columns:
        out["amount"] = 0.0
    out = out[["date", "open", "high", "low", "close", "volume", "amount"]].copy()
    out["date"] = pd.to_datetime(out["date"])
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["date", "open", "high", "low", "close", "volume"])
    out = out.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    return out


class CSVProvider:
    def load(self, path: str | Path) -> pd.DataFrame:
        return normalize_bars(pd.read_csv(path))


class AkshareProvider:
    def __init__(self, store: SQLiteStore | None = None, adjust: str = "qfq") -> None:
        self.store = store
        self.adjust = adjust

    def load(
        self,
        symbol: str,
        asset_type: str,
        start_date: str,
        end_date: str,
        timeframe: str = "1d",
        refresh: bool = False,
    ) -> pd.DataFrame:
        if timeframe != "1d":
            raise NotImplementedError("AKShare provider currently supports daily bars only.")
        start = pd.to_datetime(start_date).strftime("%Y-%m-%d")
        end = pd.to_datetime(end_date).strftime("%Y-%m-%d")
        if self.store and not refresh:
            cached = self.store.load_bars(symbol, asset_type, start, end, timeframe)
            if not cached.empty:
                return cached

        try:
            import akshare as ak
        except Exception as exc:
            raise RuntimeError("AKShare is not installed. Install dependencies from requirements.txt.") from exc

        api_start = pd.to_datetime(start_date).strftime("%Y%m%d")
        api_end = pd.to_datetime(end_date).strftime("%Y%m%d")
        if asset_type == "etf":
            raw = ak.fund_etf_hist_em(
                symbol=symbol,
                period="daily",
                start_date=api_start,
                end_date=api_end,
                adjust=self.adjust,
            )
        elif asset_type == "stock":
            raw = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=api_start,
                end_date=api_end,
                adjust=self.adjust,
            )
        elif asset_type == "index":
            index_symbol = symbol
            if symbol.isdigit() and len(symbol) == 6:
                index_symbol = ("sh" if symbol.startswith("000") else "sz") + symbol
            raw = ak.stock_zh_index_daily(symbol=index_symbol)
            raw = normalize_bars(raw)
            raw = raw[(raw["date"] >= pd.to_datetime(start_date)) & (raw["date"] <= pd.to_datetime(end_date))]
            bars = raw.reset_index(drop=True)
            if self.store:
                self.store.save_bars(bars, symbol, asset_type, timeframe)
            return bars
        else:
            raise ValueError(f"Unsupported asset type: {asset_type}")

        bars = normalize_bars(raw)
        if self.store:
            self.store.save_bars(bars, symbol, asset_type, timeframe)
        return bars
