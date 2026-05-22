from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def make_candlestick_chart(df: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=df["date"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="K线",
        )
    )
    if "ma_fast" in df:
        fig.add_trace(go.Scatter(x=df["date"], y=df["ma_fast"], mode="lines", name="MA Fast", line={"width": 1.2}))
    if "ma_trend" in df:
        fig.add_trace(go.Scatter(x=df["date"], y=df["ma_trend"], mode="lines", name="MA Trend", line={"width": 1.2}))

    markers = {
        "BUY": {"symbol": "triangle-up", "color": "#16a34a", "name": "买入"},
        "ADD": {"symbol": "circle", "color": "#2563eb", "name": "加仓"},
        "SELL": {"symbol": "triangle-down", "color": "#dc2626", "name": "卖出"},
    }
    if "signal" in df:
        for signal, style in markers.items():
            points = df[df["signal"] == signal]
            if not points.empty:
                fig.add_trace(
                    go.Scatter(
                        x=points["date"],
                        y=points["trade_price"].fillna(points["close"]),
                        mode="markers",
                        marker={"symbol": style["symbol"], "size": 12, "color": style["color"]},
                        name=style["name"],
                    )
                )

    fig.update_layout(
        title=title,
        height=650,
        xaxis_rangeslider_visible=False,
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    )
    return fig


def make_equity_chart(equity_curve: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity_curve["date"], y=equity_curve["equity"], mode="lines", name="账户权益"))
    fig.update_layout(
        title="资金曲线",
        height=360,
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
        yaxis_title="权益",
    )
    return fig
