# 15秒強制決済シミュレーション 実装計画

## 目的
既存データで「全OPEN FILLを15秒後にbid/askで決済したらP&Lはいくらか」を算出し、
15秒強制決済の実装判断材料を得る。

## 判断基準
- シミュレーションP&L > +2 JPY/trip → 実装GO
- シミュレーションP&L < -5 JPY/trip → 別戦略検討
- -1〜+1 JPY → v0.9.5データ待ち

## ファイル
- `scripts/simulate_forced_close.py` （新規作成）

## 実装ステップ

### Step 1: データ取得・パース
- analyze_metrics.pyのキャッシュ機構を参考に実装
- VPSから trades CSV + metrics CSV を取得
- trades: event=ORDER_FILLED, is_close=false のみ抽出
- metrics: timestamp, mid_price, best_bid, best_ask をパース
- `--date`, `--fetch` オプション対応

### Step 2: 時系列ルックアップ構築
- metrics CSVからtimestamp→(mid_price, best_bid, best_ask)の配列
- bisectで任意timestampの最近傍を O(log n) 取得
- ルックアップオフセット: +16秒（15秒 + 1秒API遅延バッファ）

### Step 3: シミュレーションロジック
各OPEN FILLに対して:
```
BUY open → 16秒後のbest_bidで売り決済
  PnL = (bid_16s - fill_price) * size

SELL open → 16秒後のbest_askで買い決済
  PnL = (fill_price - ask_16s) * size
```

P&L分解:
- entry_spread_cost = |fill_price - mid_price_at_entry| * size
- mid_movement = (mid_16s - mid_entry) * size * direction
- exit_spread_cost = |mid_16s - close_price| * size

### Step 4: レポート出力
- 全体: 合計P&L, 平均P&L/trip, トリップ数
- BUY/SELL別: 合計, 平均, 勝率
- P&L分解: entry_spread, mid_movement, exit_spread の平均
- 分布: P&Lバケット (-10以下, -5〜-10, -2〜-5, -2〜0, 0〜+2, +2〜+5, +5以上)
- 比較: 現実のcollateral変化 vs シミュレーションP&L
- 複数閾値: 10秒, 15秒, 20秒, 30秒で比較

### Step 5: 既存v0.9.4データ (2026-02-16) で実行
- VPSからデータフェッチ
- シミュレーション実行
- 結果を分析・報告

## テスト
- ルックアップ関数の単体テスト（境界値、データ欠損）
- 既知の値でP&L計算の正確性を検証
