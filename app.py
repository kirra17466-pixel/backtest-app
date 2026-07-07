# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path

st.set_page_config(page_title="台股策略回測", page_icon="📈", layout="centered")
st.title("📈 台股策略回測工具")
st.caption("資料來源：00631L = 台灣證交所官方 ｜ 0050 = yfinance 含息還原")
st.info("📅 回測區間：**2014/10/31（00631L 掛牌日）→ 2026/07/07**　｜　每年最後一個交易日執行再平衡")

# ── 資料載入（快取）────────────────────────────────────────────────────────

@st.cache_data(show_spinner="載入 0050 含息資料...")
def load_0050():
    csv_path = Path(__file__).parent / "0050_adj.csv"
    if not csv_path.exists():
        st.error("找不到 0050_adj.csv")
        st.stop()
    df = pd.read_csv(csv_path, index_col="date", parse_dates=True)
    return df["close"]

@st.cache_data(show_spinner="載入 00631L TWSE 資料...")
def load_l2():
    csv_path = Path(__file__).parent / "00631L_twse.csv"
    if not csv_path.exists():
        st.error("找不到 00631L_twse.csv，請先執行 fetch_00631L_twse.py")
        st.stop()
    df = pd.read_csv(csv_path, index_col="date", parse_dates=True)
    return df["close"].sort_index()

@st.cache_data(show_spinner="建立回測資料集...")
def build_prices(_p_l2_raw, _p_0050):
    # 補缺口
    all_dates = _p_0050.index
    p_l2 = _p_l2_raw.reindex(all_dates)
    r_0050 = _p_0050.pct_change()
    for i in range(1, len(all_dates)):
        if pd.isna(p_l2.iloc[i]) and not pd.isna(p_l2.iloc[i-1]):
            p_l2.iloc[i] = p_l2.iloc[i-1] * (1 + 2 * r_0050.iloc[i])
    p_l2 = p_l2.dropna()

    # 還原股票分割
    r_tmp = p_l2.pct_change()
    splits = r_tmp[r_tmp < -0.40]
    p_l2_adj = p_l2.copy()
    for d in splits.index:
        idx = p_l2_adj.index.get_loc(d)
        ratio = p_l2_adj.iloc[idx-1] / p_l2_adj.iloc[idx]
        p_l2_adj.iloc[:idx] = p_l2_adj.iloc[:idx] / ratio

    prices = pd.DataFrame({"L2": p_l2_adj, "0050": _p_0050}).ffill().dropna()
    prices = prices[prices.index >= "2014-10-31"]
    return prices

# ── 回測邏輯 ──────────────────────────────────────────────────────────────

def calc_mdd(values):
    arr = np.array(values)
    peak = np.maximum.accumulate(arr)
    return ((arr - peak) / peak).min()

def run_backtest(prices, w_l2, w_0050, w_cash, init):
    r_l2   = prices["L2"].pct_change().fillna(0)
    r_0050 = prices["0050"].pct_change().fillna(0)
    dates  = prices.index
    n = len(dates)

    a_l2   = init * w_l2
    a_0050 = init * w_0050
    a_cash = init * w_cash
    portfolio = []

    for i in range(n):
        a_l2   *= (1 + r_l2.iloc[i])
        a_0050 *= (1 + r_0050.iloc[i])
        total   = a_l2 + a_0050 + a_cash
        portfolio.append(total)

        is_last = (i == n-1) or (dates[i+1].year != dates[i].year)
        if is_last and dates[i].year != dates[0].year:
            a_l2   = total * w_l2
            a_0050 = total * w_0050
            a_cash = total * w_cash

    s = pd.Series(portfolio, index=dates)
    return s

# ── UI ───────────────────────────────────────────────────────────────────

st.markdown("### 投入配置")
st.caption("最多可同時比較 3 個策略，留空（三欄皆為 0）表示不啟用該策略")

STRATEGY_DEFAULTS = [
    ("策略 A", 1500, 0,   500),
    ("策略 B", 1200, 600, 200),
    ("策略 C", 0,    2000, 0),
]

