# v0.10.x 正確なデータでの再分析レポート

**日付**: 2026-02-21
**分析者**: Claude Code (自動分析)
**目的**: バージョンラベルの誤りを修正し、正確なデータで再分析

---

## 1. バージョンラベルの修正

### 以前の誤り
| ラベル | 日付 | 実際のバージョン |
|--------|------|-----------------|
| "v0.10.0-day1" | 2/18 | **v0.9.5** (SLなし、SOKなし) |
| "v0.10.0-day2" | 2/19 | 60% v0.9.5 + 40% v0.10.x混在 |
| "v0.10.0-day3" | 2/20 | v0.10.x (11.7h分のみ) |

### 確定したデプロイ境界
- **v0.10.xデプロイ**: 2026-02-19 14:38:15 UTC
- **根拠**: 最初の `STOP_LOSS_TRIGGERED` イベント (SLはv0.10.xで導入)
- **v0.10.x停止**: 2026-02-20 ~12:00 UTC (手動停止)
- **合計稼働**: 約21時間

---

## 2. 正確な分析結果

### 2a. v0.9.5 正確ベースライン (2/18 全日 24.0h)

```
--- A. Operational Summary ---
  Uptime:        24.0 hours
  Total events:  22,616
  Cycles:        9,187

--- B. Order Flow ---
  ORDER_SENT:      10,954
  ORDER_FILLED:    3,166
  ORDER_CANCELLED: 7,788
  ORDER_FAILED:    708
  STOP_LOSS:       0
  Fill Rate:       28.90%
  Open Fill Rate:  31.97%
  Close Fill Rate: 26.37%

--- C. P&L ---
  Collateral: 30,353 -> 27,052 JPY
  P&L:        -3,301 JPY (-10.88%)
  P&L/hour:   -137.60 JPY/h
  Max DD:     3,311 JPY

--- D. Trip Analysis ---
  Completed trips:     1,581
  P&L/trip:            -1.62 JPY
  Spread capture/trip: +2.12 JPY
  Mid adverse/trip:    -3.74 JPY
  Win rate:            46.24%
  Avg hold:            58.5s
  Median hold:         25.8s
  Unmatched opens:     1
  Unmatched closes:    3

--- F. Errors ---
  ERR-422 (Ghost): 708
  Stop-loss total: 0 JPY
```

### 2b. v0.10.x Day 1 (2/19 14:38-23:59 UTC, 9.4h)

```
--- A. Operational Summary ---
  Uptime:        9.4 hours
  Total events:  8,887
  Cycles:        3,589

--- B. Order Flow ---
  ORDER_SENT:      4,247
  ORDER_FILLED:    1,496
  STOP_LOSS:       209
  Fill Rate:       35.22%
  Open Fill Rate:  33.68%
  Close Fill Rate: 37.61%

--- C. P&L ---
  Collateral: 25,762 -> 23,813 JPY
  P&L:        -1,949 JPY (-7.57%)
  P&L/hour:   -208.23 JPY/h   <-- 最悪
  Max DD:     2,001 JPY

--- D. Trip Analysis ---
  Completed trips:     626
  P&L/trip:            -2.95 JPY
  Spread capture/trip: +1.59 JPY
  Mid adverse/trip:    -4.53 JPY
  Win rate:            47.28%
  Avg hold:            4,913s   <-- バグ
  Unmatched opens:     243      <-- バグ

--- F. Errors ---
  ERR-422 (Ghost): 185
  Stop-loss total: -2,292.67 JPY
```

### 2c. v0.10.x Day 2 (2/20 全日, 11.7h)

```
--- A. Operational Summary ---
  Uptime:        11.7 hours
  Total events:  9,474
  Cycles:        3,864

--- B. Order Flow ---
  ORDER_SENT:      4,607
  ORDER_FILLED:    1,274
  STOP_LOSS:       96
  Fill Rate:       27.65%
  Open Fill Rate:  24.24%
  Close Fill Rate: 33.61%

--- C. P&L ---
  Collateral: 23,813 -> 22,464 JPY
  P&L:        -1,349 JPY (-5.67%)
  P&L/hour:   -115.79 JPY/h   <-- v0.9.5より良い
  Max DD:     1,352 JPY

--- D. Trip Analysis ---
  Completed trips:     563
  P&L/trip:            +0.86 JPY  <-- プラス
  Spread capture/trip: +1.42 JPY
  Mid adverse/trip:    -0.56 JPY  <-- 異常に小さい
  Win rate:            47.78%
  Avg hold:            4,674s     <-- バグ
  Unmatched opens:     147        <-- バグ

--- F. Errors ---
  ERR-422 (Ghost): 164
  Stop-loss total: -695.26 JPY
```

### 2d. v0.10.x 結合 (2/19午後+2/20, 21.0h)

