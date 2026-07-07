# -*- coding: utf-8 -*-
"""
從台灣證交所 API 抓取 00631L 完整歷史收盤價
輸出：00631L_twse.csv
"""
import urllib.request, json, ssl, time
import pandas as pd
from datetime import date

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def fetch_month(yyyymm: str) -> list[dict]:
    """抓取指定月份（格式 '201410'）的每日資料"""
    url = (f"https://www.twse.com.tw/exchangeReport/STOCK_DAY"
           f"?response=json&date={yyyymm}01&stockNo=00631L")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            data = json.loads(r.read())
        if data.get("stat") != "OK":
            return []
        rows = []
        for row in data.get("data", []):
            # 民國年轉西元
            roc = row[0]  # e.g. '103/10/31'
            parts = roc.split("/")
            year = int(parts[0]) + 1911
            date_str = f"{year}/{parts[1]}/{parts[2]}"
            close = float(row[6].replace(",", ""))
            rows.append({"date": date_str, "close": close})
        return rows
    except Exception as e:
        print(f"  !! {yyyymm} 失敗：{e}")
        return []

# ── 產生月份清單 2014/10 → 2026/07
months = []
y, m = 2014, 10
while (y, m) <= (2026, 7):
    months.append(f"{y}{m:02d}")
    m += 1
    if m > 12:
        m = 1
        y += 1

print(f"共 {len(months)} 個月份，開始下載...")
all_rows = []
for i, ym in enumerate(months):
    rows = fetch_month(ym)
    all_rows.extend(rows)
    print(f"  [{i+1:3d}/{len(months)}] {ym}  → {len(rows)} 筆")
    time.sleep(0.3)  # 避免打太快

df = pd.DataFrame(all_rows)
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date").drop_duplicates("date").set_index("date")

out = "00631L_twse.csv"
df.to_csv(out)
print(f"\n完成！共 {len(df)} 個交易日，已存至 {out}")
print(f"起始：{df.index[0].date()}  收盤：{df['close'].iloc[0]}")
print(f"結束：{df.index[-1].date()}  收盤：{df['close'].iloc[-1]}")
