from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
import os
import time

import pandas as pd
import requests

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


@contextmanager
def without_proxy_env():
    proxy_keys = [
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "all_proxy",
        "ALL_PROXY",
    ]
    original = {key: os.environ.get(key) for key in proxy_keys}
    try:
        for key in proxy_keys:
            os.environ.pop(key, None)
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def eastmoney_secid(symbol: str, asset_type: str) -> str:
    if asset_type == "index":
        market = "1" if symbol.startswith("000") else "0"
        return f"{market}.{symbol}"
    if symbol.startswith(("5", "6", "9")):
        return f"1.{symbol}"
    return f"0.{symbol}"


def eastmoney_fqt(adjust: str) -> str:
    if adjust == "qfq":
        return "1"
    if adjust == "hfq":
        return "2"
    return "0"


def market_prefix(symbol: str) -> str:
    return "sh" if symbol.startswith(("5", "6", "9", "000")) else "sz"


class EastmoneyDirectProvider:
    """Daily Eastmoney K-line fetcher that ignores broken system proxies.

    AKShare internally calls the same Eastmoney endpoint for many A-share and ETF
    series, but it uses the default requests proxy environment. In some desktop
    setups a stale local proxy causes ProxyError. This provider uses a local
    requests.Session with trust_env=False, then AKShare remains available as a
    fallback.
    """

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

    def __init__(self, adjust: str = "qfq", retries: int = 2, timeout: int = 12) -> None:
        self.adjust = adjust
        self.retries = retries
        self.timeout = timeout

    def load(self, symbol: str, asset_type: str, start_date: str, end_date: str) -> pd.DataFrame:
        start = pd.to_datetime(start_date).strftime("%Y%m%d")
        end = pd.to_datetime(end_date).strftime("%Y%m%d")
        params = {
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116",
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "klt": "101",
            "fqt": eastmoney_fqt(self.adjust if asset_type != "index" else ""),
            "secid": eastmoney_secid(symbol, asset_type),
            "beg": start,
            "end": end,
        }
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
            "Accept": "application/json,text/plain,*/*",
        }
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                session = requests.Session()
                session.trust_env = False
                response = session.get(self.url, params=params, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                payload = response.json()
                data = payload.get("data") or {}
                klines = data.get("klines") or []
                if not klines:
                    raise ValueError(f"东方财富没有返回 {symbol} 的日线数据")
                rows = []
                for item in klines:
                    parts = item.split(",")
                    if len(parts) < 7:
                        continue
                    rows.append(
                        {
                            "date": parts[0],
                            "open": parts[1],
                            "close": parts[2],
                            "high": parts[3],
                            "low": parts[4],
                            "volume": parts[5],
                            "amount": parts[6],
                        }
                    )
                return normalize_bars(pd.DataFrame(rows))
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.4 * (attempt + 1))
        raise RuntimeError(f"东方财富直连失败：{last_error}") from last_error


class TencentDirectProvider:
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    def __init__(self, adjust: str = "qfq", timeout: int = 12) -> None:
        self.adjust = adjust
        self.timeout = timeout

    def load(self, symbol: str, asset_type: str, start_date: str, end_date: str) -> pd.DataFrame:
        if asset_type == "index":
            raise NotImplementedError("Tencent fallback is only used for stocks and ETFs.")
        prefix = market_prefix(symbol)
        key = f"{prefix}{symbol}"
        adjust_key = "qfqday" if self.adjust == "qfq" else "hfqday" if self.adjust == "hfq" else "day"
        start = pd.to_datetime(start_date).strftime("%Y-%m-%d")
        end = pd.to_datetime(end_date).strftime("%Y-%m-%d")
        params = {"param": f"{key},day,{start},{end},1000,{self.adjust if self.adjust in {'qfq', 'hfq'} else ''}"}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}
        session = requests.Session()
        session.trust_env = False
        response = session.get(self.url, params=params, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        item = (payload.get("data") or {}).get(key) or {}
        klines = item.get(adjust_key) or item.get("day") or []
        if not klines:
            raise ValueError(f"腾讯行情没有返回 {symbol} 的日线数据")
        rows = []
        for parts in klines:
            if len(parts) < 6:
                continue
            # date, open, close, high, low, volume
            rows.append(
                {
                    "date": parts[0],
                    "open": parts[1],
                    "close": parts[2],
                    "high": parts[3],
                    "low": parts[4],
                    "volume": parts[5],
                    "amount": 0.0,
                }
            )
        return normalize_bars(pd.DataFrame(rows))


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

        api_start = pd.to_datetime(start_date).strftime("%Y%m%d")
        api_end = pd.to_datetime(end_date).strftime("%Y%m%d")
        direct_errors = []
        if asset_type in {"etf", "stock", "index"}:
            try:
                bars = EastmoneyDirectProvider(adjust=self.adjust).load(symbol, asset_type, start_date, end_date)
                if self.store:
                    self.store.save_bars(bars, symbol, asset_type, timeframe)
                return bars
            except Exception as direct_exc:
                direct_errors.append(f"东方财富：{direct_exc}")
        if asset_type in {"etf", "stock"}:
            try:
                bars = TencentDirectProvider(adjust=self.adjust).load(symbol, asset_type, start_date, end_date)
                if self.store:
                    self.store.save_bars(bars, symbol, asset_type, timeframe)
                return bars
            except Exception as tencent_exc:
                direct_errors.append(f"腾讯行情：{tencent_exc}")
        else:
            direct_errors = direct_errors

        try:
            import akshare as ak
        except Exception as exc:
            raise RuntimeError("AKShare is not installed. Install dependencies from requirements.txt.") from exc

        try:
            with without_proxy_env():
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
        except Exception as akshare_exc:
            if direct_errors:
                raise RuntimeError(f"行情下载失败。{'; '.join(direct_errors)}；AKShare：{akshare_exc}") from akshare_exc
            raise

        bars = normalize_bars(raw)
        if bars.empty and direct_errors:
            raise RuntimeError(f"数据源返回空数据；{'; '.join(direct_errors)}")
        if self.store:
            self.store.save_bars(bars, symbol, asset_type, timeframe)
        return bars
