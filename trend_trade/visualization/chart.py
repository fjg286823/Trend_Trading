from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def make_candlestick_chart(df: pd.DataFrame, title: str) -> go.Figure:
    chart_df = df.copy()
    chart_df["x_label"] = pd.to_datetime(chart_df["date"]).dt.strftime("%Y-%m-%d")
    chart_df["is_up"] = chart_df["close"] >= chart_df["open"]

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.76, 0.24],
        specs=[[{"secondary_y": False}], [{"secondary_y": False}]],
    )
    fig.add_trace(
        go.Candlestick(
            x=chart_df["x_label"],
            open=chart_df["open"],
            high=chart_df["high"],
            low=chart_df["low"],
            close=chart_df["close"],
            name="K线",
            increasing={"line": {"color": "#d60000", "width": 1}, "fillcolor": "#ffffff"},
            decreasing={"line": {"color": "#008f3a", "width": 1}, "fillcolor": "#008f3a"},
            whiskerwidth=0.4,
        ),
        row=1,
        col=1,
    )
    ma_styles = {
        "ma5": ("MA5", "#f59e0b"),
        "ma10": ("MA10", "#8b5cf6"),
        "ma20": ("MA20", "#2563eb"),
        "ma60": ("MA60", "#111827"),
    }
    for col, (name, color) in ma_styles.items():
        if col in chart_df:
            fig.add_trace(
                go.Scatter(
                    x=chart_df["x_label"],
                    y=chart_df[col],
                    mode="lines",
                    name=name,
                    line={"width": 1.1, "color": color},
                    connectgaps=False,
                ),
                row=1,
                col=1,
            )

    volume_colors = chart_df["is_up"].map({True: "#d60000", False: "#008f3a"})
    fig.add_trace(
        go.Bar(
            x=chart_df["x_label"],
            y=chart_df["volume"],
            name="成交量",
            marker={"color": volume_colors},
            opacity=0.55,
        ),
        row=2,
        col=1,
    )

    markers = {
        "BUY": {"symbol": "triangle-up", "color": "#d60000", "name": "买入"},
        "ADD": {"symbol": "circle", "color": "#2563eb", "name": "加仓"},
        "SELL": {"symbol": "triangle-down", "color": "#008f3a", "name": "卖出"},
    }
    if "signal" in chart_df:
        for signal, style in markers.items():
            points = chart_df[chart_df["signal"] == signal]
            if not points.empty:
                fig.add_trace(
                    go.Scatter(
                        x=points["x_label"],
                        y=points["trade_price"].fillna(points["close"]),
                        mode="markers",
                        marker={
                            "symbol": style["symbol"],
                            "size": 12,
                            "color": style["color"],
                            "line": {"color": "#111827", "width": 0.8},
                        },
                        name=style["name"],
                        hovertemplate="%{x}<br>" + style["name"] + ": %{y:.3f}<extra></extra>",
                    ),
                    row=1,
                    col=1,
                )

    fig.update_layout(
        title=title,
        height=760,
        template="plotly_white",
        xaxis_rangeslider_visible=False,
        margin={"l": 12, "r": 12, "t": 46, "b": 12},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        hovermode="x unified",
        dragmode="pan",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )
    fig.update_xaxes(
        type="category",
        showgrid=True,
        gridcolor="#efefef",
        tickangle=0,
        nticks=12,
        rangeslider_visible=False,
    )
    fig.update_yaxes(showgrid=True, gridcolor="#e5e7eb", zeroline=False, row=1, col=1)
    fig.update_yaxes(showgrid=True, gridcolor="#f1f5f9", zeroline=False, title_text="成交量", row=2, col=1)
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
