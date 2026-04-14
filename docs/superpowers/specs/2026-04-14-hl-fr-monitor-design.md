# Hyperliquid FR Monitor 設計

## 目的

Bitget FR モニターと並行して Hyperliquid の FR データを収集し、DEX vs CEX の FR 分布・持続性を比較可能にする。

## アーキテクチャ

```
scripts/
  fr_monitor.py          ← 既存 Bitget（変更なし）
  hl_fr_monitor.py       ← 新規 Hyperliquid
  fr_analyzer.py         ← --source フラグ追加
  data_cache/
    fr_snapshots_*.csv   ← Bitget データ
    hl_fr_snapshots_*.csv ← Hyperliquid データ
    fr_episodes.csv      ← 分析出力
```

## hl_fr_monitor.py

### API

- **Base URL**: `https://api.hyperliquid.xyz/info`（POST、認証不要）
- **全ペア一覧**: `{"type": "meta"}` → `universe` 配列（name, szDecimals, maxLeverage）
- **FR + マーケットデータ**: `{"type": "metaAndAssetCtxs"}` → 各ペアの funding, markPx, oraclePx, openInterest, dayNtlVlm

### 動作

1. 起動時に `meta` で全ペア一覧を取得
2. 5分間隔で `metaAndAssetCtxs` をポーリング
3. |funding| > 0.001 (0.1%/8h) のペアを CSV に書き出し
4. 100ポールごとにペア一覧を再取得

### CSV フォーマット

`data_cache/hl_fr_snapshots_{YYYY-MM-DD}.csv`

| カラム | 型 | 説明 |
|--------|-----|------|
| timestamp | ISO8601 | UTC |
| symbol | str | ペア名（例: ETH） |
| funding_rate | float | 現在の FR |
| annualized | float | FR * 3 * 365 * 100 |
| volume_24h | float | dayNtlVlm (USD) |
| open_interest | float | OI (USD) |
| hedge_status | str | 常に "UNKNOWN" |
| mark_price | float | Mark price |
| oracle_price | float | Oracle price |

### CLI

```bash
python3 scripts/hl_fr_monitor.py                    # デフォルト 5分間隔
python3 scripts/hl_fr_monitor.py --interval 60       # 60秒間隔
python3 scripts/hl_fr_monitor.py --report            # 蓄積データのサマリー
caffeinate -i python3 scripts/hl_fr_monitor.py       # Mac スリープ防止
```

### スコープ外

- Paper trading（データ収集のみ）
- Hedge classification（Hyperliquid の spot/借入構造は未調査）
- WebSocket（REST ポーリングで十分）

## fr_analyzer.py の変更

### --source フラグ

| 値 | 動作 |
|-----|------|
| bitget（デフォルト） | `fr_snapshots_*.csv` を読む（既存動作） |
| hl | `hl_fr_snapshots_*.csv` を読む |
| all | 両方読んで source カラム付きで統合分析 |

### 変更箇所

- `load_snapshots()` にプレフィックスパラメータ追加
- `main()` の argparse に `--source` 追加
- Episode に `source` フィールド追加（"bitget" or "hl"）
- レポートで source 別集計を表示（`--source all` 時）

### CSV 互換性

Hyperliquid の CSV は Bitget と一部カラムが異なる（has_spot/can_borrow がない、open_interest/oracle_price がある）。`load_snapshots()` は共通カラム（timestamp, symbol, funding_rate, volume_24h, hedge_status）のみ使用するため互換。

## 成功基準

- Hyperliquid の全 perp ペアの FR を 5 分間隔で収集できる
- 1ヶ月後に `fr_analyzer.py --source all` で Bitget vs Hyperliquid の比較レポートが出る