strategies = []
for label, d_l2, d_0050, d_cash in STRATEGY_DEFAULTS:
    st.markdown(f"**{label}**")
    c1, c2, c3 = st.columns(3)
    with c1:
        l2   = st.number_input("00631L（萬元）", min_value=0, value=d_l2,   step=100, key=f"{label}_l2")
    with c2:
        o50  = st.number_input("0050（萬元）",   min_value=0, value=d_0050, step=100, key=f"{label}_0050")
    with c3:
        cash = st.number_input("現金（萬元）",   min_value=0, value=d_cash, step=100, key=f"{label}_cash")
    total = l2 + o50 + cash
    if total > 0:
        wl = l2 / total; w5 = o50 / total; wc = cash / total
        lev = wl * 2 + w5
        st.caption(f"總資金 {total:,} 萬　｜　00631L {wl*100:.0f}%　0050 {w5*100:.0f}%　現金 {wc*100:.0f}%　｜　槓桿 **{lev:.2f}x**")
        strategies.append((label, total, wl, w5, wc))
    st.divider()

if not strategies:
    st.warning("請至少填入一個策略")
    st.stop()

run = st.button("▶ 開始回測", type="primary", use_container_width=True)

def fmt_asset(val_twd):
    """格式化資產金額"""
    yi = val_twd / 1e8
    if yi >= 1:
        return f"{yi:.2f} 億"
    return f"{val_twd/1e4:,.0f} 萬"

PRESETS = [
    ("75%正二 + 25%現金",          0.75, 0.00, 0.25),
    ("60%正二 + 30%0050 + 10%現金", 0.60, 0.30, 0.10),
    ("100% 00631L",                 1.00, 0.00, 0.00),
    ("100% 0050",                   0.00, 1.00, 0.00),
]

if run:
    with st.spinner("計算中..."):
        p_l2_raw = load_l2()
        p_0050   = load_0050()
        prices   = build_prices(p_l2_raw, p_0050)
        results = {}
        for label, total, wl, w5, wc in strategies:
            results[label] = run_backtest(prices, wl, w5, wc, total * 1e4)

    st.markdown("---")
    st.markdown("### 回測結果（2014/10/31 → 2026/07/07，每年底再平衡）")

    # ── 比較總表
    rows = []
    for label, total, wl, w5, wc in strategies:
        s   = results[label]
        f   = s.iloc[-1]
        r   = f / (total * 1e4) - 1
        m   = calc_mdd(s.values)
        lo  = s.min()
        lod = s.idxmin().date()
        lev = wl * 2 + w5
        rows.append({
            "策略": label,
            "配置": f"正二{wl*100:.0f}% / 0050 {w5*100:.0f}% / 現金{wc*100:.0f}%",
            "槓桿": f"{lev:.2f}x",
            "本金（萬）": f"{total:,}",
            "最終資產": fmt_asset(f),
            "總漲幅": f"{r*100:+.1f}%",
            "最大回撤": f"{m*100:.1f}%",
            "最低點": f"{fmt_asset(lo)}（{lod}）",
        })
    st.dataframe(pd.DataFrame(rows).set_index("策略"), use_container_width=True)

    # ── 年度明細（萬元）
    st.markdown("#### 各年度年末資產（萬元）")
    yearly = {}
    for yr in sorted(set(prices.index.year)):
        row = {}
        for label, total, wl, w5, wc in strategies:
            sub = results[label]
            sub = sub[sub.index.year == yr]
            row[label] = round(sub.iloc[-1] / 1e4, 1) if len(sub) else None
        yearly[yr] = row
    df_yr = pd.DataFrame(yearly).T
    df_yr.index.name = "年份"
    st.dataframe(df_yr, use_container_width=True)

    # ── 走勢圖（統一以各自本金=100為基準，比較相對報酬）
    st.markdown("#### 資產走勢（以本金為基準，倍數）")
    chart_data = pd.DataFrame({
        label: results[label] / (total * 1e4)
        for label, total, wl, w5, wc in strategies
    })
    st.line_chart(chart_data)

    st.caption(f"回測起點 {prices.index[0].date()}，共 {len(prices)} 個交易日")
