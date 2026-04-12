# FR Episode Analyzer 設計

## 目的

Bitget FR モニターが蓄積したスナップショット CSV を事後分析し、FR 機会の持続性・収益性を正しく評価する。現行 paper trader の FR 計算バグ（96倍水増し）とヘッジモデル不在を補正し、1ヶ月試用の GO/NO-GO 判定に使える数字を出す。

## 背景

### 現状の問題

1. **FR 収入 96倍バグ** — `fr_monitor.py:225-228` が FR を5分ポール毎に加算。実際は 8h に1回（00:00/08:00/16:00 UTC）
2. **ヘッジモデル不在** — paper trader は perp のみ追跡。price_pnl はヘッジなしの方向性リスク
3. **手数料閾値が甘い** — 往復 0.32%（perp 0.06% + spot 0.1% × 入出各1回）。FR 0.1%/8h では 24h で初めて回収

### ナレッジからの知見

- **FRASYM-ALT-002**（LiquidityGoblin）— モデル減衰「数週間で利益消失」→ decay 追跡が必須
- **Ilmanen エッジ帰属2分類** — 持続的 FR（リスクプレミアム型）vs スパイク FR（行動バイアス型）
- **DVOL Z-Score** — 後続フェーズでレジームフィルタとして検討。本設計のスコープ外

## アーキテクチャ

```
scripts/
  fr_monitor.py          ← 既存（変更なし）
  fr_analyzer.py          ← 新規：エピソード分析 CLI
  data_cache/
    fr_snapshots_*.csv    ← 入力（既存）
    fr_paper_trades.csv   ← 入力（参考、バグ含む）
    fr_episodes.csv       ← 出力（構造化エピソードデータ）
```

`fr_monitor.py` は変更しない。分析は蓄積された CSV に対するオフライン処理。

## コンポーネント設計

### 1. エピソード抽出エンジン

スナップショット CSV からシンボル別に「extreme FR エピソード」を構造化する。

**エピソードの定義** — あるシンボルが連続するポールで |FR| > threshold に出現し続ける期間。以下のいずれかで別エピソードに分割する:
- ポール間隔（デフォルト5分）の2倍（10分）以上のギャップ
- FR の符号反転（正→負 or 負→正）— トレード方向が変わるため

**各エピソードのフィールド:**

| フィールド | 型 | 説明 |
|-----------|-----|------|
| symbol | str | ペア名（例: IDUSDT） |
| direction | str | LONG（負FR）/ SHORT（正FR） |
| start_time | datetime | エピソード開始 |
| end_time | datetime | エピソード終了 |
| duration_minutes | float | 持続時間（分） |
| peak_fr | float | 期間中の最大 |FR| |
| mean_fr | float | 期間中の平均 |FR| |
| fr_windows_crossed | int | 00:00/08:00/16:00 UTC を跨いだ回数 |
| hedge_status | str | HEDGE_OK / NO_SPOT / NO_BORROW |
| volume_mean | float | 期間中の平均24h出来高（USD） |
| persistence_class | str | spike / single / persistent |

**持続性分類:**

| クラス | 条件 | 意味 |
|--------|------|------|
| spike | fr_windows_crossed == 0 | 次の FR 徴収前に消滅 |
| single | fr_windows_crossed == 1 | 1回分の FR 収入 |
| persistent | fr_windows_crossed >= 2 | 複数回の FR 収入 |

**実装方針:**
- 全日付の `fr_snapshots_*.csv` を読み込み、シンボル×タイムスタンプでソート
- シンボルごとに連続出現をグルーピング（10分ギャップで分割）
- FR payment window（00:00/08:00/16:00 UTC）の跨ぎ回数をカウント

### 2. 修正 P&L モデル

エピソードごとに「ヘッジ付き FR 裁定」の理論 P&L を算出する。

**前提:**
- delta neutral（perp + spot 両建て）→ price_pnl = 0
- FR 収入 = mean_fr × position_size × fr_windows_crossed
- 手数料 = position_size × fee_rate（往復）
- net_pnl = FR 収入 - 手数料

**損益分岐:**
- break_even_fr = fee_rate / fr_windows_crossed（fr_windows_crossed > 0 の場合）
- 各エピソードに profitable フラグを付与

**パラメータ（CLI 引数）:**

| 引数 | デフォルト | 説明 |
|------|-----------|------|
| --capital | 1000 | 投入資本 USD |
| --max-positions | 3 | 同時最大ポジション数 |
| --fee-rate | 0.0032 | 往復手数料率（perp+spot） |
| --fr-threshold | 0.001 | extreme FR 閾値（0.1%/8h） |

### 3. レポート出力

#### サマリー

```
=== FR Episode Analysis ===
  Period: 2026-04-11 — 2026-04-13 (2 days)
  Total episodes: 142
  HEDGE_OK: 31 (21.8%)
  Persistence: spike=98, single=28, persistent=16
```

#### 持続性クラス別集計テーブル

HEDGE_OK エピソードのみ対象:

```
  Class       Count  Mean FR   Mean Dur   Theory PnL  Profitable
  spike          18  0.142%      12min     -$3.20/ep      0.0%
  single          8  0.185%     6.2h       +$0.53/ep     62.5%
  persistent      5  0.231%    19.4h       +$3.81/ep     80.0%
```

#### what-if シミュレーション

```
=== What-if Simulation (capital=$1000, max_pos=3) ===
  Scenario                        Monthly PnL   Annual Return
  All HEDGE_OK                    -$12.40           -14.9%
  single+ HEDGE_OK only            +$8.30            +10.0%
  persistent HEDGE_OK only        +$19.05            +22.9%

Note: 同時刻に複数エピソードが競合する場合、mean_fr の高い順に max_positions 件まで選択。
```

#### CSV 出力

`data_cache/fr_episodes.csv` — 全エピソードの構造化データ。実行のたびに全件再生成（上書き）。冪等性を保証。

## CLI インターフェース

```bash
# 基本実行（全日付の蓄積データを分析）
python3 scripts/fr_analyzer.py

# 日付範囲指定
python3 scripts/fr_analyzer.py --start 2026-04-11 --end 2026-04-13

# パラメータ変更
python3 scripts/fr_analyzer.py --capital 3000 --fee-rate 0.0025

# CSV出力のみ（レポートなし）
python3 scripts/fr_analyzer.py --csv-only
```

## スコープ外（後続フェーズ）

- DVOL Z-Score レジームフィルタ連携
- fr_monitor.py へのリアルタイム持続性カウンター追加
- paper trader の FR バグ修正（analyzer が正しい数字を出すので優先度低）
- Bitget API 認証付きエンドポイント（実取引）

## 成功基準

1ヶ月分のデータで以下が判定できること:
- persistent + HEDGE_OK エピソードが月10件以上存在するか
- その理論 PnL が fee を上回るか（profitable 率 > 50%）
- 月間理論収益が $1000 資本で年率 10% 以上か
