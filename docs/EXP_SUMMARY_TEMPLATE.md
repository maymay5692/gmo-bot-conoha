# EXP_SUMMARY Template (v1.0, 2026-04-22)

実験（バックテスト・paper trade・本番運用 1 期分）ごとに 1 つの EXP_SUMMARY ファイルを起こす。ファイル名: `EXP_SUMMARY_<strategy-id>_<YYYY-MM-DD>.md` を推奨。

**典拠**:
- `wiki/analyses/dsr-protocol-incentive-operations-guide-2026-04-20.md` Topic 1
- `wiki/concepts/deflated-sharpe-ratio.md` N_trials 判定表
- `wiki/sources/false-strategy-theorem-dsr.md` 決定事項 (2)「試行回数 N を必須フィールド」

## 使い方

1. 本テンプレートをコピーして `EXP_SUMMARY_<id>_<date>.md` として保存
2. YAML フロントマター + 各セクションを埋める
3. **FAIL 判定の実験も全件ログに残す**（false-strategy-theorem-dsr 決定事項 3）
4. DSR 計算は `scripts/dsr_check.py --auto-n-trials --n-params N --universe-filter-source ex-ante|ex-post [--prior-universe-size P --final-universe-size F]` で実行し、JSON 出力を `result_json_path` に記録

---

## テンプレート本体

```markdown
---
strategy_id: <unique-id>          # 例: mexc-fr-basket, hl-airdrop-pivot
phase: <gate-0 | gate-1 | gate-2 | gate-3 | live>
date: YYYY-MM-DD                  # 実験実施日
verdict: <PASS | FAIL | PARTIAL | INSUFFICIENT_DATA>
result_json_path: <path to dsr_check.py --output JSON>

# --- DSR 必須フィールド (analyses Topic 1) ---
trials:
  n_params: <int>                 # 試したパラメータ組合せ数
  universe_filter_source: <ex-ante | ex-post>
  prior_universe_size: <int>      # ex-post 時: 事前候補銘柄数、ex-ante は 1
  final_universe_size: <int>      # ex-post 時: 最終選定銘柄数、ex-ante は 1
  n_trials_effective: <int>       # count_n_trials() の結果

# --- Protocol Incentive 両シナリオ (analyses Topic 2) ---
protocol_incentive:
  applicable: <true | false>
  sharpe_incentive_on: <float | null>
  sharpe_incentive_off: <float | null>
  dsr_incentive_on: <float | null>
  dsr_incentive_off: <float | null>
  fee_rate_baseline: <float>      # CSV に焼き込まれた orig fee
  fee_rate_override: <float|null> # インセンティブ replay 時の新 fee
---

# <strategy-id> Experiment Summary (<date>)

## 仮説

<1-3 行で何を検証したかを記述>

## サンプル

- データソース: <CSV path, paper trade 期間, IS/OOS split>
- n (close trades): <int>
- 期間: <start> → <end>

## Gate 1 結果

<scripts/dsr_check.py の出力を貼り付けるか result_json_path を参照>

| 指標 | 値 | 閾値 | 判定 |
|---|---|---|---|
| Sharpe (trade) | | >= 0.5 | |
| PSR | | >= 0.95 | |
| DSR (N_eff) | | >= 0.95 | |
| Skewness | | (記録のみ) | |
| Kurtosis (excess) | | (記録のみ) | |
| Concentration top-2 | | 要注意 > 50% | |

## Protocol Incentive 両シナリオ (該当する場合)

| シナリオ | Sharpe | DSR (N_eff) | 判定 |
|---|---|---|---|
| incentive ON | | | |
| incentive OFF | | | |

インセンティブ喪失時の戦略耐性:
<分析コメント>

## Gate 2 Tail Safety (該当フェーズのみ)

<詳細は戦略の spec を参照。ここでは要点のみ記述>

## Gate 3 OOS 再現性

- 時系列 split: IS=<n>, OOS=<n>, OOS Sharpe=<float>
- クロスセクショナル OOS (単一イベント戦略時):
    - サンプル事前宣言: <N 件、ファイル参照>
    - 高サブセット閾値: <層別条件>
    - 反証条件: <FAIL 条件>
    - 事後評価ループ: <次回更新予定>

## 所見

<具体的な観察、異常値、次のステップ>

## 関連ファイル

- spec: docs/superpowers/specs/<spec-file>.md
- 結果 JSON: <result_json_path>
- wiki 典拠: wiki/analyses/dsr-protocol-incentive-operations-guide-2026-04-20.md

## 次アクション

1. <具体的なフォローアップ>
```

---

## 記入例 (MEXC FR basket, 2026-04-20)

```markdown
---
strategy_id: mexc-fr-basket
phase: gate-1
date: 2026-04-20
verdict: FAIL
result_json_path: /tmp/mexc-gate1-baseline.json

trials:
  n_params: 5                     # funding_threshold × 2, hedge_mode × 2, plus baseline
  universe_filter_source: ex-ante # MEXC 上の全 perp から FR 絶対値上位 85 を固定
  prior_universe_size: 1
  final_universe_size: 1
  n_trials_effective: 5

protocol_incentive:
  applicable: true
  sharpe_incentive_on: 0.996
  sharpe_incentive_off: 0.996     # fee-free replay でも変化なし (既に fee 込み計算)
  dsr_incentive_on: 0.42
  dsr_incentive_off: 0.42
  fee_rate_baseline: 0.0002
  fee_rate_override: 0.0
---
```

---

## FAQ

### Q. ex-post 選定の場合、n_params はどう数える？

A. 以下 2 段階:
1. count_n_trials で `n_params × (log2(prior/final) + 1)` を計算
2. `n_trials_effective` に入れる (個別の n_params と universe filter は別途記録)

### Q. Protocol Incentive が applicable=false とは？

A. 戦略のエッジがリスクプレミアム型または行動バイアス型のみで、プロトコルからの報酬（ポイント/エアドロ/リベート）を**含まない**場合。該当時は sharpe_incentive_on = sharpe_incentive_off、fee 系フィールドは null でよい。

### Q. FAIL 実験もファイル化する？

A. **する**。`verdict: FAIL` で記録する。[`sources/false-strategy-theorem-dsr.md`](../wiki/sources/false-strategy-theorem-dsr.md) の決定事項 3「FAIL 判定の戦略も全件ログに残す」に準拠。FAIL の積み重ねが後続の N_trials 評価の実体データとなる。

### Q. HL エアドロのような単一イベント戦略は？

A. Gate 1 の trials は「戦略インスタンス単位」で N=5 程度（touch 頻度・金額・分散プロトコル数の暗黙比較）。Gate 3 の OOS はクロスセクショナル OOS フレーム（`wiki/concepts/3-gate-review.md` の「単一イベント戦略の Gate 3」節）で代替。spec 本体の事前宣言 5 要件と合わせて読む。

---

## 関連

- `scripts/dsr_check.py` — `count_n_trials` 実装、`--auto-n-trials` で自動記録
- `scripts/backtester/dsr.py` — DSR 核算
- `docs/superpowers/specs/2026-03-29-dsr-introduction-design.md` — DSR 導入設計
- `docs/superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md` — HL エアドロ spec（本テンプレの典型適用例）
- wiki `analyses/dsr-protocol-incentive-operations-guide-2026-04-20.md`
- wiki `concepts/deflated-sharpe-ratio.md`
