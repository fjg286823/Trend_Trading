from __future__ import annotations

from dataclasses import asdict

from trend_trade.engine.models import Position, Trade


class MockBroker:
    def __init__(
        self,
        initial_cash: float,
        commission_rate: float,
        min_commission: float,
        stamp_tax_rate: float,
        slippage_rate: float,
    ) -> None:
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.stamp_tax_rate = stamp_tax_rate
        self.slippage_rate = slippage_rate
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []

    def equity(self, prices: dict[str, float] | None = None) -> float:
        total = self.cash
        prices = prices or {}
        for symbol, pos in self.positions.items():
            total += pos.shares * prices.get(symbol, pos.avg_price)
        return total

    def get_position(self, symbol: str) -> Position | None:
        return self.positions.get(symbol)

    def _fee(self, side: str, value: float) -> float:
        commission = max(self.min_commission, value * self.commission_rate)
        stamp_tax = value * self.stamp_tax_rate if side == "SELL" else 0.0
        return commission + stamp_tax

    def buy(
        self,
        date: str,
        symbol: str,
        shares: int,
        price: float,
        stop_price: float,
        next_add_price: float | None,
        reason: str,
    ) -> Trade | None:
        if shares <= 0:
            return None
        fill_price = price * (1 + self.slippage_rate)
        value = fill_price * shares
        fee = self._fee("BUY", value)
        total = value + fee
        if total > self.cash:
            shares = int(self.cash // fill_price)
            shares = shares - shares % 100
            if shares <= 0:
                return None
            value = fill_price * shares
            fee = self._fee("BUY", value)
            total = value + fee
        self.cash -= total
        existing = self.positions.get(symbol)
        risk_per_share = max(fill_price - stop_price, 0.01)
        if existing:
            new_shares = existing.shares + shares
            existing.avg_price = (existing.avg_price * existing.shares + fill_price * shares) / new_shares
            existing.shares = new_shares
            existing.stop_price = max(existing.stop_price, stop_price)
            existing.next_add_price = next_add_price
            existing.adds += 1
        else:
            self.positions[symbol] = Position(
                symbol=symbol,
                shares=shares,
                avg_price=fill_price,
                stop_price=stop_price,
                entry_risk_per_share=risk_per_share,
                next_add_price=next_add_price,
            )
        trade = Trade(date, symbol, "BUY", shares, fill_price, value, fee, self.cash, reason)
        self.trades.append(trade)
        return trade

    def sell(self, date: str, symbol: str, shares: int, price: float, reason: str) -> Trade | None:
        pos = self.positions.get(symbol)
        if not pos:
            return None
        shares = min(shares, pos.shares)
        if shares <= 0:
            return None
        fill_price = price * (1 - self.slippage_rate)
        value = fill_price * shares
        fee = self._fee("SELL", value)
        self.cash += value - fee
        pnl = (fill_price - pos.avg_price) * shares - fee
        planned_risk = max(pos.entry_risk_per_share * shares, 0.01)
        r_multiple = pnl / planned_risk
        pos.shares -= shares
        if pos.shares <= 0:
            del self.positions[symbol]
        trade = Trade(date, symbol, "SELL", shares, fill_price, value, fee, self.cash, reason, pnl, r_multiple)
        self.trades.append(trade)
        return trade

    def trades_as_dicts(self) -> list[dict]:
        return [asdict(t) for t in self.trades]
