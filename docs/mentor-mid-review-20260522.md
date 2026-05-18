---
title: mentor 5/22 中間レビュー報告書 (conoha → mentor)
purpose: mentor 3軸役割再定義 (2026-05-18 確定) の Phase 3 移行進捗報告
status: v0.1 scaffold + session 16 patch (2026-05-18 session 14 初稿、2026-05-19 session 16 で section (3) v0.2.1 patch 反映、5/22 当日 v0.2 finalize 予定)
parent: CLAUDE.md (Phase 3 移行スケジュール)
mentor_prompt: ~/Desktop/my mentor/prompts/2026-05-18-conoha-role-redefinition.md
related:
  - CLAUDE.md
  - docs/hl-step1-route-checklist.md (v0.2.1)
  - docs/monitoring-migration-draft-20260518.md (v0.1)
  - scripts/data_cache/hl_monitoring_2026w21.md (v0.2 captured)
---

# mentor 5/22 中間レビュー報告書 — Phase 3 移行進捗

## エグゼクティブサマリ

**Phase 3 移行は順調**。5/18 mentor 確定の即時タスク 4/4 を 1 日で完了 (commit 2 件)、W21 monitoring も 5 週連続 Trigger 抵触ゼロを確認。VPS リソースは提供可能、ただし **Memory 88.1% (available 122 MB)** がボトルネックで各プロジェクト bot は 30-50 MB 以下に抑制が必要。**Step 1 ($10 経路検証) は 5/23 (土) 実行準備完了**。

---

## (1) 役割再定義反映状況

### 即時タスク 4/4 完了 (2026-05-18 session 13)

| # | タスク | 成果物 | commit |
|---|---|---|---|
| 1 | CLAUDE.md 新規作成 (3軸明示、役割境界、Phase 3 移行表) | `CLAUDE.md` 224 行 | `5a04c30` |
| 2 | VPS 状態確認 endpoint 実装 + deploy | `/api/admin/system-info`、psutil 経由 | `5a04c30` + `c0039a7` (pip 修正) |
| 3 | HL Step 1 checklist v0.2 update (spec v7 整合化 + 5/23 実行手順追記) | `docs/hl-step1-route-checklist.md` v0.2 | `5a04c30` |
| 4 | monitoring 移管準備ドラフト作成 | `docs/monitoring-migration-draft-20260518.md` v0.1 | `5a04c30` |

### 役割境界遵守 — 5 項目を CLAUDE.md に明文化

1. bot 本体 (FR/MM) の再着手禁止 (戦略開発は strategy-lab の役割)
2. VPS 上での独自戦略実装禁止 (conoha は基盤提供のみ)
3. HL airdrop 以外の戦略 spec 起票禁止
4. 各プロジェクト Claude のコード編集禁止 (デプロイ受け入れ側として動作)
5. ユーザー承認なしの実弾移動禁止 ($10 でも例外なし)

### W21 monitoring (本報告書送付直前、2026-05-18 採取)

**5 週連続 Trigger 抵触ゼロ、配分 B baseline 維持判断**。詳細は `scripts/data_cache/hl_monitoring_2026w21.md` v0.2。

