---
title: HL airdrop spec — 単一イベント戦略 5 要件カバレッジ自己評価
purpose: wiki `analyses/backtest-edge-validation-workflow-2026-05-28.md` §8 の 5 要件 (クロスセクショナル OOS 代替) で spec v7 / retro v0.5 をカバレッジ自己評価し、Step 2 入金前のギャップ把握 + spec v8 fed-back 候補抽出
status: v0.1 (2026-05-29 conoha 自己評価、mentor 5/29 prompt 由来)
parent: CLAUDE.md (軸2 HL airdrop 専用)
mentor_prompt: ~/Desktop/my mentor/prompts/2026-05-29-conoha-event-driven-5-requirements-check.md
wiki_source: ~/Desktop/CCナレッジ/wiki/analyses/backtest-edge-validation-workflow-2026-05-28.md §8
related:
  - docs/superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md (v7)
  - docs/hl-airdrop-s1-retro.md (v0.5)
---

# HL airdrop spec — 単一イベント戦略 5 要件カバレッジ自己評価

## 結論 (エグゼクティブサマリ)

**5 要件中 4 件 ◯ (完全カバー) + 1 件 △ (部分カバー)**。spec v7 §Gate 3 が「クロスセクショナル OOS 事前宣言式」として 5 要件を section 化済、構造的に整っている。**要件 5 (事後評価ループ) のみ △**: プロセスは存在 + retro v0.4 → v0.5 update で実行実績あり、ただし (a) 当たり/外れ log フォーマット未標準化、(b) prior 更新ルール (ベイズ or 別形式) 未確定 の 2 ギャップ。**Step 2 入金の阻害要因ではない** (技術判断レイヤーで完結可能)、ただし要件 5 補強を **spec v8 fed-back #9** として mentor に上申。

要件 2 / 3 / 4 に軽微補強案あり (validator/insurance 評点軸の追加、中サブセット閾値、Gate 2 ↔ Gate 3 発火順序)、いずれも spec v8 候補で Step 2 着手とは独立。

---

## 自己評価表

| # | 要件 | カバレッジ | spec 内の該当 section | ギャップ | 補足対応案 |
|---|---|---|---|---|---|
| 1 | サンプル事前宣言 | **◯** | spec v7 §Gate 3 要件 1 (L354-369) | なし (mentor 例示の Blur/Wormhole/Sui/Pyth/Celestia は未採用だが N=8 で十分性確保) | (任意、優先度低) v8 で N=10 拡張検討 |
| 2 | 比較可能性テスト | **◯** | spec v7 §Gate 3 要件 2 (L371-386) + retro v0.5 §7 (L314-326) | mentor 例示の **validator structure / insurance fund 評点軸** が Gate 3 比較可能性テストに未統合 (retro §12 Tail Safety 10 項目で別途あり) | v8 候補: Gate 3 評点表に validator/insurance 列を追加 |
| 3 | 層別閾値 | **◯** | spec v7 §Gate 3 要件 3 (L388-391) | **中サブセット閾値が未定義** (高 100% / 全 62% の 2 段、wiki §8 の「比較可能性低 = 緩め」表現に厳密対応せず) | v8 候補: 中サブセット ({JTO,JUP,APT,ARB,DYDX,UNI}) で 50% 以上ポジ等の中間閾値追加 |
| 4 | 反証条件 | **◯** | spec v7 §Gate 3 要件 4 (L393-397) | **Gate 3 反証条件と Gate 2 monitoring trigger (HF cluster / Insurance / Validator) の発火順序ルール未明示** | v8 候補: Gate 2 trigger が先行発火 → Gate 3 再評価着手、Gate 3 反証先行 → 戦略保留/破棄判定の優先順序を明文化 |
| 5 | 事後評価ループ | **△** | spec v7 §Gate 3 要件 5 (L399-403) + retro v0.4 → v0.5 update 実績 (§14 全 8 候補統合) | (a) `analyses/hyperliquid-airdrop-retro-2026.md` **(仮称、未作成)**、log フォーマット標準化なし<br>(b) prior 更新ルール (ベイズ or 単純頻度) **未確定** ("claude-bridge 側で検討中" のまま) | **★ spec v8 #9 候補として mentor 上申**: (1) log フォーマット template を spec v8 で確定 (2) prior 更新ルールを明文化 (3) HL2 配布完了直後の事後評価 (retro v0.5 → v0.6) プロセスを spec 末尾に annotation 追加 |

