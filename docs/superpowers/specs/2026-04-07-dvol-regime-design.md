# DVOL Z-Scoreレジームフィルタ（バックテスター）設計

## 概要

Deribit APIからBTC DVOL（インプライドボラティリティ指数）履歴データを取得し、
Z-Scoreベースでレジーム分類。高DVOL時の取引除外what-ifをDSR付きで検証する。

## 背景と目的

- v0.14.xの5日間データで「レンジ=黒字(+2.07/trip)、トレンド=赤字(-0.84/trip)」が明確
- 4/2のBTC -1.1%急落で-197 JPY（手動決済除外後）の損失
- DVOLはオプション市場由来のforward-lookingボラ指標（Deribitが世界のBTCオプション90%を取引）
- DVOL Z-Score ≥ 2 の時に取引を抑制すれば、トレンド日の損失を事前に回避できる可能性

## モジュール構成

### 新規: `scripts/backtester/dvol_fetcher.py`

Deribit公開APIからDVOLデータを取得しローカルキャッシュ。

#### `fetch_dvol(start_date, end_date, resolution="1h")`

- エンドポイント: `https://www.deribit.com/api/v2/public/get_volatility_index_data`
- パラメータ: `currency=BTC`, `start_timestamp`, `end_timestamp`, `resolution`
- 認証不要（公開API）
- 戻り値: `[{"timestamp": datetime, "open": float, "high": float, "low": float, "close": float}, ...]`
- キャッシュ: `scripts/data_cache/dvol/YYYY-MM-DD.json` に日単位で保存
- キャッシュがあればAPIを叩かない

### 新規: `scripts/backtester/dvol_regime.py`

DVOLデータとtripデータを組み合わせてレジーム分析。

#### `calc_dvol_zscore(dvol_data, lookback_hours=720)`

DVOL close値の移動平均・標準偏差からZ-Scoreを算出。

- lookback_hours: Z-Score計算のウィンドウ（デフォルト720h = 30日）
- 戻り値: `[{"timestamp": datetime, "dvol": float, "z_score": float}, ...]`

#### `classify_dvol_regime(zscore_data, z_threshold=2.0)`

Z-Scoreでレジーム分類。

- Z ≥ z_threshold → "high"
- Z ≤ -z_threshold → "low"
- それ以外 → "normal"
- 戻り値: `{"labels": {datetime: str}, "stats": {"mean": float, "std": float}}`

#### `analyze_by_dvol_regime(trips, dvol_regime_result, timeline)`

レジーム別P&L集計。tripのopen_fill時刻に最も近いDVOLデータポイントのレジームを使用。

戻り値: vol_regimeと同じ構造のリスト。

#### `calc_dvol_filter_impact(trips, dvol_regime_result, timeline, exclude_regimes)`

特定レジーム除外のwhat-if。vol_regimeのcalc_vol_filter_impactと同じインターフェース。

### 変更: `scripts/backtester/run_analysis.py`

- `analysis_dvol_regime()` 関数追加
- `--analysis dvol_regime` をchoicesに追加
- DVOLデータ取得 → Z-Score算出 → レジーム分類 → P&L集計 → what-if → DSR

## DVOLデータとtripの時刻マッチング

DVOLは1時間解像度、tripは秒単位。tripのopen_fill.timestampに対して:
1. DVOLデータを時刻順にソート
2. tripの時刻以前で最も近いDVOLデータポイントを使用（bisect）
3. DVOLデータがない時刻のtripは"normal"にフォールバック

## テスト

- dvol_fetcher: APIレスポンスのパース、キャッシュ読み書き
- dvol_regime: Z-Score計算、レジーム分類、P&L集計
- モックデータでテスト（実API呼び出しはテストでは行わない）

## 依存関係

- requests（HTTPクライアント、既にインストール済み）
- 既存backtesterモジュール（data_loader, market_replay, dsr）

## スコープ外

- bot本体（Rust）へのリアルタイムDVOL統合（バックテスト結果に基づく後続プロジェクト）
- DVOLのWebSocket購読
- ETH DVOLの取得
- DVOL先物の取引
