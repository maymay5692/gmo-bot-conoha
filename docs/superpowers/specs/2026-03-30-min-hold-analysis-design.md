# min_hold シミュレーション分析 設計

## 概要

バックテスターに min_hold（最低保持時間）シミュレーションを正式分析モードとして追加する。
open後一定時間closeを禁止した場合のP&L変化をwhat-ifシミュレーションし、DSRで統計的有意性を判定する。

## 背景と目的

C-new-1/C-new-3調査により以下が判明:

- 現行botはclose注文のcancel/再送信を繰り返し、逆行中に追いかけて不利なタイミングで決済している
- cancel 3-5回帯が全損失の58%を占める（P&L=-415.49 JPY）
- min_hold=180sでP&L/tripが-1.69→+0.31に改善（黒字転換）
- min_hold=300sでP&L/trip=+0.95（最大改善）
- 300s+保持のtripはmean reversionにより平均P&L/trip=+9.15

この分析モードにより、min_hold値の最適化とその統計的根拠を定量化し、
bot本体（Rust）へのmin_hold制約導入の判断材料とする。

## モジュール構成

### 新規ファイル: `scripts/backtester/min_hold_sim.py`

既存cnew3_whatif.pyの`_simulate_min_hold`ロジックを再利用・整理。

#### `simulate_min_hold(trips, timeline, min_hold_s)`

hold_time < min_hold_s のtripについて、min_hold_s時点のmid_priceでcloseしたと仮定してP&L変化を推定。

- trips — build_trips()の結果
- timeline — build_market_timeline()の結果
- min_hold_s — 最低保持時間（秒）

戻り値:
```python
{
    "min_hold_s": float,
    "total_trips": int,
    "affected_trips": int,
    "original_pnl_sum": float,
    "simulated_pnl_sum": float,
    "delta_pnl": float,
    "pnl_per_trip_orig": float,
    "pnl_per_trip_sim": float,
    "simulated_pnl_list": list[float],  # DSR計算用の個別trip P&Lリスト
}
```

ロジック:
1. matchedなtripを走査
2. hold_time >= min_hold_s のtripはP&Lをそのまま使用
3. hold_time < min_hold_s のtripは:
   - open_fill.timestamp + min_hold_s 時点のmid_priceをtimelineから取得
   - mid_priceが取得できない場合は元のP&Lを使用
   - 取得できた場合: `new_pnl = (target_mid - open_mid) * size * direction + spread_captured`

#### `simulate_min_hold_sweep(trips, timeline, hold_values=None)`

複数のmin_hold値で一括シミュレーション。

- hold_values — min_hold値のリスト。デフォルト `[30, 60, 120, 180, 300]`
- 戻り値 — `list[dict]`（各dictは`simulate_min_hold`の戻り値）

### 既存ファイルの変更

#### `scripts/backtester/run_analysis.py`

- `analysis_min_hold()` 関数を追加
- `--analysis` choicesに `"min_hold"` を追加
- `--analysis all` にも含める
- DSR判定: N=len(hold_values)、各パターンのsimulated_pnl_listからSRを算出しベストでDSR

## 出力形式

```
=== min_hold シミュレーション ===
  min_hold   件数  影響trip   orig_pnl/t   sim_pnl/t     delta
     30s     425       98       -1.691      -1.310    +0.381
     60s     425      147       -1.691      -1.056    +0.635
    120s     425      232       -1.691      -0.406    +1.285
    180s     425      302       -1.691      +0.311    +2.001
    300s     425      358       -1.691      +0.952    +2.643

  DSR: X.XX (N=5, T=425, SR_best=X.XX) — ...
```

## 依存関係

- `market_replay.get_mid_price_series` — 指定時刻のmid_price取得
- `dsr.evaluate_dsr`, `dsr.format_dsr_line`, `dsr.calc_sharpe_ratio` — DSR判定

## スコープ外

- bot本体（Rust）へのmin_hold制約導入（分析結果に基づく後続プロジェクト）
- cnew3_whatif.pyの他のシナリオ（delayed close, early SL）の統合
- cnew1_analysis.pyの統合（探索的スクリプトとして残す）
- mid逆行パス分析（Scenario 3）の統合
