# DSR (Deflated Sharpe Ratio) 導入設計

## 概要

バックテスター (`scripts/backtester/`) に Deflated Sharpe Ratio (DSR) を導入する。
複数パラメータを比較した際に「ベストの結果が偶然の産物でないか」を統計的に判定する。

参考文献: Bailey & López de Prado (2014), Harvey, Liu & Zhu (2016)
素材: `~/Desktop/claude-bridge/knowledge/on-demand/20260326-偽戦略定理DSR導入検討.md`

## 背景と目的

- バックテスターで alpha, time_filter, EV式 などパラメータ変更の効果を比較している
- 現状は生の P&L/trip だけで判断しており、多重比較バイアスを考慮していない
- N回試行すれば偶然良い結果が出る確率が上がる（N=1000でSR≈1.46が偶然出る）
- DSRを入れることで「この改善は統計的に有意か」を定量判定できる
- 後続のボラレジーム分類器導入時に、効果が本物か偶然かを検証する基盤になる

## モジュール構成

### 新規ファイル: `scripts/backtester/dsr.py`

2つの関数を提供する。

#### `expected_max_sr(N, T, skew, kurt)`

N回の独立試行で偶然出る最大 Sharpe Ratio の期待値を返す。

- N — 試行回数（比較パラメータ数）
- T — サンプル数（trip数）
- skew — P&L分布の歪度
- kurt — P&L分布の尖度（超過尖度）

計算式: Bailey & López de Prado (2014) の式に基づく。
正規分布の逆CDF と オーダー統計量の期待値を使用。

#### `deflated_sharpe_ratio(sr_observed, sr_benchmark, N, T, skew, kurt)`

DSR値（0〜1）を返す。

- sr_observed — 観測されたベストの Sharpe Ratio
- sr_benchmark — expected_max_sr() で算出した基準値
- 戻り値が 0.95 以上なら統計的に有意

内部で SR の標準誤差を skew/kurt から補正し、片側検定の p-value を算出。

### 既存ファイルの変更: `scripts/backtester/run_analysis.py`

各分析関数の末尾で DSR を自動計算・表示する。

対象:
- `analysis_ev_sim()` — EV式比較 (N=式の数) + alpha感度 (N=alphaリストの長さ)
- `analysis_time_filter()` — 時間フィルタ比較 (N=フィルタパターン数)

## 入力パラメータの算出方法

| パラメータ | 算出方法 |
|-----------|---------|
| sr_observed | 各パラメータ設定での trip P&L 系列から SR = mean/std * sqrt(annualization) で計算。ベスト値を使用 |
| N | 比較パラメータ数。コード内のリスト長から自動取得（alpha感度=8, 時間フィルタ=7, EV式=4） |
| T | trip 数。既に `build_trips()` で取得済み |
| skew | trip P&L の歪度。`scipy.stats.skew()` で算出 |
| kurt | trip P&L の超過尖度。`scipy.stats.kurtosis()` で算出 |

SR の年率化は trip 頻度ベース: `SR_annual = SR_per_trip * sqrt(trips_per_year)`

## 出力形式

各分析モードの結果末尾に1行追加:

```
DSR: 0.87 (N=8, T=127, SR_best=0.42) — ⚠ 閾値0.95未満: この改善は偶然の可能性あり
```

判定ルール:
- DSR >= 0.95 → `✓ 統計的に有意な改善`
- DSR < 0.95 → `⚠ 閾値0.95未満: この改善は偶然の可能性あり`

## 依存ライブラリ

- `scipy.stats` — norm.cdf, norm.ppf, skew, kurtosis
- 既存の依存に scipy が含まれていない場合は追加が必要

## スコープ外

- alpha_pipeline.py への組み込み（未配置のため）
- EXP_SUMMARY.md への試行回数N記録（別プロジェクトの関心事）
- CSCV (Combinatorially Symmetric Cross-Validation)（DSR導入後に必要性を再評価）
- 累積N（分析モード横断の合算）— 必要になったら後から追加
- hold_time 分析、close_dynamics 分析への DSR 適用（パラメータ比較を行わないモードのため不要）
