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
  run_analysis   - CLI分析エントリポイント
"""
