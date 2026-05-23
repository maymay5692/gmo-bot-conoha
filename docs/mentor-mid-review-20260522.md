---
title: mentor 5/22 中間レビュー報告書 (conoha → mentor)
purpose: mentor 3軸役割再定義 (2026-05-18 確定) の Phase 3 移行進捗報告
status: **v0.2 finalize + 5/24 mentor (1)-(5) 回答反映** (session 22 = 2026-05-24、(5) スケジュールのみ実質変更: 任意整理 5/24 → 5/28 延期、Step 1 5/30 維持、(1)-(4) は conoha 判断 OK 承認のみ)。基底 = v0.2 finalize (2026-05-22 中間レビュー B1-B5 mentor 確定反映、session 21 = 2026-05-23 で finalize 化): B1 経路 A 採用承認 ◎ / B2 Step 1 = 5/30 (土) 確定 / B3 XRP 50 = JPY 戻し採用 / B4 retro v0.5 #7/#8 起票 + spec v7 §Step 1 章末 annotation + ハンドオフ誤記訂正 (50×2 → 30+20=50) / B5 monitoring 試験並走 5/22→6/1。過去履歴: 2026-05-18 session 14 初稿、2026-05-19 session 16 で section (3) v0.2.1 patch + GMO 確定情報反映 + section (5) #4 部分回答、2026-05-20 session 19 で section (3) ユーザー TODO #5/#6/#8 不明 + 5/30 延期 option 併記 draft、2026-05-21 session 20 で section (3) #6/#8 完了 + MEXC 出金条件実測 + 両構え採用、2026-05-21 09:41 で section (3) 緊急 update: GMO 拒否で経路再設計、2026-05-22 中間レビュー本番でパート B 完了 → 2026-05-23 session 21 finalize、2026-05-24 session 22 で mentor (1)-(5) 回答反映 (スケジュール微修正のみ)
parent: CLAUDE.md (Phase 3 移行スケジュール)
mentor_prompt: ~/Desktop/my mentor/prompts/2026-05-18-conoha-role-redefinition.md
related:
  - CLAUDE.md
  - docs/hl-step1-route-checklist.md (v0.2.2)
  - docs/step1-user-prep-guide-20260520.md (v0.1、session 19 新規作成)
  - docs/monitoring-migration-draft-20260518.md (v0.2)
  - scripts/data_cache/hl_monitoring_2026w21.md (v0.2 captured)
---

# mentor 5/22 中間レビュー報告書 — Phase 3 移行進捗

## エグゼクティブサマリ

**Phase 3 移行は順調、Step 1 は経路 A 採用承認 ◎ + 5/30 (土) 確定**。5/18 mentor 確定の即時タスク 4/4 を 1 日で完了 (commit 2 件)、W21 monitoring も 5 週連続 Trigger 抵触ゼロを確認。VPS リソースは提供可能、ただし **Memory 88.1% (available 122 MB)** がボトルネックで各プロジェクト bot は 30-50 MB 以下に抑制が必要。**★ Step 1 ($10 経路検証) は 5/21 09:41 GMO → MEXC 構造的拒否で 5/23 強行を中止、Explore subagent web 調査 → 代替経路 A 採用 (bitbank → MetaMask → Across → Arbitrum → HL bridge、手数料 $1.5-6, 所要 20-40 min、KYC 不要、user bitbank 既存活用)、Step 1 真のコスト $14-16 → $6-8 に大幅減**。**5/22 中間レビュー B1-B5 mentor 確定: B1 経路 A ◎ / B2 Step 1 = 5/30 (土) / B3 XRP 50 = JPY 戻し / B4 retro v0.5 #7/#8 + spec v7 §Step 1 annotation / B5 monitoring 試験並走 5/22→6/1**。詳細は section (3) ★ 09:41 緊急 update + ★ 5/22 B1-B5 mentor 確定 + section (4) v0.2 final 参照。

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

### ★ 2026-05-19 PM update (session 16 内、ユーザー確認結果反映)

