# 🧭 Harbor 系統：市場環境報告解讀指南

此文件用於說明 `notifier.py` 推送至 Discord 的每日自動化報告各項指標之意義。

---

## 🛑 核心決策層 (The Alpha Decision)

### 1. Final Regime (最終市場模式)
系統綜合「結構」與「情緒」後給出的最高指令：

| Regime | 顏色 | 含義 | 操作 |
| :--- | :--- | :--- | :--- |
| **EASY_MONEY_PRO** | 🟢 綠色 | 強力多頭。結構健康 + 資金進場。 | 滿倉進攻。VCP 突破、Stage 2 動能交易。 |
| **DISTRIBUTION_DANGER** | 🟡 黃色 | 誘多或出貨期。結構尚可但資金開始外逃。 | 半倉試探，收緊停損，減少獲利了結。 |
| **ACCUMULATION_PHASE** | 🟠 橘色 | 築底期。結構爛但情緒悄悄回溫。 | 30% 倉位。超跌抄底 (Spring)、Mean Reversion。 |
| **HARD_MONEY_PROTECT** | 🔴 紅色 | 冰河期 / 崩盤。結構和情緒雙殺。 | 100% 現金，嚴禁買入。可用 `oversold_screener.py` 觀察標的。 |

### 2. Confidence & Position Size (信心度與倉位)

| Regime | Confidence | Position Size | 說明 |
| :--- | :--- | :--- | :--- |
| EASY_MONEY_PRO | 100% | 100% | 滿倉進攻，正常停損。 |
| DISTRIBUTION_DANGER | 50% | 50% | 半倉試探，停損縮 tight 50%。 |
| ACCUMULATION_PHASE | 30% | 30% | 小倉位 Pilot，觀察反轉確認。 |
| HARD_MONEY_PROTECT | 0% | 0% | 空倉觀望，等待結構修復。 |

---

## 🦴 Panel A: 市場結構指標 (Market Structure)
*確認市場「參與度」與「健康度」— 數據來源: yfinance (S&P 500)*

| 指標 | 基準值 | 多頭 (+1) | 空頭 (0) | 說明 |
| :--- | :--- | :--- | :--- | :--- |
| **Breadth (50MA/200MA)** | > 50% | 兩者皆 > 50% | 任一 < 50% | S&P 500 中高於均線的股票百分比。代表「有多少股票在漲」。 |
| **Net New Highs** | > 0 | Net > 0 且 > EMA | Net < 0 | 252 日創新高家數 − 創新低家數。正值 = 內部動能向上。 |
| **Smart Money (HYG/IEF)** | > SMA50 | Ratio > SMA50 | Ratio < SMA50 | 高收益債 vs 國債比值。大戶買垃圾債 = 願意承擔風險 = Risk-On。 |
| **VIX** | < 20 | VIX < 20 且 < SMA20 | VIX > 20 或 > SMA20 | 波動率指數。低 VIX = 市場平靜 = 買入訊號較穩定。 |

---

## 🧬 Panel B: 機構情緒指標 (Institutional Sentiment)
*透過 FRED / yfinance 判斷「資金真實流向」— 數據來源: Direct FRED API + yfinance ETF proxies*

| 指標 | 基準值 | 多頭 (+1) | 空頭 (0) | 說明 |
| :--- | :--- | :--- | :--- | :--- |
| **Growth vs Defensive (QQQ/XLP)** | > SMA50 | Ratio > SMA50 | Ratio < SMA50 | 科技股相對於必選消費。向上 = 機構追逐成長股。 |
| **Credit Appetite (HYG/IEF)** | > SMA50 | Ratio > SMA50 | Ratio < SMA50 | 信用債 vs 國債。同 Smart Money 但獨立計算。 |
| **High Yield OAS** | < 4.0% | Spread < 4% | Spread > 4% | 信用利差。利差收窄 = Risk-On；利差擴張 = 崩盤前兆。**此為「止跌」第一個訊號。** |
| **Yield Curve (10Y-2Y)** | > 0 | Spread > 0 | Spread < 0 | 殖利率曲線。正值 = 正常；負值 (倒掛) = 衰退預警。 |

### FRED 數據來源

| 指標 | FRED Series ID | 備用方案 |
| :--- | :--- | :--- |
| High Yield OAS | `BAMLH0A0HYM2` | HYG 20 日報酬率 (上漲 = 利差收窄) |
| 10Y Yield | `DGS10` | TLT/SHY 比值變化 |
| 2Y Yield | `DGS2` | TLT/SHY 比值變化 |

---

## 📊 圖表附件 (`market_health.png`)
每日報告附帶的 4-in-1 趨勢圖，用於觀察上述指標的 **「歷史趨勢」**。

*注意：指標的「轉折點」比「絕對數值」更重要。*

---

## 🔍 Oversold Screener (超賣選股器)

當系統進入 `HARD_MONEY_PROTECT` 或 `ACCUMULATION_PHASE` 時，執行：

```bash
python screen/screen_main.py --screener oversold
```

選股條件：
- **RSI < 30**: 極度超賣 (加 2 分)
- **RSI < 40**: 超賣 (加 1 分)
- **Above 200MA**: 在熊市中仍站穩長期均線 = 相對強勢 (加 1 分)
- **RSI Divergence**: 價格創新低但 RSI 未創新低 = 底部背離 (加 2 分)
- **Volume Surge**: 放量上漲 = 機構進場 (加 1 分)

---

## 🔄 每日執行流程

```bash
# 1. 生成報告 (結構 + 情緒 + 決策)
python market_health/market_regime.py

# 2. 推送 Discord (Embed + 圖表)
python notifier.py

# 3. 若為 HARD_MONEY / ACCUMULATION，執行超賣選股
python screen/screen_main.py --screener oversold
```

---
*Harbor System — Your Quantitative Navigation Brain.*
