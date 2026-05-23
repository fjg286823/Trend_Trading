from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from trend_trade.config import load_config
from trend_trade.data.providers import AkshareProvider, CSVProvider
from trend_trade.engine.backtest import BacktestEngine, BacktestResult
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
def load_sample_data(symbol: str = "SAMPLE") -> pd.DataFrame:
    dates = pd.bdate_range("2022-01-03", periods=520)
    seed = sum(ord(ch) for ch in symbol) % 19
    price = 9.0 + seed * 0.2
    rows = []
    for i, dt in enumerate(dates):
        if i < 120:
            price += 0.006 + seed * 0.0008
        elif i < 260:
            price += 0.065 + seed * 0.0015
        elif i < 360:
            price -= 0.035 + seed * 0.0008
        else:
            price += 0.035 + seed * 0.001
        wave = 0.12 * ((i + seed) % 17 - 8) / 8
        close = max(price + wave, 1.0)
        open_ = close * (0.995 + ((i + seed) % 5) * 0.002)
        high = max(open_, close) * 1.004
        low = min(open_, close) * 0.996
        volume = 1_000_000 + ((i + seed) % 30) * 30_000
        if 120 <= i < 260 or i >= 360:
            volume *= 1.35
        rows.append([dt, open_, high, low, close, volume, close * volume])
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])


def fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def friendly_error(exc: Exception) -> str:
    text = str(exc)
    if "ProxyError" in text or "proxy" in text.lower() or "Unable to connect to proxy" in text:
        return (
            "网络/代理错误：行情接口连接失败。软件会优先禁用系统代理直连东方财富，"
            "如果仍失败，请检查本机代理、VPN、防火墙，或先切换到“示例数据/CSV”。"
        )
    if "东方财富" in text or "AKShare" in text or "行情下载失败" in text:
        return f"行情下载失败：{text}"
    return text


def parse_symbols(text: str) -> list[str]:
    raw = text.replace("，", ",").replace("\n", ",").replace(" ", ",").split(",")
    symbols = []
    for item in raw:
        symbol = item.strip()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols


def guess_asset_type(symbol: str) -> str:
    if symbol.startswith(("5", "1")):
        return "etf"
    return "stock"


def build_configs(config: dict[str, Any], sidebar_values: dict[str, Any]) -> tuple[dict, dict]:
    strategy_config = dict(config["strategy"])
    strategy_config.update(
        {
            "entry_window": int(sidebar_values["entry_window"]),
            "exit_window": int(sidebar_values["exit_window"]),
            "atr_stop_multiple": float(sidebar_values["atr_stop"]),
            "risk_per_trade": float(sidebar_values["risk"]),
            "max_adds": int(sidebar_values["max_adds"]),
            "use_volume_filter": bool(sidebar_values["use_volume_filter"]),
        }
    )
    broker_config = dict(config["backtest"])
    broker_config["initial_cash"] = float(sidebar_values["initial_cash"])
    return broker_config, strategy_config


def load_symbol_bars(
    symbol: str,
    source: str,
    asset_type_mode: str,
    start: date,
    end: date,
    config: dict[str, Any],
    refresh: bool,
    uploaded_file=None,
) -> tuple[pd.DataFrame, str]:
    if source == "示例数据":
        return load_sample_data(symbol), "sample"
    if source == "CSV":
        if uploaded_file is None:
            return pd.DataFrame(), "csv"
        return CSVProvider().load(uploaded_file), "csv"
    asset_type = guess_asset_type(symbol) if asset_type_mode == "自动识别" else asset_type_mode
    bars = load_akshare_data(
        symbol=symbol,
        asset_type=asset_type,
        start_date=str(start),
        end_date=str(end),
        db_path=config["data"]["sqlite_path"],
        adjust=config["data"]["adjust"],
        refresh=refresh,
    )
    return bars, asset_type