```
--- C. P&L ---
  Collateral: 25,762 -> 22,464 JPY
  P&L:        -3,298 JPY (-12.80%)
  P&L/hour:   -156.97 JPY/h
  Max DD:     3,353 JPY

--- D. Trip Analysis ---
  Completed trips:     1,190
  P&L/trip:            -5.91 JPY
  Spread capture/trip: +1.52 JPY
  Mid adverse/trip:    -7.43 JPY
  Unmatched opens:     389

--- F. Errors ---
  Stop-loss total: -2,987.92 JPY
```

---

## 3. 比較サマリー

| 指標 | v0.9.5 (2/18, 24h) | v0.10.x (2/19午後, 9.4h) | v0.10.x (2/20, 11.7h) | v0.10.x結合 (21h) |
|------|:---:|:---:|:---:|:---:|
| **P&L/h** | -137.6 | **-208.2** | -115.8 | -157.0 |
| **P&L/trip** | -1.62 | -2.95 | **+0.86** | -5.91 |
| **Fill Rate** | 28.9% | **35.2%** | 27.7% | 31.3% |
| **Spread捕捉** | **2.12** | 1.59 | 1.42 | 1.52 |
| **Mid逆行** | -3.74 | -4.53 | **-0.56** | -7.43 |
| **保有(s)** | **58.5** | 4,913 | 4,674 | 12,410 |
| **SL損失** | 0 | -2,293 | -695 | -2,988 |
| **Unmatched** | **4** | 244 | 148 | 390 |
| **ERR-422** | 708 | 185 | 164 | 349 |

---

## 4. 分析所見

### 4a. v0.10.xは全体的にv0.9.5より悪化
- **P&L/h**: v0.9.5 -137.6 vs v0.10.x結合 -157.0 (**14%悪化**)
- **P&L/trip**: v0.9.5 -1.62 vs v0.10.x結合 -5.91 (**3.6倍悪化**)
- ただし結合分析のtrip matchingは日をまたぐため数値が膨張している

### 4b. SL -5が損失の主因
- v0.10.x 21hの総P&L: -3,298 JPY
- うちSL損失: -2,988 JPY (**全損失の90.6%**)
- SLなしの場合のP&L推定: -310 JPY (-14.8/h) → **大幅改善の可能性**
- ただしSLなし=ポジション滞留拡大のリスクもあるため単純比較は危険

### 4c. 2/20のP&L/trip +0.86は市場環境要因
- Mid逆行が-0.56と異常に小さい (v0.9.5: -3.74, 2/19午後: -4.53)
- これはbot戦略の改善ではなく市場のmid価格変動が小さかっただけ
- **v0.10.xの構造的改善は確認できない**

### 4d. execution_retain_msバグの影響
- 保有時間 58.5s (v0.9.5) → 4,600-4,900s (v0.10.x) = **80倍**
- Unmatched 4 → 148-244 = **40-60倍**
- 原因: execution_retain_ms=5000ms (WS市場データ保持)
- 注意: 以前「ポジション追跡が5sで消える」と誤解していたが、実際はWSデータ保持期間
- ポジション追跡はget_position (5sポーリング)で別管理

### 4e. ERR-422の改善
- v0.9.5: 708 → v0.10.x: 164-185
- v0.10.1でERR-422ハンドリング追加(リセット+延長クールダウン)が効果を発揮

### 4f. Fill Rateの変動
- 2/19午後のFill Rate 35.2%は異常に高い（v0.9.5: 28.9%）
- order_interval 2s (v0.9.5は5s) による注文頻度増加が要因
- 2/20では27.7%に低下 → 市場環境依存が大きい

---

## 5. 結論と次アクション

### 確定事項
1. **v0.10.xはv0.9.5より悪化** - SL損失が主因。バグ修正だけでは改善しない
2. **SL -5のチューニングが最優先** - 現状では損失の90%以上がSL由来
3. **SOK無効化は有効** - ERR-5003=0でMaker成功率100%だがリベート=0なので不要
4. **execution_retain_ms拡大は必要** - ボラ推定データ増加のため (ポジション追跡とは無関係)

### 推奨アクション (優先順)
1. SL閾値の再調整 (-5 → -10 or -15、またはSL一時無効化で比較)
2. SOK無効化 (config変更のみ)
3. execution_retain_ms: 5000 → 30000 (config変更のみ)
4. バグ修正後にベースライン測定 (最低24h)
5. Phase 2 (L1-L3除外, 深夜帯停止) の実装

---

## 6. データファイル一覧

分析に使用したデータはすべてキャッシュに保存済み:

| ファイル | 内容 |
|---------|------|
| `scripts/.cache/verify-v0.9.5-correct-2026-02-18.json` | v0.9.5正確ベースライン |
| `scripts/.cache/verify-v0.10.x-2026-02-19-afternoon.json` | v0.10.x 2/19午後 |
| `scripts/.cache/verify-v0.10.x-2026-02-20-full.json` | v0.10.x 2/20フルデータ |
| `scripts/.cache/verify-v0.10.x-combined.json` | v0.10.x結合 |
| `scripts/.cache/trades-2026-02-19-v10x.json` | 2/19フィルタ済みtrades |
| `scripts/.cache/metrics-2026-02-19-v10x.json` | 2/19フィルタ済みmetrics |
