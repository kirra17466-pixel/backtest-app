# -*- coding: utf-8 -*-
"""
真實回測 v4 最終版
- 00631L：TWSE 官方收盤價 + 補缺口(0050×2) + 自動偵測並還原股票分割
- 0050：yfinance auto_adjust 含息還原
"""
import pandas as pd
import numpy as np
import yfinance as yf

START = "2014-10-31"
INIT  = 20_000_000

# ── 1. 載入 00631L TWSE 資料
print("載入 00631L TWSE 資料...")
df_l2 = pd.read_csv("00631L_twse.csv", index_col="date", parse_dates=True)
p_l2_raw = df_l2["close"].sort_index()
p_l2_raw = p_l2_raw[p_l2_raw.index >= START]

# ── 2. 載入 0050 含息還原
print("下載 0050 含息資料...")
t = yf.Ticker("0050.TW")
hist = t.history(start=START, end="2026-07-10", auto_adjust=True)
p_0050 = hist["Close"].copy()
p_0050.index = p_0050.index.tz_localize(None)

# ── 3. 補 00631L 缺口：用 0050×2 的日報酬填入缺少的交易日
#    以 0050 的交易日為基準，00631L 缺的日子用前一天 × (1 + 2×0050_daily_ret) 補
all_dates = p_0050.index
p_l2_filled = p_l2_raw.reindex(all_dates)

r_0050_daily = p_0050.pct_change()
for i in range(1, len(all_dates)):
    d = all_dates[i]
    if pd.isna(p_l2_filled[d]):
        prev = p_l2_filled.iloc[i-1]
        if not pd.isna(prev):
            p_l2_filled.iloc[i] = prev * (1 + 2 * r_0050_daily.iloc[i])

p_l2_filled = p_l2_filled.dropna()

# ── 4. 偵測並還原股票分割（日報酬絕對值 > 40%）
r_l2_raw = p_l2_filled.pct_change()
splits = r_l2_raw[r_l2_raw < -0.40]
print(f"\n偵測到 {len(splits)} 個分割事件：")
for d, ret in splits.items():
    before = p_l2_filled[d - pd.Timedelta(days=1):d].iloc[-2] if len(p_l2_filled[:d]) >= 2 else None
    after  = p_l2_filled[d]
    ratio  = before / after if before else None
    print(f"  {d.date()}：前一日 {before:.2f} → 當日 {after:.2f}，隱含比例 {ratio:.2f}x")

# 逐一往回調整分割點之前的所有價格（backward adjustment）
p_l2_adj = p_l2_filled.copy()
for d, ret in splits.items():
    idx = p_l2_adj.index.get_loc(d)
    before_price = p_l2_adj.iloc[idx - 1]
    after_price  = p_l2_adj.iloc[idx]
    # 包含市場波動的真實split ratio：前一交易日收盤 / 當日收盤（market move已在填充時處理）
    split_ratio = before_price / after_price
    # 往回乘以split_ratio，讓所有歷史價格縮小到post-split尺度
    p_l2_adj.iloc[:idx] = p_l2_adj.iloc[:idx] / split_ratio

print(f"\n00631L 調整後：起始 {p_l2_adj.iloc[0]:.4f}  終止 {p_l2_adj.iloc[-1]:.4f}")
print(f"0050 含息   ：起始 {p_0050.iloc[0]:.4f}  終止 {p_0050.iloc[-1]:.4f}")

# ── 5. 對齊並計算日報酬
prices = pd.DataFrame({"L2": p_l2_adj, "0050": p_0050}).ffill().dropna()
prices = prices[prices.index >= START]

r_l2   = prices["L2"].pct_change().fillna(0)
r_0050 = prices["0050"].pct_change().fillna(0)

print(f"\n對齊後：{prices.index[0].date()} → {prices.index[-1].date()}，共 {len(prices)} 個交易日")
print(f"00631L 總報酬：{(prices['L2'].iloc[-1]/prices['L2'].iloc[0] - 1)*100:.1f}%")
print(f"0050   總報酬：{(prices['0050'].iloc[-1]/prices['0050'].iloc[0] - 1)*100:.1f}%\n")

# ── 6. 回測
def calc_mdd(values):
    arr = np.array(values)
    peak = np.maximum.accumulate(arr)
    return ((arr - peak) / peak).min()

def run_strategy(name, w_l2, w_0050, w_cash, rebalance=True):
    dates = prices.index
    n = len(dates)
    a_l2   = INIT * w_l2
    a_0050 = INIT * w_0050
    a_cash = INIT * w_cash
    portfolio = []

    for i in range(n):
        a_l2   *= (1 + r_l2.iloc[i])
        a_0050 *= (1 + r_0050.iloc[i])
        total   = a_l2 + a_0050 + a_cash
        portfolio.append(total)

        if rebalance:
            is_last = (i == n-1) or (dates[i+1].year != dates[i].year)
            if is_last and dates[i].year != dates[0].year:
                a_l2   = total * w_l2
                a_0050 = total * w_0050
                a_cash = total * w_cash

    s = pd.Series(portfolio, index=dates)
    final    = s.iloc[-1]
    mdd      = calc_mdd(portfolio)
    lowest   = s.min()
    lowest_d = s.idxmin().date()

    print(f"{'─'*64}")
    print(f"【{name}】")
    print(f"  最終資產：{final/1e4:>10.1f} 萬元")
    print(f"  總漲幅  ：{(final/INIT-1)*100:>+.1f}%")
    print(f"  最大回撤：{mdd*100:.1f}%")
    print(f"  最低點  ：{lowest/1e4:>10.1f} 萬元  ({lowest_d})")
    print()
    return s

print("=" * 64)
print(f"回測起始資金：{INIT/1e4:.0f} 萬元")
print("資料：00631L=TWSE官方+分割還原 ｜ 0050=yfinance含息還原")
print("=" * 64 + "\n")

s1 = run_strategy("方案1：75%正二 + 25%現金（年底再平衡）",
                  w_l2=0.75, w_0050=0.0, w_cash=0.25)
s2 = run_strategy("方案2：60%正二 + 30%0050 + 10%現金（年底再平衡）",
                  w_l2=0.60, w_0050=0.30, w_cash=0.10)
s3 = run_strategy("方案3：100% 00631L（持有不動）",
                  w_l2=1.0, w_0050=0.0, w_cash=0.0, rebalance=False)
s4 = run_strategy("方案4：100% 0050（持有不動）",
                  w_l2=0.0, w_0050=1.0, w_cash=0.0, rebalance=False)

print("\n── 各年度年末資產（萬元）──")
header = f"{'年份':>6} {'方案1':>10} {'方案2':>10} {'方案3':>10} {'方案4':>10}"
print(header)
print("─" * len(header))
for yr in sorted(set(s1.index.year)):
    row = f"{yr:>6}"
    for s in [s1, s2, s3, s4]:
        sub = s[s.index.year == yr]
        val = sub.iloc[-1] / 1e4 if len(sub) else float("nan")
        row += f" {val:>10.1f}"
    print(row)

combined = pd.DataFrame({"方案1": s1, "方案2": s2, "方案3": s3, "方案4": s4})
combined.to_csv("backtest_final.csv")
print("\n完整每日資產已存至 backtest_final.csv")
