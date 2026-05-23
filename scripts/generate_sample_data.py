from __future__ import annotations

from pathlib import Path

import pandas as pd


def main() -> None:
    dates = pd.bdate_range("2022-01-03", periods=520)
    price = 10.0
    rows = []
    for i, dt in enumerate(dates):
        if i < 120:
            price += 0.01
        elif i < 260:
            price += 0.08
        elif i < 360:
            price -= 0.04
        else:
            price += 0.05
        wave = 0.15 * ((i % 17) - 8) / 8
        close = max(price + wave, 1.0)
        open_ = close * (0.995 + (i % 5) * 0.002)
        high = max(open_, close) * 1.004
        low = min(open_, close) * 0.996
        volume = 1_000_000 + (i % 30) * 30_000
        if 120 <= i < 260 or i >= 360:
            volume *= 1.35
        rows.append([dt.strftime("%Y-%m-%d"), open_, high, low, close, volume, close * volume])

    path = Path("data/sample_bars.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    out = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])
    out.to_csv(path, index=False)
    print(f"Wrote {path} ({len(out)} rows)")


if __name__ == "__main__":
    main()