def load_benchmark(source: str, start: date, end: date, config: dict[str, Any], refresh: bool, fallback: pd.DataFrame | None) -> pd.DataFrame | None:
    if source == "示例数据":
        return fallback.copy() if fallback is not None else None
    try:
        return load_akshare_data(
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
        return None


def run_one_backtest(
    symbol: str,
    bars: pd.DataFrame,
    benchmark: pd.DataFrame | None,
    broker_config: dict,
    strategy_config: dict,
) -> BacktestResult:
    return BacktestEngine(broker_config, strategy_config).run(symbol, bars, benchmark)


def result_summary(symbol: str, asset_type: str, result: BacktestResult, error: str = "") -> dict[str, Any]:
    if error:
        return {"代码": symbol, "类型": asset_type, "状态": "失败", "错误": error}
    m = result.metrics
    latest_close = float(result.bars["close"].iloc[-1]) if not result.bars.empty else 0.0
    latest_signal = result.bars[result.bars["signal"] != ""].tail(1)
    return {
        "代码": symbol,
        "类型": asset_type,
        "状态": "完成",
        "最终权益": round(m.get("final_equity", 0), 2),
        "收益率": m.get("total_return", 0),
        "最大回撤": m.get("max_drawdown", 0),
        "胜率": m.get("win_rate", 0),
        "交易次数": int(m.get("trade_count", 0)),
        "平均R": round(m.get("avg_r", 0), 3),
        "最新收盘": round(latest_close, 3),
        "最后信号": "" if latest_signal.empty else str(latest_signal["signal"].iloc[-1]),
        "错误": "",
    }


def main() -> None:
    config = load_config()
    st.title("趋势交易系统")
    st.caption("A股/ETF 日线趋势交易研究：行情查看、买卖点可视化、批量策略回测、虚拟资金模拟。")

    with st.sidebar:
        st.header("行情")
        source = st.radio("数据源", ["AKShare", "示例数据", "CSV"], horizontal=True)
        chart_symbol = st.text_input("当前图表代码", value=config["app"]["default_symbol"], help="例如 ETF: 510300；股票: 600519、000001")
        asset_type_mode = st.selectbox("代码类型", ["自动识别", "etf", "stock"], index=0)
        today = date.today()
        start = st.date_input("开始日期", today - timedelta(days=365 * 3))
        end = st.date_input("结束日期", today)
        refresh = st.checkbox("强制刷新AKShare缓存", value=False)
        uploaded = st.file_uploader("上传CSV", type=["csv"]) if source == "CSV" else None

        st.header("回测股票池")
        symbols_text = st.text_area("股票/ETF代码", value=chart_symbol, height=110, help="支持逗号、空格、换行分隔，例如：510300, 159915, 600519")
        use_benchmark = st.checkbox("启用沪深300大盘过滤", value=True)

        st.header("策略参数")
        values = {
            "initial_cash": st.number_input("单标的初始资金", min_value=10000, value=int(config["backtest"]["initial_cash"]), step=10000),
            "entry_window": st.number_input("突破周期", min_value=10, max_value=250, value=int(config["strategy"]["entry_window"])),
            "exit_window": st.number_input("退出周期", min_value=5, max_value=120, value=int(config["strategy"]["exit_window"])),
            "atr_stop": st.number_input("ATR止损倍数", min_value=0.5, max_value=10.0, value=float(config["strategy"]["atr_stop_multiple"]), step=0.5),
            "risk": st.number_input("单笔风险", min_value=0.001, max_value=0.05, value=float(config["strategy"]["risk_per_trade"]), step=0.001, format="%.3f"),
            "max_adds": st.number_input("最多加仓次数", min_value=0, max_value=10, value=int(config["strategy"]["max_adds"])),
            "use_volume_filter": st.checkbox("启用成交量过滤", value=bool(config["strategy"]["use_volume_filter"])),
        }

    broker_config, strategy_config = build_configs(config, values)
    tabs = st.tabs(["行情与买卖点", "策略回测", "单标的明细", "交易日志"])

    chart_bars = pd.DataFrame()
    chart_result: BacktestResult | None = None
    chart_asset_type = ""
    try:
        chart_bars, chart_asset_type = load_symbol_bars(chart_symbol.strip(), source, asset_type_mode, start, end, config, refresh, uploaded)
        benchmark = load_benchmark(source, start, end, config, refresh, chart_bars) if use_benchmark else None
        if not chart_bars.empty:
            chart_result = run_one_backtest(chart_symbol.strip(), chart_bars, benchmark, broker_config, strategy_config)
    except Exception as exc:
        st.error(f"{chart_symbol} 加载或回测失败：{friendly_error(exc)}")

    with tabs[0]:
        if chart_result is None:
            st.info("请输入股票/ETF代码，或切换到示例数据/上传CSV。")
        else:
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("代码", chart_symbol)
            col_b.metric("数据类型", chart_asset_type)
            col_c.metric("最新收盘", f"{chart_result.bars['close'].iloc[-1]:.3f}")
            col_d.metric("交易次数", f"{int(chart_result.metrics.get('trade_count', 0))}")
            st.plotly_chart(make_candlestick_chart(chart_result.bars, f"{chart_symbol} 日K线、均线与买卖点"), use_container_width=True)

    with tabs[1]:
        symbols = parse_symbols(symbols_text)
        run_batch = st.button("运行批量回测", type="primary", use_container_width=False)
        if run_batch:
            summaries = []
            results: dict[str, BacktestResult] = {}
            progress = st.progress(0)
            status = st.empty()
            for i, symbol in enumerate(symbols, start=1):
                status.write(f"正在回测 {symbol} ({i}/{len(symbols)})")
                try:
                    bars, asset_type = load_symbol_bars(symbol, source, asset_type_mode, start, end, config, refresh, uploaded)
                    if bars.empty:
                        raise ValueError("没有行情数据")
                    benchmark = load_benchmark(source, start, end, config, refresh, bars) if use_benchmark else None
                    result = run_one_backtest(symbol, bars, benchmark, broker_config, strategy_config)
                    results[symbol] = result
                    summaries.append(result_summary(symbol, asset_type, result))
                except Exception as exc:
                    summaries.append(result_summary(symbol, guess_asset_type(symbol), None, friendly_error(exc)))  # type: ignore[arg-type]
                progress.progress(i / max(len(symbols), 1))
            st.session_state["batch_results"] = results
            st.session_state["batch_summary"] = pd.DataFrame(summaries)
            status.write("批量回测完成")

        summary = st.session_state.get("batch_summary")
        if summary is None:
            st.info("输入股票池并点击“运行批量回测”。")
        else:
            show = summary.copy()
            for col in ["收益率", "最大回撤", "胜率"]:
                if col in show:
                    show[col] = show[col].map(lambda x: fmt_pct(x) if pd.notna(x) and x != "" else "")
            st.dataframe(show, use_container_width=True, hide_index=True)
            st.download_button(
                "导出回测汇总 CSV",
                summary.to_csv(index=False).encode("utf-8-sig"),
                file_name="backtest_summary.csv",
                mime="text/csv",
            )

    with tabs[2]:
        results = st.session_state.get("batch_results", {})
        choices = list(results.keys())
        if chart_result is not None and chart_symbol not in choices:
            choices = [chart_symbol] + choices
            results = {chart_symbol: chart_result, **results}
        if not choices:
            st.info("先查看单个代码或运行批量回测。")
        else:
            selected = st.selectbox("选择标的查看明细", choices)
            selected_result = results[selected]
            m = selected_result.metrics
            cols = st.columns(6)
            cols[0].metric("最终权益", f"{m.get('final_equity', 0):,.2f}")
            cols[1].metric("总收益率", fmt_pct(m.get("total_return", 0)))
            cols[2].metric("最大回撤", fmt_pct(m.get("max_drawdown", 0)))
            cols[3].metric("胜率", fmt_pct(m.get("win_rate", 0)))
            cols[4].metric("交易次数", f"{int(m.get('trade_count', 0))}")
            cols[5].metric("平均R", f"{m.get('avg_r', 0):.2f}")
            st.plotly_chart(make_candlestick_chart(selected_result.bars, f"{selected} 回测买卖点"), use_container_width=True)
            st.plotly_chart(make_equity_chart(selected_result.equity_curve), use_container_width=True)

    with tabs[3]:
        results = st.session_state.get("batch_results", {})
        log_frames = []
        for symbol, result in results.items():
            if not result.trades.empty:
                frame = result.trades.copy()
                frame.insert(0, "symbol_view", symbol)
                log_frames.append(frame)
        if not log_frames and chart_result is not None and not chart_result.trades.empty:
            frame = chart_result.trades.copy()
            frame.insert(0, "symbol_view", chart_symbol)
            log_frames.append(frame)
        if not log_frames:
            st.info("暂无交易记录。")
        else:
            trades = pd.concat(log_frames, ignore_index=True)
            st.dataframe(trades, use_container_width=True)
            st.download_button(
                "导出交易日志 CSV",
                trades.to_csv(index=False).encode("utf-8-sig"),
                file_name="trade_logs.csv",
                mime="text/csv",
            )


if __name__ == "__main__":
    main()