| 項目 | 確定内容 |
|---|---|
| **国内取引所** | **GMO コイン確定** (本 bot 用既存口座、KYC 完了済、SBI VC Trade はアカウント未開設判明し選択肢から除外) |
| **トラベルルール** | **GMO で MEXC 宛 XRP 送付の登録申請完了、5/19 時点で審査中** (通常 1-2 営業日、5/21-5/22 完了見込) |
| **Step 1 資金源** | **GMO 既存 13,060 JPY から $10 = ¥1,500 を流用** (別途入金不要、軸0 廃止後資金の最適活用) |
| **5/23 スケジュール** | **維持** (審査完了見込前提)、5/22 朝に審査完了確認、不完了なら 5/30 (土) 延期判断 |
| **GMO 残資金** | **11,560 JPY ($77)** が残る、扱いは section (5) #4 案件 (GMO bot 軸0 廃止後資金) の継続論点として持ち越し |

### ★ 2026-05-20 update (session 19、ユーザー TODO 進捗確認結果 + 5/30 延期 option 併記)

#### ユーザー側 TODO 4 件の進捗確認結果 (2026-05-20 session 19 で確認)

| TODO | 状態 | 5/23 実行への影響 |
|---|---|---|
| #4 MetaMask wallet | ✅ 既存利用中 + seed phrase 保管済 | 影響なし、そのまま 5/23 使用可 |
| **#5 Arbitrum ETH 0.001+ (gas 用)** | ❌ **未保有 + 入手手順不明** | 区間⑤ HL bridge deposit が gas 不足で実行不可、$3-4 相当の別途調達必要 |
| **#6 HL bridge contract Arbiscan 照合** | ❌ **手順不明** | 5/23 当日に初見で実施は誤送リスク、事前照合推奨 |
| **#8 MEXC native USDC + Min withdrawal 実測** | ❌ **手順不明** | 区間④ 出金可否判定 + Minimum > $7 で 5/30 延期判定の根拠 |

#### conoha 対応 (5/20 session 19)

1. **ユーザー側準備 guide 新規作成**: `docs/step1-user-prep-guide-20260520.md` v0.1、#5/#6/#8 をブラウザ UI 操作レベルで平易化 (各手順 5-30 分、5/20-21 実施目標)
2. **mentor 報告書 section (3) に「5/30 延期 option」併記** (本 update)、5/22 中間レビューで mentor 判断材料を提供
3. **5/22 朝までの完了確認 protocol**:
   - 3 件すべて完了 → 5/23 強行確定
   - 1 件でも未完了 → **5/30 (土) 延期** 推奨

#### Step 1 真のコスト見直し ($10 投入は USDC 移動コストの検証のみ、別途必要)

| 項目 | 金額 | 補足 |
|---|---|---|
| Step 1 投入額 (USDC 経路) | $10 = ¥1,500 | GMO から流用、session 16 確定 |
| **Arbitrum ETH gas (別途必要)** | **$3-4 相当** | MetaMask Arbitrum に 0.001 ETH、区間⑤ deposit tx 用 |
| **ETH 入手の出金手数料** | **$1-2** | MEXC ETH 出金手数料 (時期により変動) |
| **Step 1 真のコスト合計** | **$14-16** | $10 + $4-6 = 約 ¥2,100-2,400 |

これは spec v7 で当初想定 (経路試算 $6.5-8.0 着金見込) には **gas 費用が含まれていなかった盲点** であり、retro v0.5 候補項目として記録すべき。

#### 5/30 延期判定の根拠 (mentor 5/22 判断事項)

以下のいずれかが該当する場合、5/23 強行ではなく 5/30 (土) 延期を **推奨**:

1. ユーザー TODO #5/#6/#8 のいずれか 1 件でも 5/22 朝までに完了できない
2. GMO トラベルルール審査が 5/22 PM までに承認されない
3. MEXC USDC Minimum withdrawal が $7 を超え、$10 投入の経路検証で詰むリスクが顕在化
4. ユーザーの 5/23 体調 / 時間確保が困難

