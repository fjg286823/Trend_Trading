from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from trend_trade.config import load_config
from trend_trade.data.providers import AkshareProvider, CSVProvider
from trend_trade.engine.backtest import BacktestEngine
from trend_trade.storage.db import SQLiteStore
from trend_trade.visualization.chart import make_candlestick_chart, make_equity_chart


st.set_page_config(page_title="趋势交易系统", layout="wide")


@st.cache_resource
def get_store(db_path: str) -> SQLiteStore:
    return SQLiteStore(db_path)


@st.cache_data(show_spinner=False)
def load_akshare_data(
    symbol: str,
    asset_type: str,
    start_date: str,
    end_date: str,
    db_path: str,
    adjust: str,
    refresh: bool,
) -> pd.DataFrame:
    provider = AkshareProvider(store=get_store(db_path), adjust=adjust)
    return provider.load(symbol, asset_type, start_date, end_date, refresh=refresh)


@st.cache_data(show_spinner=False)
def load_sample_data() -> pd.DataFrame:
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
        high = max(open_, close) * 1.015
        low = min(open_, close) * 0.985
        volume = 1_000_000 + (i % 30) * 30_000
        rows.append([dt, open_, high, low, close, volume, close * volume])
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])


def fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def main() -> None:
    config = load_config()
    st.title(config["app"]["title"])

    tabs = st.tabs(["行情与K线", "策略回测", "模拟账户", "交易日志"])
    with st.sidebar:
        st.header("数据")
        source = st.radio("数据源", ["示例数据", "AKShare", "CSV"], horizontal=True)
        symbol = st.text_input("标的代码", value=config["app"]["default_symbol"])
        asset_type = st.selectbox("标的类型", ["etf", "stock"], index=0 if config["app"]["default_asset_type"] == "etf" else 1)
        today = date.today()
        start = st.date_input("开始日期", today - timedelta(days=365 * 3))
        end = st.date_input("结束日期", today)
        refresh = st.checkbox("强制刷新AKShare缓存", value=False)
        uploaded = st.file_uploader("上传CSV", type=["csv"]) if source == "CSV" else None

        st.header("策略参数")
        initial_cash = st.number_input("初始资金", min_value=10000, value=int(config["backtest"]["initial_cash"]), step=10000)
        entry_window = st.number_input("突破周期", min_value=10, max_value=250, value=int(config["strategy"]["entry_window"]))
        exit_window = st.number_input("退出周期", min_value=5, max_value=120, value=int(config["strategy"]["exit_window"]))
        atr_stop = st.number_input("ATR止损倍数", min_value=0.5, max_value=10.0, value=float(config["strategy"]["atr_stop_multiple"]), step=0.5)
        risk = st.number_input("单笔风险", min_value=0.001, max_value=0.05, value=float(config["strategy"]["risk_per_trade"]), step=0.001, format="%.3f")
        max_adds = st.number_input("最多加仓次数", min_value=0, max_value=10, value=int(config["strategy"]["max_adds"]))
        use_benchmark = st.checkbox("启用沪深300大盘过滤", value=True)

    bars = None
    error = None
    try:
        if source == "示例数据":
            bars = load_sample_data()
            symbol = "SAMPLE"
        elif source == "AKShare":
            bars = load_akshare_data(
                symbol=symbol,
                asset_type=asset_type,
                start_date=str(start),
                end_date=str(end),
                db_path=config["data"]["sqlite_path"],
                adjust=config["data"]["adjust"],
                refresh=refresh,
            )
        elif uploaded is not None:
            bars = CSVProvider().load(uploaded)
    except Exception as exc:
        error = exc

    if error:
        st.error(f"加载数据失败：{error}")
    if bars is None or bars.empty:
        st.info("请选择示例数据、AKShare 数据源，或上传包含 date/open/high/low/close/volume 的 CSV。")
        return

    strategy_config = dict(config["strategy"])
    strategy_config.update(
        {
            "entry_window": int(entry_window),
            "exit_window": int(exit_window),
            "atr_stop_multiple": float(atr_stop),
            "risk_per_trade": float(risk),
            "max_adds": int(max_adds),
        }
    )
    broker_config = dict(config["backtest"])
    broker_config["initial_cash"] = float(initial_cash)

    benchmark = None
    if use_benchmark and source == "示例数据":
        benchmark = bars.copy()
    elif use_benchmark:
        try:
            benchmark = load_akshare_data(
                symbol=config["app"]["default_benchmark"],
                asset_type="index",
                start_date=str(start),
                end_date=str(end),
                db_path=config["data"]["sqlite_path"],
                adjust="",
                refresh=refresh,
            )
        except Exception as exc:
            st.warning(f"大盘过滤数据加载失败，已跳过过滤：{exc}")

    engine = BacktestEngine(broker_config, strategy_config)
    result = engine.run(symbol, bars, benchmark)

    with tabs[0]:
        st.plotly_chart(make_candlestick_chart(result.bars, f"{symbol} K线与交易信号"), use_container_width=True)
        st.dataframe(result.bars.tail(30), use_container_width=True)

    with tabs[1]:
        m = result.metrics
        cols = st.columns(5)
        cols[0].metric("最终权益", f"{m.get('final_equity', 0):,.2f}")
        cols[1].metric("总收益率", fmt_pct(m.get("total_return", 0)))
        cols[2].metric("最大回撤", fmt_pct(m.get("max_drawdown", 0)))
        cols[3].metric("胜率", fmt_pct(m.get("win_rate", 0)))
        cols[4].metric("交易次数", f"{int(m.get('trade_count', 0))}")
        st.plotly_chart(make_equity_chart(result.equity_curve), use_container_width=True)
        st.subheader("回测指标")
        st.json(m)

    with tabs[2]:
        latest = result.equity_curve.iloc[-1]
        st.metric("虚拟账户权益", f"{latest['equity']:,.2f}")
        st.metric("现金", f"{latest['cash']:,.2f}")
        st.metric("当前持仓股数", f"{int(latest['shares'])}")
        st.caption("第一版模拟账户来自回测逐日撮合结果；后续会扩展为每日增量运行和人工确认模式。")

    with tabs[3]:
        if result.trades.empty:
            st.info("当前参数下没有交易。")
        else:
            st.dataframe(result.trades, use_container_width=True)
            st.download_button(
                "导出交易日志 CSV",
                result.trades.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"{symbol}_trades.csv",
                mime="text/csv",
            )


if __name__ == "__main__":
    main()
