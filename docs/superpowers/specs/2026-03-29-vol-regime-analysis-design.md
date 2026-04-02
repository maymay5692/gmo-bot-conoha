# ボラティリティレジーム分析 設計

## 概要

バックテスター (`scripts/backtester/`) にボラティリティレジーム分析を追加する。
EWMA volatilityのパーセンタイルで低・中・高の3レジームに分類し、
レジーム別P&L集計とフィルタwhat-ifシミュレーションを提供する。

## 背景と目的

- v0.13.3バックテスト分析で120-300s帯が損失の47%を占めることが判明
- 高ボラティリティ環境ではadverse movementが大きくなり、MM botの損失が拡大する
- ボラレジームごとのP&L特性を定量化し、「高ボラ時に取引を止めるべきか」の根拠を得る
- 将来的にbot本体（Rust）へのレジーム制御導入の判断材料とする

## モジュール構成

### 新規ファイル: `scripts/backtester/vol_regime.py`

3つの公開関数を提供する。

#### `classify_vol_regime(timeline, percentiles=(25, 75))`

metricsから構築されたtimelineのvolatility分布からパーセンタイル境界を算出し、
各MarketStateにレジームラベルを付与したマッピングを返す。

- timeline — `build_market_timeline(metrics)` の結果（`list[MarketState]`）
- percentiles — 低/中/高の境界パーセンタイル（デフォルト P25/P75）
- 戻り値 — `VolRegimeResult` dict: `{"boundaries": {"p25": float, "p75": float}, "labels": dict[datetime, str]}`

レジーム分類:
- vol < P25 → "low"
- P25 ≤ vol < P75 → "mid"
- vol ≥ P75 → "high"

#### `analyze_by_vol_regime(trips, regime_result, timeline)`

各tripのopen_fill時刻でのvolatilityレジームを取得し、レジーム別にP&L集計する。

- tripのopen_fill.timestampに最も近いtimeline上のMarketStateからvolatilityとレジームを取得
- `market_replay.get_market_state_at(timeline, timestamp)` を使用

戻り値 — レジーム別のリスト:
```python
[{
    "regime": str,       # "low" / "mid" / "high"
    "count": int,
    "pnl_sum": float,
    "pnl_mean": float,
    "adverse_mean": float,
    "win_rate": float,
    "hold_mean_s": float,
    "vol_mean": float,   # そのレジーム内の平均volatility
}]
```

#### `calc_vol_filter_impact(trips, regime_result, timeline, exclude_regimes)`

特定レジームを除外した場合のP&L変化をシミュレート。

- exclude_regimes — 除外するレジーム名のリスト（例: `["high"]`, `["high", "mid"]`）
- 戻り値 — `time_filter`と同じ構造: `{"included": {...}, "excluded": {...}, "total": {...}}`

### 既存ファイルの変更

#### `scripts/backtester/run_analysis.py`

- `analysis_vol_regime()` 関数を追加
- `--analysis` choicesに `"vol_regime"` を追加
- `--analysis all` にも含める
- 出力末尾にDSRを表示（N=除外パターン数）

## 出力形式

```
=== ボラティリティレジーム分析 ===
  Volatility分布: P25=520.3  P75=892.1

  レジーム    件数  P&L合計   P&L/trip  adverse  win率    hold(s)  avg_vol
  low          32    +45.20    +1.41   -1.82    62.5%    185.3    420.1
  mid          64    -28.50    -0.45   -3.12    48.4%    220.1    710.5
  high         31    -95.30    -3.07   -8.45    32.3%    310.5   1105.2

=== フィルタwhat-if ===
  除外パターン      件数  P&L合計   P&L/trip  改善
  high除外           96    +16.70    +0.17   +2.73/trip
  high+mid除外       32    +45.20    +1.41   +4.98/trip
  low除外            95   -123.80    -1.30   +0.27/trip

  DSR: 0.82 (N=3, T=96, SR_best=0.15) — ⚠ 閾値0.95未満: この改善は偶然の可能性あり
```

## DSR統合

what-ifフィルタパターン（high除外、high+mid除外、low除外）の3パターンを比較するため、N=3でDSR計算。
ベストSRのフィルタパターンのP&Lサブセットで判定する（time_filterと同じ方式）。

## 依存関係

- `market_replay.get_market_state_at` — tripの時刻でのMarketState取得
- `market_replay.MarketState` — volatilityフィールドを持つ
- `dsr.evaluate_dsr`, `dsr.format_dsr_line`, `dsr.calc_sharpe_ratio` — DSR判定
- numpy は不要（パーセンタイル計算はsorted + インデックスで実装）

## スコープ外

- bot本体（Rust）へのレジーム制御導入（データ根拠を得た後の別プロジェクト）
- 連続値回帰分析（過学習リスクが高く、DSRで有意にならない可能性が高い）
- 複数日にまたがるレジーム分析（各日独立分析）
- レジーム遷移タイミングの分析（今回はスナップショット分類のみ）
- カスタムパーセンタイル指定のCLI引数（デフォルトP25/P75で固定）
