from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


BAR_COLUMNS = ["symbol", "asset_type", "timeframe", "date", "open", "high", "low", "close", "volume", "amount"]


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bars (
                    symbol TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    amount REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (symbol, asset_type, timeframe, date)
                )
                """
            )

    def save_bars(self, df: pd.DataFrame, symbol: str, asset_type: str, timeframe: str = "1d") -> None:
        if df.empty:
            return
        bars = df.copy()
        bars["symbol"] = symbol
        bars["asset_type"] = asset_type
        bars["timeframe"] = timeframe
        bars["date"] = pd.to_datetime(bars["date"]).dt.strftime("%Y-%m-%d")
        if "amount" not in bars:
            bars["amount"] = 0.0
        bars = bars[BAR_COLUMNS]
        records = list(bars.itertuples(index=False, name=None))
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO bars
                (symbol, asset_type, timeframe, date, open, high, low, close, volume, amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records,
            )

    def load_bars(
        self,
        symbol: str,
        asset_type: str,
        start_date: str,
        end_date: str,
        timeframe: str = "1d",
    ) -> pd.DataFrame:
        with self._connect() as conn:
            df = pd.read_sql_query(
                """
                SELECT date, open, high, low, close, volume, amount
                FROM bars
                WHERE symbol = ? AND asset_type = ? AND timeframe = ?
                  AND date >= ? AND date <= ?
                ORDER BY date
                """,
                conn,
                params=(symbol, asset_type, timeframe, start_date, end_date),
            )
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"])
        return df
