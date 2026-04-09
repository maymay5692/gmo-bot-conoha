"""GMO Bot バックテスター - 実際のCSVデータを使ったリプレイ・what-if分析。

モジュール構成:
  data_loader    - データ読み込み・パース・Trip構築
  market_replay  - 市場状態タイムライン・補間
  ev_formulas    - EV計算式群
  trip_analyzer  - トリップ分析・what-if
  decision_sim   - EVパラメータシミュレーター
  metrics_sim    - 24h Market Hoursシミュレーション (EV-to-P&L比率スケーリング)
  dsr            - Deflated Sharpe Ratio (多重比較バイアス補正)
  vol_regime     - ボラティリティレジーム分析 (パーセンタイル分類・what-if)
  min_hold_sim     - min_hold（最低保持時間）シミュレーション
  dvol_fetcher     - Deribit DVOL データ取得・キャッシュ
  dvol_regime      - DVOL Z-Scoreレジーム分析
  close_fill_sim   - クローズ約定シミュレーター (SimResult, calc_close_price, calc_fill_prob)
  run_analysis     - CLI分析エントリポイント
"""
