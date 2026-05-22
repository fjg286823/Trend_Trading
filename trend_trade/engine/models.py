from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Position:
    symbol: str
    shares: int
    avg_price: float
    stop_price: float
    entry_risk_per_share: float
    adds: int = 0
    next_add_price: float | None = None


@dataclass
class Trade:
    date: str
    symbol: str
    side: str
    shares: int
    price: float
    value: float
    fee: float
    cash_after: float
    reason: str
    pnl: float = 0.0
    r_multiple: float = 0.0