---

## 要件 1 — サンプル事前宣言 ◯

### 該当 section

spec v7 §Gate 3 要件 1 (L354-369):

| # | 事例 | 年 | 採用/除外理由 |
|---|---|---|---|
| 1 | UNI | 2020 | DEX エアドロの原点、形式的類似は低い |
| 2 | DYDX | 2021 | CEX→perp、参加形態は perp trade 類似 |
| 3 | APT | 2022 | chain-level、参加形態は低類似 |
| 4 | ARB | 2023 | L2、on-chain activity 条件、競合密度は類似 |
| 5 | JTO | 2023 | Solana DEX、HL エコシステムと構造的類似 |
| 6 | JUP | 2024 | Solana DEX aggregator、参加形態中類似 |
| 7 | EIGEN | 2024 | restaking、参加要件明確、HL に最も近い設計 |
| 8 | HL 第 1 弾 | 2024 | **最重要比較対象**。同プロトコルの前例 |

**除外理由明記**: FTX 絡みのエアドロ事例は取引所破綻の影響を受けているためサバイバーシップバイアス回避で除外。

### 評価根拠

- **N = 8 件 リスト化済** ✅
- **選定基準明記** ✅ (DEX / perp / chain-level / L2 / Solana / restaking / 同プロトコル前例)
- **除外基準明記** ✅ (サバイバーシップバイアス規則で FTX 絡み除外)

### ギャップ

なし。mentor 例示の Blur / Wormhole / Sui / Pyth / Celestia は未採用だが、N=8 で 4 つのカテゴリ (DEX, perp DEX, L2, restaking, chain-level) をカバーしており十分なサンプリング多様性。優先度低の追加候補として v8 で N=10 拡張は可能だが、Step 2 阻害要因ではない。

---

## 要件 2 — 比較可能性テスト ◯

### 該当 section

spec v7 §Gate 3 要件 2 (L371-386) + retro v0.5 §7 (L314-326)

| 事例 | プロトコル規模 | 参加形態類似 | 競合密度類似 | **総合** |
|---|---|---|---|---|
| HL1 | 高 | 高 | 高 | **高** |
| EIGEN | 高 | 中 | 高 | **高** |
| JTO | 中 | 高 | 中 | 中 |
| JUP | 高 | 中 | 中 | 中 |
| APT | 中 | 低 | 中 | 中 |
| ARB | 高 | 低 | 高 | 中 |
| DYDX | 中 | 高 | 低 | 中 |
| UNI | 高 | 低 | 低 | 中 |

**高サブセット = {HL1, EIGEN}** の 2 件確定。

### 評価根拠

- **4 軸評点 (プロトコル規模 / 参加形態類似 / 競合密度類似 / 総合) 実施済** ✅
- **高/中サブセット区別済** ✅
- **HL1 列に 1 次データ実測あり** (retro §7、Dune + ASXN 由来) ✅

### ギャップ (軽微)

mentor 例示の **validator structure / insurance fund 評点軸** は Gate 3 比較可能性テストに未統合。ただし retro §12 (Tail Safety 10 項目) で HL1 実績は #1 (清算バッファ), #2 (OI 上限), #3 (DDoS), #7 (中央集権) として別途評価済。Gate 3 評点軸に追加するなら spec v8 候補。

### 補足対応案

spec v8: Gate 3 比較可能性テスト評点表に **validator concentration 軸 (Top 1/3/5 share, HF-equivalent cluster ratio)** + **insurance fund 軸 (規模 / stablecoin diversification)** を追加し、HL1 列に retro v0.5 §12 のデータを反映。優先度: 低〜中 (Step 2 阻害要因ではない)。