**5/30 延期で得られるリードタイム**:

- 5/24 (日)-5/29 (金) の 6 日間で TODO 解説の再確認 + 実施
- 5/29 (金) 夜に最終チェック → 5/30 (土) 朝実行
- リスク低減: 手順理解 + リードタイム確保 + 5/22 中間レビュー結果反映時間
- Step 1 経路検証の主目的 (HL bridge 経路 / 手数料実測 / Step 2 入金判断材料) は 5/30 実行でも同等に達成可能

#### conoha の推奨スタンス (mentor 5/22 確認用)

- 5/22 朝までに **ユーザー TODO 3 件完了 + GMO トラベルルール承認 + MEXC Min ≤ $7** がすべて揃えば → 5/23 強行
- いずれか 1 件でも欠ければ → **5/30 延期推奨** (リスク低減 + リードタイム確保)
- mentor 判断: 上記スタンスを採用するか、5/22 当日に再評価するか

### ★ 2026-05-21 09:14 update (session 20 前半、#6/#8 完了 + 両構え採用)

> ⚠️ 本 subsection の判定 (Option A 着手 + 5/22 朝着金確認で 5/23 強行 or 5/30 延期) は **下記「★ 2026-05-21 09:41 緊急 update」で覆る**。GMO → MEXC 送付が構造的に拒否されたため、Option A 自体が不成立。本 subsection は時系列記録として残す。

#### 進捗 (2/3 完了、5/21 朝 session 20 で user 実施)

| TODO | 状態 | 結果 |
|---|---|---|
| #4 MetaMask wallet | ✅ (5/20 確認済) | — |
| **#5 Arbitrum ETH 0.001+** | **未着手 → 5/21 朝 Option A 着手判断** | 本 update 下記参照 |
| **#6 HL bridge Arbiscan 照合** | ✅ **5/21 完了** | `Hyperliquid: Deposit Bridge 2` nametag (Kleros Curate) + Source Code Verified Exact Match (Bridge2.sol v0.8.9 MIT) + Multichain $3.84B + 累計 3.64M tx + Hyperliquid: Validator 1/3/4 からの Batched Deposit active → 本物 bridge 稼働確認、誤送リスク消滅 |
| **#8 MEXC native USDC + Min** | ✅ **5/21 完了** | Token contract `0xaf88d...e5831` 一致 (native 確定) + **Min withdrawal = 2 USDC** ($7 以下、経路詰まりリスク消滅) + 出金手数料 **0.0043 USDC ($0.004)** (想定 $1-2 比で大幅安) |

#### #5 戦略 — 両構え採用 (Option A 着手 + 5/30 延期 option 維持)

- **Option A 着手** (5/21 朝以降 user 実施): GMO で XRP $5-10 購入 → MEXC へ送金 (5/19 申請の登録アドレス + DestinationTag 必須) → MEXC で XRP→USDT→ETH 交換 → MEXC から ETH を **Arbitrum One** ネットワークで MetaMask Arbitrum address へ出金 → 0.001 ETH+ 着金確認
- **判定タイミング**: 5/22 朝 着金確認時点で
  - **着金済** → 5/23 強行
  - **未着金** → **5/30 (土) 延期**
- 前提: GMO トラベルルール審査 (5/19 PM 申請) が 5/21-22 朝までに承認されること (2 営業日経過済、5/22 朝確認予定)

#### Step 1 真のコスト試算微修正

| 項目 | session 19 試算 | 5/21 実測反映 | 補足 |
|---|---|---|---|
| MEXC USDC 出金手数料 | $1-2 | **$0.004** (0.0043 USDC) | 想定より $1-2 安い |
| Step 1 真のコスト合計 | $14-16 | **$13.5-15.0** | 微修正、ETH 入手系 (ETH $3-4 + MEXC ETH 出金手数料 $1-2) が依然支配的 |

#### 経路詰まりリスクの整理 (5/21 update)