| 主要指標 | W20 | **W21** | 変化 | 評価 |
|---|---|---|---|---|
| HYPE 価格 | $40.33 | **$45.9** | +13.8% | $45 boundary 初突破、配分 A 例外 ($60≥) まで距離 23% |
| Insurance HYPE | 44.14M | 44.32M | +0.40% | 5 週連続増加、healthy |
| Insurance USDE | $39,612 | **$9,812** | -75.2% | **5 週連続増加シナリオ棄却** (W17 baseline 回帰) |
| HF cluster | 53.62% | 53.89% | +0.27pt | 振動継続、>55% trigger 余裕 |
| Active validator | 24 | 24 | ±0 | <16 trigger 余裕大 |
| 第 2 弾アナウンス | 未公開 | 未公開 | — | 5 週連続未公開、spec v8 trigger なし |
| **新規 watch** | — | Anchorage By Figment stake -2.71pt | (#5 → #6) | W22 で reversal/継続判定 |

---

## (2) VPS リソース現状 + 提供可能容量

### 現状 (2026-05-18 採取、psutil 経由)

| 指標 | 値 | 評価 |
|---|---|---|
| OS | Windows 10, AMD64, node `vm-1593639a-5f` | — |
| CPU | 2 cores, 19.4% 使用 | ✅ 80%+ 余裕 |
| **Memory** | **1023.5 MB total / 901.9 used (88.1%) / available 121.6 MB** | ⚠️ **要 watch** |
| Disk C: | 99.9 GB / 26.99 used (27%) / **free 72.91 GB** | ✅ 十分 |
| 稼働日数 | 34.07 日 (≈ 4/14 から無再起動) | ✅ 安定 |
| プロセス数 | 92 | — |
| cloudflared.exe | pid 3096, RSS 15.6 MB | ✅ 稼働中 |
| python.exe (bot-manager) | pid 5964 (39.5 MB) + pid 6344 (3.5 MB) | ✅ 稼働中 |
| **gmo-bot.exe** | **検出されず** | ✅ v0.14.4 停止モード確定 (軸0 廃止裏付け) |

### 提供可能容量試算

| リソース | 結論 | 詳細 |
|---|---|---|
| **CPU** | ★ **余裕大** | scout + strategy-lab + sho-gun cron すべて並行可、現状 19.4% 使用 |
| **Disk** | ★ **十分** | 72 GB free で log 蓄積数年分、各プロジェクト 1-5 GB 配分可 |
| **Memory** | ⚠️ **ボトルネック** | available 122 MB、各プロジェクト Python プロセスは **30-50 MB 以下に抑制**、最大 2-3 プロセス追加が現実的 |

### 配分推奨 (Phase 3 移行先プロジェクト別)

| 移行対象 | プロセス型 | 推奨 RSS | 想定追加 Memory | 移行可否 |
|---|---|---|---|---|
| **scout cron (6/1 まで)** | Python cron + WebSearch | 30-50 MB | 30-50 MB | ✅ 可 |
| **strategy-lab Gate 2 HEIKIN bot (6/15 まで)** | Python long-running | 50-100 MB | 50-100 MB | ⚠️ **要 plan upgrade 判断** (現状 available 122 MB を圧迫) |
| **sho-gun note 自動公開 cron (6/11 以降)** | Python cron 軽量 | 20-30 MB | 20-30 MB | ✅ 可 |
| **strategy-lab Gate 3 通過戦略 (未定)** | Rust binary 想定 100-200 MB | 100-200 MB | 100-200 MB | ❌ **ConoHa plan upgrade 必須** (現 1 GB → 2 GB / 4 GB へ) |

### 結論

- scout + sho-gun の 2 プロジェクト並行は **現プラン (1 GB) で可能**
- strategy-lab Gate 2 bot 追加で **要 watch** (combined ~150 MB 追加、available 122 MB を超過する可能性)
- strategy-lab Gate 3 通過 (Rust binary) は **ConoHa plan upgrade 必須**、目安 2 GB or 4 GB プラン (現プランから +¥500-1000/月)

---

## (3) HL Step 1 準備状況

### checklist v0.2.1 完成 (`docs/hl-step1-route-checklist.md`、session 15 patch 反映)

- spec 参照を v5 → v7 に整合化 (v0.2)
- **5/23 (土) 実行手順セクション新設** (v0.2):
  - 事前 (朝): 国内取引所 JPY 残高 / MetaMask ETH gas / HL bridge contract address 確認
  - 当日: 5 区間 (JPY→XRP / XRP送金 / XRP→USDC / USDC出金Arbitrum / HL bridge) を順次実行
  - 完了後: evidence 保存 + mentor 報告書ドラフト
  - 中断条件: 任意区間で違和感 → ユーザー判断で打ち切り、$10 = ¥1,500 内で実損確定
- Step 2 配分金額を spec v7 baseline (HL $350 / BP $150) に修正 (v0.2)
- **★ session 15 (2026-05-19) で v0.2.1 patch 適用 — 事前準備 checklist 漏れ 2 件を塞いだ**:
  1. **国内取引所の送金先事業者リストに MEXC 登録済か** (トラベルルール対応、bitflyer / GMO 等で初回送金時に必須、未登録だと書類提出で数日遅延 → 5/23 前夜未完了なら経路②区間で詰む)
  2. **MEXC の Arbitrum USDC 出金が native USDC 対応か** (Token contract `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` を Arbiscan で照合、bridged USDC.e は HL bridge で受け取れない → 受け取り永久損失リスク)
- 5/23 前夜タスクとして 5 項目化 (元 3 → 5、native USDC 確認 + トラベルルール確認を追加)

### 5/23 実行体制

| 項目 | 担当 | 確認方法 |
|---|---|---|
| ユーザー承認 (各区間都度) | ユーザー | mentor 役割境界遵守、$10 でも例外なし |
| 経路遂行 | ユーザー手動 (ブラウザ UI) | conoha は Claude が checkpoint 助言のみ |
| evidence 保存 | conoha + ユーザー | `handoff/step1-evidence-2026-05-23/` 配下にスクリーンショット + tx hash |
| 完了後報告書 | conoha | mentor 用 (実測手数料 / 所要 / エラー有無 / HL 最終着金額) |

### 投入見積もり

- 投入: $10 = ¥1,500
- 想定総手数料: $2-4
- HL 最終着金見込: $6-8
- HL 最小預入 $5 USDC をクリア可能
- 所要時間: 40-75 min

### 落とし穴 (checklist v0.2 で明文化)

- HL bridge contract address (`0x2df1c51e09aecf9cacb7bc98cb1742757f163df7`) 必ず Arbiscan で確認 (誤送で永久損失)
- MetaMask Arbitrum 上に 0.001 ETH 以上 (gas 用) — 新規 wallet は別途 Arbitrum ETH 確保が必要
- MEXC の USDC 出金は **native USDC + Arbitrum network 限定** (bridged USDC.e 不可)

---

## (4) monitoring 移管準備

### 移管準備ドラフト v0.1 完成 (`docs/monitoring-migration-draft-20260518.md`)

### 分担定義

| 区分 | 担当 | 指標 |
|---|---|---|
| **scout 移管対象** (web 巡回ベース、軽量) | scout | HL 公式アカウント追跡 / HYPE 価格 / 第 2 弾アナウンス検出 |
| **conoha 継続** (spec v7 知見集中) | conoha | Insurance fund / Validator / Bug bounty / ToS / TVL Top 3 / HYPE 90d historical |
| **conoha 専担** (移管対象外) | conoha | Trigger 抵触最終判定 / 配分シナリオ判定 / spec v7 → v8 finalize / retro v0.4 → v0.5 update / 週次 monitoring ファイル編集 |

### 連携プロトコル (案)

- **毎週月曜**: scout が raw データ (HYPE 価格 / HL 公式新着 / アナウンス検出有無) を conoha が読める path に置く → conoha が Insurance / Validator 採取と統合 + Trigger 判定 + monitoring file 編集
- **即日 trigger** (アナウンス検出時): scout → conoha 通知 (mentor 経由 or file watch)

### 5/22 中間レビュー時の擦り合わせ論点 (mentor + scout + conoha)

1. データ受け渡し方法 (push vs pull)
2. アナウンス検出時の即日通知経路 (mentor 経由 vs file watch vs 別経路)
3. データ source 一致確認 (scout HYPE 価格 vs conoha 採取値)
4. scout 障害時の fallback 経路 (conoha が一時的に scout 担当指標を採取)
5. 5/22 → 6/1 までの試験移管 (並走で一致確認)

### 移管完了の判定基準 (案)

- scout が 4 週連続で安定採取 + conoha 採取値と整合
- scout 障害時の fallback 経路機能
- Trigger 検出時の通知経路機能
- → mentor 承認で正式移管

---

## (5) 6 月以降統合計画準備

### Phase 3 移行スケジュール (mentor 2026-05-18 確定)

| 日 | アクション | 担当 |
|---|---|---|
| 2026-05-22 | 中間レビュー (本報告書送付) | mentor + scout + conoha |
| **2026-05-23 (土)** | ★ HL Step 1 実行 ($10 経路検証) | conoha + ユーザー |
| 2026-06-01 | scout cron Mac→VPS 移行検討完了 | scout Claude + conoha |
| **2026-06-05** | strategy-lab Gate 2 結果報告、Mac→VPS 移行判断 | strategy-lab Claude + conoha |
| **2026-06-11** | sho-gun 案2' Day 30 売上判定、Mac→VPS 移行判断 | sho-gun Claude + conoha |
| 2026-06-15 | mentor 月次レビュー、conoha 役割再定義の総括 | mentor |
| HL 公式第 2 弾アナウンス検出後 | spec v8 finalize + Step 2 入金 | conoha + ユーザー |

### conoha からの依頼事項 (mentor 確認待ち)

1. **strategy-lab Gate 2 bot の Memory 想定値**: 50-100 MB 以下に抑制可能か (現プラン available 122 MB の制約)、超える場合は ConoHa plan upgrade のタイミング判断
2. **scout cron の VPS 移行時の cron 設定方法**: Windows Task Scheduler 経由 or nssm サービス化 (現 bot-manager と同方式) のいずれが scout Claude にとって運用しやすいか
3. **5/22 中間レビュー時の各プロジェクト Claude 同席方式**: scout Claude 同席は確定、strategy-lab Claude / sho-gun Claude は同席か mentor 経由報告か
4. **GMO bot 軸0 廃止に伴う資金 (13,060 JPY) の扱い**: 出金して別用途 (HL airdrop 軍資金 / 別プロジェクト) に振り向けるか、当面 GMO 口座放置か (5/22 ユーザー判断確認)

### conoha が 5/22 以降に着手予定

- W21 monitoring 結果を踏まえた retro v0.5 候補項目整理 (HYPE $45 boundary 初突破 / Anchorage stake 動向 / Insurance USDE 棄却)
- scout 擦り合わせ後の monitoring 移管プロトコル確定 (5/22 → 6/1 試験移管期間)
- 5/23 Step 1 実行 + 完了後報告書作成
- Step 1 結果反映 retro v0.4 → v0.5 update (5/23 後)

---

## 付録

### git 状態 (2026-05-18 session 13 末尾)

- 直近 commit:
  - `c0039a7` fix: self_update pip コマンドを sys.executable -m pip に変更
  - `5a04c30` feat: mentor 3軸役割再定義反映 (Phase 3 conoha 役割正式化)
  - `03ad25c` chore: gitignore に .claude/settings.json 追加

### 関連ドキュメント

- `CLAUDE.md` — プロジェクト 3軸役割定義
- `docs/hl-step1-route-checklist.md` (v0.2.1、session 15 patch 反映済)
- `docs/monitoring-migration-draft-20260518.md` (v0.1)
- `scripts/data_cache/hl_monitoring_2026w21.md` (v0.2、W21 採取完了)
- spec: `docs/superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md` (v7)
- retro: `docs/hl-airdrop-s1-retro.md` (v0.4)
- mentor prompt: `~/Desktop/my mentor/prompts/2026-05-18-conoha-role-redefinition.md`

### 報告書 v0.2 化のトリガ (5/22 当日)

- mentor + scout + conoha 3 者擦り合わせ結果を section (4) に追記
- 5/22 当日新規確認事項を section (5) 「conoha からの依頼事項」に反映
- W21 monitoring 5/18 採取結果は本書 section (1) で簡潔触れ済、W22 採取が 5/22 後なら post-review に保留