---

## 要件 3 — 層別閾値 ◯

### 該当 section

spec v7 §Gate 3 要件 3 (L388-391)

- **高サブセット (HL1, EIGEN)**: **100% ポジティブ必須** (2/2)
- **全 8 件**: **62% 以上ポジティブ** (5/8 以上)

### 評価根拠

- **高サブセット閾値定義済** ✅
- **全件閾値定義済** ✅
- spec 事前宣言として明文化 ✅

### ギャップ (軽微)

**中サブセット閾値が未定義** (高/全のみの 2 段階)。wiki §8 の「比較可能性高サブセットで厳しめ、**比較可能性低サブセット (例: 一般 L2 エアドロ) では緩め**」表現に厳密対応していない。現状の中サブセット ({JTO, JUP, APT, ARB, DYDX, UNI}) は全件閾値 62% に統合されている。

### 補足対応案

spec v8: 中サブセット閾値を追加する場合、例えば「**中サブセット 6/8 中 50% 以上 (3/6) ポジ**」等の中間閾値を明示。優先度: 低 (現状の 2 段階でも反証機能は成立)。

---

## 要件 4 — 反証条件 ◯

### 該当 section

spec v7 §Gate 3 要件 4 (L393-397)

- 高サブセットの 1 件でもネガ → **Gate 3 FAIL 再検討 (戦略保留)**
- 全 8 件で 5 件未満ポジ → **Gate 3 FAIL (戦略破棄候補)**
- 両方 PASS なら **Gate 3 PASS として HL2 実行に進む**

### 評価根拠

- **FAIL 判定条件明記済** ✅
- 既存 Trigger 抵触条件 (HF cluster / Insurance / Validator / Bug bounty / TVL Top 3 / ToS / Regulatory / 第 2 弾アナウンス) は **Gate 2 monitoring layer** で網羅、weekly monitoring (`hl_monitoring_YYYYwXX.md`) で運用中
- Gate 3 反証 + Gate 2 monitoring trigger が二重チェック層として機能 ✅

### ギャップ (軽微)

**Gate 3 反証条件と Gate 2 monitoring trigger の発火順序ルール未明示**。例: 配布完了前に Gate 2 trigger (HF cluster >55% 継続 2 週) と Gate 3 反証 (高サブセット 1 件ネガ判定) が同時発火した場合、どちらが優先判定か。

### 補足対応案

spec v8: 発火順序の優先度ルールを明文化:
- Gate 2 trigger 先行発火 → 配分縮小 (B → C) + Gate 3 反証データ収集継続
- Gate 3 反証先行確定 → 戦略保留 / 破棄判定、Gate 2 monitoring 継続するが新規 touch 停止
- 両者同時発火 → 戦略破棄が優先

優先度: 中 (Step 2 入金後の monitoring 運用安定性に直結、ただし Step 2 入金前は影響なし)。

---

## 要件 5 — 事後評価ループ △ (★ 唯一の △ 評価)

### 該当 section

spec v7 §Gate 3 要件 5 (L399-403):
- HL2 配布完了後、実際の結果を `analyses/hyperliquid-airdrop-retro-2026.md` (**仮称、未作成**) に記録
- 比較可能性評点の事後 validation (想定外れ事例を log 化)
- 次のエアドロ戦略 spec の prior 更新に使用 (**ベイズ更新 rule は未確定、claude-bridge 側で検討中**)

