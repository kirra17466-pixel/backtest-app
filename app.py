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
col1, col2, col3 = st.columns(3)
with col1:
    amt_l2   = st.number_input("00631L（萬元）", min_value=0, value=1500, step=100)
with col2:
    amt_0050 = st.number_input("0050（萬元）",   min_value=0, value=0,    step=100)
with col3:
    amt_cash = st.number_input("現金（萬元）",   min_value=0, value=500,  step=100)

total_init = amt_l2 + amt_0050 + amt_cash

if total_init == 0:
    st.warning("請輸入至少一項金額")
    st.stop()

w_l2   = amt_l2   / total_init
w_0050 = amt_0050 / total_init
w_cash = amt_cash / total_init

leverage = w_l2 * 2 + w_0050 * 1
st.info(
    f"**總資金：{total_init:,} 萬元**　｜　"
    f"00631L {w_l2*100:.1f}%　0050 {w_0050*100:.1f}%　現金 {w_cash*100:.1f}%　｜　"
    f"**組合槓桿：{leverage:.2f}x**"
)

run = st.button("▶ 開始回測", type="primary", use_container_width=True)

if run:
    with st.spinner("計算中..."):
        p_l2_raw = load_l2()
        p_0050   = load_0050()
        prices   = build_prices(p_l2_raw, p_0050)

        s = run_backtest(prices, w_l2, w_0050, w_cash, total_init * 1e4)

    final  = s.iloc[-1]
    mdd    = calc_mdd(s.values)
    lowest = s.min()
    low_d  = s.idxmin().date()
    ret    = final / (total_init * 1e4) - 1

    st.markdown("---")
    st.markdown("### 回測結果（2014/10/31 → 2026/07/07，每年底再平衡）")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("最終資產", f"{final/1e4:,.0f} 萬元")
    m2.metric("總漲幅",   f"{ret*100:+.1f}%")
    m3.metric("最大回撤", f"{mdd*100:.1f}%")
    m4.metric("最低點",   f"{lowest/1e4:,.0f} 萬（{low_d}）")

    # 年度表
    st.markdown("#### 各年度年末資產")
    yearly = {}
    for yr in sorted(set(s.index.year)):
        sub = s[s.index.year == yr]
        if len(sub):
            yearly[yr] = {
                "年末資產（萬元）": round(sub.iloc[-1] / 1e4, 1),
                "當年漲跌":        f"{(sub.iloc[-1]/sub.iloc[0] - 1)*100:+.1f}%"
            }
    df_yr = pd.DataFrame(yearly).T
    df_yr.index.name = "年份"
    st.dataframe(df_yr, use_container_width=True)

    # 走勢圖
    st.markdown("#### 資產走勢")
    chart = (s / 1e4).rename("資產（萬元）")
    st.line_chart(chart)

    st.caption(f"回測起點 {prices.index[0].date()}，共 {len(prices)} 個交易日，每年最後一個交易日執行再平衡")