| リスク | 5/20 時点 | 5/21 update |
|---|---|---|
| 区間④ MEXC Min 不足 | 未確認 | **解消** (Min $2 実測) |
| 区間⑤ HL bridge 誤送 | 未確認 | **解消** (本物 bridge 確認) |
| 区間⑤ ETH gas 不足 | リスクあり | **未解消** (Option A 着手中、5/22 朝判定) |
| GMO トラベルルール審査 | 審査中 | 5/22 朝確認予定 |

→ **残課題 = 2 項目** (#5 ETH 着金 + GMO 審査承認)、5/22 朝にこの 2 項目 clear で 5/23 強行確定、片方欠ければ 5/30 延期

#### conoha の推奨スタンス update (5/21)

- 5/20 時点: 「TODO 3 件揃わなければ 5/30 延期推奨」(qualified)
- **5/21 時点**: 「#6/#8 完了で経路詰まりリスク消滅、残るは #5 ETH 着金 + GMO 審査承認のみ。両方 clear で 5/23 強行、片方欠ければ 5/30 延期推奨」
- Option A 着手は 5/23 強行確率を上げる行動、ただし MEXC balance ゼロからの出金審査リードタイムで 5/22 朝着金が間に合わない可能性あり (両構えの本質)

### ★ 2026-05-21 09:41 緊急 update (session 20、GMO → MEXC 構造的拒否で 5/23 強行不可 + 経路再設計必須)

#### 緊急事実関係

5/21 朝 user が Option A (#5 ETH 入手) 着手の一環として GMO で XRP 50 購入 → MEXC 宛送付を試行した結果、**GMO 側で構造的に拒否** されたメール 2 通受信:

| 時刻 | イベント |
|---|---|
| 09:30 | XRP 30 約定 (GMO 内購入、送信試行) |
| 09:35 | GMO 送付拒否メール (1 回目) |
| 09:39 | XRP 20 追加約定 (最低送信単位 50 に合わせるため、user 再試行) |
| 09:41 | GMO 送付拒否メール (2 回目、同文) |

→ 累計 XRP **50 保有** (5/22 01:23 GMO API 実測と一致、5/22 中間レビュー B4-2 でハンドオフ誤記「各 50 × 2 = 100」を訂正)

- 拒否理由: 「当社ではトラベルルールに基づく対応として、法律等によって求められる通知を行えない取引所 (暗号資産交換業者) 宛への暗号資産の送付をお断りしております」
- 1 次ソース: https://support.coin.z.com/hc/ja/articles/18617534062617
- 銘柄: XRP、宛先: MEXC、累計約定 50 XRP (30 + 20、2 回試行)

これは **「審査中」ではなく構造的拒否**。session 16 PM update で「5/19 PM 申請、5/21-22 完了見込」と判定した内容は誤りで、**送付先アドレス登録自体は完了したが送付実行段階で GMO トラベルルール対応プロトコル (TRP / Sumsub) と MEXC の通知要件未対応のため永久拒否**。

#### 影響評価

| 項目 | 判定 |
|---|---|
| **5/23 強行** | **完全に不可能** (経路②の出発点 GMO → MEXC で詰む) |
| **5/30 延期** | **MEXC 経路継続なら非現実的** (代替取引所立ち上げ KYC 数日〜1 週間) |
| **金銭損失** | **なし** (XRP 50 累計、GMO 内残留、5/22 B3 確定 = JPY 戻し採用) |
| **spec v7 / retro v0.4 への波及** | **根本盲点**、retro v0.5 候補 #7 (新規) 起票済、spec v7 §11 経路試算 章末に annotation 必要 |
| **session 13-20 の MEXC 前提準備** | **大部分が無効化** (MEXC アカウント開設 / native USDC 確認 / Min withdrawal 実測 等)、ただし MEXC 経路復活時に再利用可 |

#### conoha emergency 対応 (5/21 09:41 以降、session 20 後半)

1. **Explore subagent 派遣 (5/21 ~10 時)**: 国内取引所のトラベルルール対応マトリクス + 個人ウォレット経由ルート + 代替経路 2-3 案の web 調査 (1 次ソース重視、2024-2026 最新情報)、結果は `/tmp/route-redesign-research-20260521.md` 配下
2. **retro v0.5 候補 #7 起票** (`scripts/data_cache/retro_v0.5_candidates_20260519.md` 計 7 件に拡張): GMO → MEXC 構造的拒否を spec v7 根本盲点として記録
3. **本 update 作成** (本 subsection): mentor 5/22 中間レビュー時に emergency 状況を qualified に共有
4. **XRP 50 処理 = (a) JPY 戻し採用** (5/22 mentor B3 確定、user が GMO で 5/22 中に XRP→JPY 売却実施)

#### conoha 推奨スタンス update (5/21 09:41)

- **5/23 強行 = 不可能、5/30 延期も MEXC 経路では非現実的**
- mentor 5/22 中間レビューで **MAJOR pivot 議論**: Step 1 経路再設計を最優先議題化
- Explore subagent 結果 (5/22 朝までに完了予定) を基に代替経路 2-3 案を mentor に提示
- 5/30 (土) Step 1 を代替経路で finalize できなければ Step 2 入金 ($350 HL + $150 BP) も延期判断
- spec v7 §11 経路試算 (MEXC 前提) は **構造的盲点として retro v0.5 / spec v8 で正式 fed-back**

#### 経路再設計提案 (5/21 ~10:30 Explore subagent 結果反映)

Explore subagent (web 調査、1 次ソース重視) の結果を `scripts/data_cache/route-redesign-research-20260521.md` に保存。要点:

##### 国内取引所トラベルルール対応マトリクス (主要結果)

| 取引所 | TRP プロトコル | MEXC | Binance | Bybit | Bitget |
|---|---|---|---|---|---|
| bitbank | Sygna | ✅ | ✅ | ✅ | ✅ |
| bitFlyer | TRUST | ✅ | ❌ | ✅ | ✅ |
| Coincheck | TRUST | ✅ | ❌ | ✅ | ❌ |
| SBI VC Trade | Sygna | ✅ | ✅ | ✅ | ✅ |
| **GMOコイン** | Sygna | **❌ [構造的拒否]** | ✅ | ✅ | ✅ |

- **MEXC 経路自体は復活可能** (GMO 以外の 4 社すべて MEXC OK)
- bitFlyer ↔ Binance は TRP 互換性なしで NG
- 全取引所で **個人ウォレット (MetaMask 等) 送付 OK、トラベルルール対象外** (受取人名・住所登録のみ、追加 KYC 不要)
- **bitbank は ETH を Arbitrum One ネットワーク直接出金対応** (2023/10/8 実装)、USDC は要確認

##### user 既存アカウント状況 (5/21 10:30 確認)

- ✅ **bitbank 開設済** → 経路 A 採用可能 (KYC 不要、最短)
- ✅ **Bitget 開設済** → 経路 D 採用可能 (補欠)
- Coincheck は必要なら開設可
- bitFlyer / SBI VC Trade は未開設

##### 採用提案: 経路 A (★ conoha 最推奨)

```
bitbank で ETH 購入 → MetaMask (Ethereum) 送付 → Across bridge で Arbitrum へ → MetaMask (Arbitrum) → HL bridge
```

- **手数料合計: $1.5-6** (session 19 試算 $14-16 から **$8-10 減**)
- **所要時間: 20-40 min**
- **KYC 要件**: bitbank 既存活用、追加不要
- **HL 最小預入 5 USDC** クリアのため $12-15 USDC 規模で経路検証推奨
- **リスク: 低** (Arbitrum bridge は標準 DeFi、HL bridge は本物 verified)

##### 補欠: 経路 D (GMO → Bitget → Arbitrum → HL)

- user Bitget アカウント既存 = KYC 不要、GMO → Bitget は Sygna 互換性で構造的 OK
- XRP 50 (GMO 内残留、5/22 B3 で JPY 戻し採用済) を Bitget へ送付経路として再活用する option もあったが mentor 確定で JPY 戻し採用
- 経路 A の bitbank ETH/USDC 出金対応に問題が出た場合の backup として保持

##### 5/22 mentor 中間レビュー提案議題 (経路再設計関連)

1. ★ **経路 A 採用承認** (bitbank → Arbitrum → HL、手数料 $1.5-6、所要 20-40 min)
2. ★ **Step 1 実行日**: 5/30 (土) or 5/22-29 中の任意土曜への delay 確定 (経路 A は KYC 不要なので最短 5/22-23 でも理論可)
3. ★ **経路 A 用 Step 1 checklist 新規作成 (v0.3)** の起票
4. **spec v7 §11 経路試算 章末 annotation** (MEXC 構造的拒否、代替経路は retro v0.5 §13.4)
5. **XRP 50 (GMO 残留) 処理判断**: (a) JPY 戻し / (b) GMO → bitbank or Bitget 等構造的 OK 経路で transfer / (c) Step 2 軍資金保持

##### 5/22 mentor レビュー前 conoha 作業 (本日 5/21 中)

1. retro v0.5 候補 #7 update (Explore 結果反映) — 完了 (5/21 ~10:35)
2. 本 update finalize + mentor 送付 — 5/22 朝
3. user bitbank ETH/USDC 出金対応確認 (5-10 min user 作業) — 5/21 中依頼
4. (option) 経路 A 用 Step 1 checklist v0.3 draft — mentor 承認後 finalize

### ★ 2026-05-22 中間レビュー B1-B5 mentor 確定

5/22 中間レビュー本番のパート B (conoha、5 論点) で mentor が以下を確定:

| # | 論点 | mentor 判定 |
|---|---|---|
| **B1** | 経路 A 採用承認 | **◎ 採用** (bitbank → MetaMask → Across → Arbitrum → HL bridge) |
| **B2** | Step 1 実行日 | **5/30 (土) 確定** (5/23 強行は中止、5/29 (金) 夜最終チェック → 5/30 (土) 朝実行) |
| **B3** | XRP 50 残高処理 | **(a) JPY 戻し** 採用 (user が GMO で XRP→JPY 売却を 5/22 中に実施) |
| **B4** | 構造的盲点記録 + ハンドオフ誤記訂正 | retro v0.5 #7/#8 起票 + spec v7 §Step 1 章末 annotation + 上記テーブル誤記訂正 (50×2 → 30+20) |
| **B5** | monitoring 移管プロトコル | 試験並走 **5/22 → 6/1 (10 日間)** 採用、6/1 で本移管判定 |

#### 5/22 → 5/30 conoha 作業スケジュール

| 日 | アクション |
|---|---|
| 5/22 (木) PM | mentor B1-B5 判定反映 (本 update、retro #7/#8、spec v7 annotation、checklist v0.3、monitoring v0.2 final) — session 21 (commit 4e4005f) |
| 5/23 (金) | conoha session 21 = 5/22 B1-B5 反映完了 + mentor へ context/mentor_response_20260522_B1_B5.txt 送付 |
| 5/24 (土) | mentor 回答 (1)-(5) 受領 + 反映 (session 22)、★ user 市役所休みで任意整理 5/28 (水) に延期 |
| 5/25 (日) | W22 採取 (Insurance / Validator + 第 2 弾 WebSearch、conoha 自走) |
| 5/26-5/27 (月-火) | bitbank での ETH/USDC 出金経路実地テスト ($1-3 少額) — user 帰宅後 1 区間ずつ、conoha 都度承認 |
| **5/28 (水)** | **★ 任意整理相談** (user 平日休み)、Step 1 準備せず |
| 5/29 (金) 夜 | Step 1 最終チェック (経路 A checklist v0.3 沿い、全 TODO ✅ + path A1/A2/A3 確定 + **★ XRP 売却完了確認 (conoha が user に直接、5/24 mentor 推奨)**)、user 体調次第で 5/30 強行 or 6/6 延期判断 |
| **5/30 (土) 朝** | **★ Step 1 本実行** (経路 A、$12-15 USDC → 約 $7-13 HL 着金) ※ 5/29 で user 体調無理なら 6/6 延期、conoha 判断 OK (5/24 mentor 承認済) |
| 5/30 (土) 完了後 | mentor 報告書送付 + retro v0.5 candidate #3-5 (Step 1 実測由来) 埋め + v0.5 bump (#8 §13.4 併記 or §14 独立は conoha 判断、5/24 mentor 確定) |

### 5/30 (土) Step 1 実行体制 (旧「5/23 実行体制」、5/22 B2 で 5/30 に確定)

| 項目 | 担当 | 確認方法 |
|---|---|---|
| ユーザー承認 (各区間都度) | ユーザー | mentor 役割境界遵守、$10 でも例外なし |
| 経路遂行 | ユーザー手動 (ブラウザ UI) | conoha は Claude が checkpoint 助言のみ |
| evidence 保存 | conoha + ユーザー | `handoff/step1-evidence-2026-05-30/` 配下にスクリーンショット + tx hash |
| 完了後報告書 | conoha | mentor 用 (実測手数料 / 所要 / エラー有無 / HL 最終着金額) |
| 経路 | — | **経路 A 確定** (bitbank → MetaMask → Across bridge → Arbitrum → HL)、旧 MEXC 経路 (v0.2.2 checklist) は構造的盲点として archive |
| 詳細手順書 | conoha | [docs/hl-step1-route-checklist-routeA-v0.3.md](hl-step1-route-checklist-routeA-v0.3.md) (5/22 mentor B1 承認後起票) |

### 投入見積もり (経路 A 確定後、5/22 B1 反映)

- 投入: $12-15 USDC 相当 = ¥1,800-2,200 (HL 最小預入 5 USDC + 安全マージン)
- 想定総手数料: **$1.5-6** (session 19 旧経路試算 $14-16 から **$8-10 減**)
  - bitbank → MetaMask 送付: 無料 (bitbank ETH 送付手数料は時期により $0-5)
  - Across bridge (Ethereum → Arbitrum): $0.80-5
  - Arbitrum gas (HL bridge deposit): <$0.10
- HL 最終着金見込: $7-13 (旧 $6-8 から改善)
- HL 最小預入 $5 USDC をクリア可能
- 所要時間: **20-40 min** (旧 40-75 min から短縮、MEXC swap 工程削除のため)

### 落とし穴 (経路 A、checklist v0.3 で明文化予定)

- HL bridge contract address (`0x2df1c51e09aecf9cacb7bc98cb1742757f163df7`) 必ず Arbiscan で確認 (誤送で永久損失)
- MetaMask Arbitrum 上に 0.001 ETH 以上 (gas 用) — bitbank から ETH を Arbitrum 直接出金できれば最短、Ethereum mainnet 経由なら Across bridge で確保
- bitbank → MetaMask の送付先アドレス登録 + 送付目的確認 (トラベルルール対象外だが 2022/4/1 義務化の手続き)
- Across bridge は **canonical USDC contract** (`0xaf88d065e77c8cC2239327C5EDb3A432268e5831`) を選択、bridged USDC.e は HL bridge で受け取れない
- 旧 MEXC 経路 (v0.2.2) の落とし穴 (Destination Tag 未入力 / MEXC Min withdrawal 不足) は経路 A では発生しない

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
   - **★ 2026-05-19 PM 部分回答**: Step 1 で $10 = ¥1,500 を GMO から流用することに確定、残 ¥11,560 ($77) の扱いは継続論点。候補: (a) Step 2 入金時に追加軍資金として転用、(b) GMO 口座保持 (軸1 VPS インフラ側で将来の運用予備費)、(c) 出金して別プロジェクト (sho-gun / strategy-lab) へ。5/22 で (a-c) いずれかを mentor 判断

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