retro v0.4 → v0.5 update プロセス実績 (§14 新設、2026-05-25):
- Step 1 実測 (候補 #3-5) + W21 以降 monitoring 由来 (候補 #1, #2, #6, #7, #8) の **全 8 候補を §14 に統合**
- HL2 配布前の中間 update として機能 — これは事後評価ループの先行プラクティス相当

### 評価根拠

**プロセス自体は存在 + 実行実績あり** ✅:
- retro 文書のバージョン管理規律 (v0.1 → v0.2 → v0.3 → v0.4 → v0.5) が確立済
- W17 以降の monitoring 由来 fed-back 8 候補が retro §14 で形式化
- spec v7 §Gate 3 要件 5 で「HL2 配布完了後に retro 化」の方針明示

### ギャップ (2 つ、要対応)

**(a) 当たり/外れ log フォーマット未標準化**:
- `analyses/hyperliquid-airdrop-retro-2026.md` は **仮称**、未作成
- 比較可能性評点 (8 事例 × 4 軸) の事後 validation テンプレートなし
- 「想定通り / 想定外れ / 判定不能」の 3 値カテゴリ標準化なし

**(b) prior 更新ルール (ベイズ or 別形式) 未確定**:
- "ベイズ更新 rule は未確定、claude-bridge 側で検討中" のまま
- 次回エアドロ戦略 spec (HL3 or 他プロトコル) で prior をどう更新するか未明文化
- 単純頻度更新 (8/8 ポジ → 100% prior) でも明示があれば運用可能

### 補足対応案 (★ spec v8 #9 候補として mentor 上申)

**spec v8 fed-back #9** として 3 アクション提案:

1. **log フォーマット template を spec v8 で確定** — 比較可能性 4 軸 × 8 事例の事後 validation テーブル雛形 + 「当たり/外れ/判定不能」3 値カテゴリ
2. **prior 更新ルールを明文化** — 推奨案: 単純頻度更新 (ポジ件数 / 全件数 = 次回 spec の prior) を default、ベイズ更新は将来オプション
3. **HL2 配布完了直後の事後評価プロセス** を spec v7/v8 末尾に annotation 追加 — retro v0.5 → v0.6 (or v1.0) bump のトリガ条件 + 期限 (配布完了から 14 日以内)

**優先度**: 中 (Step 2 入金は遮らないが、HL2 配布完了後の retro 化を確実にするため事前確定が望ましい)

---

## 判断レイヤーと次アクション

### conoha 単独判断で決定済 (技術判断レイヤー)

- 5 要件カバレッジ自己評価レポート (本書) 作成
- 要件 1 / 2 / 3 / 4 は **◯**、軽微補強は spec v8 候補で **Step 2 着手とは独立**
- 5/30 Step 1 経路 A 本実行に影響なし、6/15 月次レビュー判断依頼 5 項目に影響なし

### mentor 上申事項

**spec v8 fed-back #9 候補として要件 5 補強を上申**:
- (a) log フォーマット template 確定
- (b) prior 更新ルール明文化
- (c) HL2 配布完了直後の事後評価プロセス annotation

現在 mentor 判断待ち中の **spec v8 #8 (HF cluster trigger 閾値再校正)** とは独立、並列に判断可能。

### 既存 6/15 月次レビュー判断依頼 5 項目との関係

本レポートは **6 項目目 (spec v8 #9 候補) として追加** すべきか、それとも独立アーカイブとするかは mentor 判断。conoha 推奨: 6/15 月次レビュー報告書 `docs/mentor-monthly-review-20260615.md` v0.1 に **#6 として追記 (v0.2 bump)** が時系列的に効率的。

---

## 関連ドキュメント

- wiki ガイド: `~/Desktop/CCナレッジ/wiki/analyses/backtest-edge-validation-workflow-2026-05-28.md` §8
- 詳細フレーム: `~/Desktop/CCナレッジ/wiki/analyses/dsr-protocol-incentive-operations-guide-2026-04-20.md` Topic 3
- spec v7 §Gate 3: `docs/superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md` L348-411
- retro v0.5 §7 比較可能性評点: `docs/hl-airdrop-s1-retro.md` L314-326
- retro v0.5 §12 Tail Safety 10 項目: `docs/hl-airdrop-s1-retro.md` L437-489
- retro v0.5 §14 v0.4 → v0.5 update: `docs/hl-airdrop-s1-retro.md` L606+
- 6/15 月次レビュー報告書: `docs/mentor-monthly-review-20260615.md` v0.1
- mentor 5/29 prompt: `~/Desktop/my mentor/prompts/2026-05-29-conoha-event-driven-5-requirements-check.md`
