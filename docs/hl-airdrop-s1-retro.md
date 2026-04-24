---
title: Hyperliquid 第 1 弾エアドロ 後知恵分析 (HL S1 Retro)
strategy_id: hl-airdrop-pivot
purpose: HL 第 2 弾戦略 Gate 3 比較可能性評点の 1 次データ + Gate 2 Tail Safety 10 項目チェック HL1 実績評価 + spec v7 fed-back 候補抽出
status: draft v0.3
date: 2026-04-24
sources: 外部レポート (Arkham / Blockworks / PANews / CoinGecko Learn / CoinMarketCap / ASXN / 加東たまお / lutwidse / Node Science / PassiveYieldLab) + Dune `hyperliquid.market_data` 1-min snapshots (2026-04-24 Free tier 直接クエリ実行済) + ASXN HyperScreener homepage manual extraction (2026-04-24)
---

# HL 第 1 弾エアドロ 後知恵分析 (v0.3)

本書は [docs/superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md](superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md) v6 の **論点 4 成果物**。Gate 3 比較可能性評点の HL1 列 1 次データ + Gate 2 Tail Safety 10 項目チェックの HL1 実績評価 + **spec v7 配分期待値表の 1 次データ裏取り**を担う。外部レポート集約 + **Dune 1 次クエリ** + **ASXN UI 部分抽出**。

**v0.3 変更点** (2026-04-24, session 5):
- **Dune 1 次クエリ実行**: `hyperliquid.market_data` で UMA listing 事件 + HYPE 90 日 historical + HYPE precise percentile stats を取得 (archive: `scripts/data_cache/hl_uma_incident_20240119_dune.md`, `scripts/data_cache/hl_hype_90d_20260112_20260412_dune.md`)
- **§1 概要に HL 全体規模 anchor 追加** (ASXN homepage: Total Users 1.20M / Volume $4.30T / Net Inflow $3.70B)
- **§5.5 新設**: ASXN Top Volume ≠ S1 Airdrop Top Recipient の区別を明文化 (混同防止)
- **§10 継続調査 #1 を closed** (Dune per-user route 不能を 1 次確認、bonus: market_data で HYPE 履歴分析 + UMA 裏取りが実施可能に)
- **§10 継続調査 #2 を 3/10 + ASXN homepage partial**: ASXN Top Volume Top 10 抜粋済み、S1 Top 10 特定は Route A/B/B'/C 4 経路を v0.4 送り明示
- **§12.1 #2 評点を B → A 昇格**: UMA 2024-01-19 事件を Dune 1 次データで裏取り、**1.24%/h (lutwidse 原典の 1%/h を超える)** 確認、lutwidse 原典の月日記述 (「2024-02」) を訂正 → **実際は 2024-01-19 listing**
- **§13 新設**: Dune 1 次データ × spec v7 fed-back 候補 (配分 A 条件見直し / 配分 C buffer 見直し / FR コスト更新)
- **Appendix A.5 新設**: Dune 実行済みクエリ (動作確認済 SQL、`hyperliquid.market_data` 実 schema ベース) — 仮 schema の A.1-A.3 は非動作
- phase roadmap 更新: v0.3 は "部分完了" 段階、v0.4 条件明記 (ASXN Route A 試行 or HL API per-user lookup)

**v0.2 変更点** (2026-04-22):
- §2 に Season 1 / Closed Alpha / Season 2 のタイムラインと配布 credit 量を追記
- §3 に ASXN の top/bottom bracket % を追記
- §4 を Season 1 (100% perp 構造) / Season 2 (multi-activity 定性推定) に分離、定量 % は公式未公開を明記
- §5 を Top 10 相当に拡張 (`0xfe..fe` Insurance fund system address / $9.56M holder / 2TheMoon の 3 件)
- §12 新設: **Tail Safety 10 項目チェック HL1 実績評価** (lutwidse 原典還元の Gate 2 8 項目 + §補足 2 項目)
- Appendix A 新設: Dune SQL queries (将来ユーザー実行用、活動タイプ別 % 推定)

---

## 1. 概要

### 1.1 S1 Airdrop 基本データ

| 項目 | 値 |
|---|---|
| 配布日 | 2024-11-29 |
| 総供給量 | 310M HYPE (全 1B 上限の **31%**) |
| 実配布量 | **274M tokens** to 94,000 addresses (ASXN) |
| 受取 addresses | **94,000+** wallets |
| 総価値 at unlock | **$1.8B** (当時最大規模のエアドロ、後知恵で $7B 超到達) |
| 平均受取 | **2,915.66 HYPE** ($20,000 @ unlock, 約 $45,000 @ snapshot estimate) |
| 中央値受取 | **64.53 HYPE** (約 $400 @ unlock) → 右方歪み強い長尾分布 |
| 最大単発受取 | **970,000 HYPE** ≈ $9.56M (ASXN / PANews) — おそらく system address `0xfe..fe` 絡み、§5 参照 |
| Unlock 形態 | fair launch (VC 配分ゼロ、即時フル unlock、multiplier 分のみ vesting) |
| HYPE 価格 @ unlock | **~$6.86/HYPE** (推定: $20k / 2,915 HYPE) |
| HYPE 価格 @ 2026-04 (Dune 実測) | **$42.27** (2026-04-12 boundary) = **6.2×** vs unlock |

### 1.2 HL プロトコル全体規模 anchor (v0.3 追加, 2026-04-24 ASXN)

| 指標 | 値 | 解釈 |
|---|---|---|
| Total Users | **1.20M** | S1 受給者 94k = 現 user base の **~7.8%**、S2 以降潜在受給者プール 92.2% |
| Total Volume (累計) | **$4.30T** | 2023 年 10 月 closed alpha 開始以降の total notional |
| Total Deposits (All Time) | **$372.19B** | treasury size の目安 |
| Total Withdrawals (All Time) | **$368.49B** | — |
| Net Inflow | **$3.70B** | deposits の 1%、フロー型 (長期 HODL は expected less) |
| Daily Active Users | 60K-80K/日 | 累計 1.2M ユーザの **~5-7%** DAU = 安定エンゲージメント |

**source**: `scripts/data_cache/hl_asxn_homepage_20260424.md` (ASXN homepage OCR)。S1 airdrop を受け取ったのは **総ユーザ数の約 8% のみ** で、S2 以降の potential 受給者プールの方が圧倒的に大きい — これは HL2 戦略において「late entrants の potential 参加障壁」と「competition scaling」の双方を示唆する。

---

## 2. 活動基準 (Hyperliquid Points)

### 2.1 タイムライン (v0.2 追記)

| 期間 | 日付 | 配布 credit / 週 | 参加者 | 活動条件 | 備考 |
|---|---|---|---|---|---|
| Closed Alpha | 〜2023-10-31 | **446M credits 一括** | **11,500 active users** | perp testing | 初期テスター |
| **Season 1 本番** | **2023-11-01 〜 2024-05-01** (26 週) | **1,000,000 / 週** | 広範 | **perp trading 純 volume 型** (spot / HLP なし) | 合計 26M credits |
| Season 2 | **2024-05-29 〜 2024-09-29** (18 週) | **700,000 / 週** | 広範 | perp + spot + HLP + referral + staking + **fee-weighted scoring** | 合計 12.6M credits |
| Snapshot | 2024-09-29 推定 | — | 94k addresses | — | 配布 2024-11-29、snapshot から約 2 ヶ月ラグ |

**出典**: PANews "How the Hyperliquid Points System Created the Most Successful Airdrop", Node Science Medium, PassiveYieldLab (2026-04 集約)。

### 2.2 活動タイプ × 倍率

| 活動 | 条件 | 倍率 | 期間 | 備考 |
|---|---|---|---|---|
| Perpetual futures trading | $1,000+ cumulative volume | 基本資格 | S1 + S2 | S1 はこれのみ |
| Spot market trading | — | 基本資格 | **S2 のみ** | S1 には spot 点源なし |
| **HLP vault deposit** | — | **3×** | **S2 のみ** | 最高倍率、6 ヶ月 linear vesting |
| Top 5% fee payer (Power Trader) | — | **2×** | **S2 のみ** | fee-weighted scoring の下位互換、6 ヶ月 linear vesting |
| Referral | 5+ active referrals | 基本資格 | S1 + S2 | 単一アドレスでは非適用 |
| HYPE staking | Season 1 → Season 2 snapshot 維持 | 基本資格 | S2 継続のみ | 低コスト |

- **Season 2 変更点**: 純 volume 型 (S1) → **fee-weighted scoring + multi-activity** (S2)
- **Multiplier vesting**: HLP 3× + Power Trader 2× は claim 後 **6 ヶ月 linear vesting**
- **Season 1 は perp trading 一本足** — whales / HFT / MM が構造的優遇 (Season 2 で緩和)

---

## 3. 受取分布 (wallet サイズ別)

### 3.1 CoinGecko / CoinMarketCap 集計 (2024-11 時点、HYPE ≈ $3.9 at airdrop)

| 受取 HYPE tokens | holders 比率 |
|---|---|
| 16-64 | 20.6% |
| 64-256 | 20.6% |
| 256-1,000 | 12.8% |
| 1,000-4,100 | 8.2% |
| ≤100 合算 | **56.6%** |
| 最大単発 | $9.56M |

### 3.2 ASXN bracket 集計 (v0.2 追記)

| bracket | HYPE tokens | holders 比率 |
|---|---|---|
| Top bracket | 10,000+ (≈$28,000+ @ $2.8) | **4.3%** |
| Bottom bracket | ≤100 (≈$2,800 or less) | **57.0%** |
| 中間 | 101-9,999 | 38.7% |

長尾分布、中央値は **64-256 tokens** レンジ、平均 2,916 tokens ≈ $20,000。平均/中央値比 ≈ 45× は極端な右方歪み → 大口少数 + 小口多数の典型的 Pareto 分布。

---

## 4. 活動タイプ別配布

### 4.1 公式配布詳細は未公開

HL 運営は活動タイプ別 % を公式発表していない。Dune / ASXN の公開ダッシュボードも active trader 数・volume 時系列は出しているが、**「配布された 274M HYPE の %-by-activity-type」の分解は公開されていない**。これは第 2 弾の操作余地確保 + Sybil 対策として意図的に隠している可能性高い (lutwidse §5 の「ポイント計算式非公開・毎週変動」と整合)。

### 4.2 Season 1: perp 100% (構造的確定)

Season 1 (2023-11-01 〜 2024-05-01) の点源は **perp trading 純 volume 型のみ**。spot / HLP / referral / staking は Season 2 から追加。よって:

| S1 配布比 (構造推定) | 値 |
|---|---|
| Perp trading | **100%** |
| その他 | 0% |

配布 credit 総量は **26M credits / 26 週** (1M/週)。

### 4.3 Season 2: multi-activity, 定量データ未公開 (定性推定のみ)

Season 2 (2024-05-29 〜 2024-09-29) の multiplier 構造から定性推定:

| 活動 | 推定寄与 | 根拠 |
|---|---|---|
| Perp trading (base 1×) | **大 (最大参加者層)** | 94k addresses の多数派が perp 経由でエントリー |
| HLP deposit (3×) | **大口に集中** | 3× multiplier + 6 ヶ月 vesting は大口長期プレイヤー向け、2TheMoon 等 Top recipient に集中 |
| Power Trader (2×, top 5% fee payer) | **中** | fee-weighted scoring で whales/MM/HFT 優遇 |
| Spot trading (base 1×) | **小** | S2 導入、spot volume は perp の数分の一 |
| Referral (base 1×) | **副次** | 5+ active referrals 条件、大型ネットワーク所有者のみ |
| HYPE staking (base 1×) | **最小** | S2 継続性維持のみ、低コスト |

配布 credit 総量は **12.6M credits / 18 週** (700k/週)。

**定量化の方法** (v0.2 で確認可能だった場合に備えた推定パイプライン):
1. HL API `spotClearinghouseState` + `info.userState` で snapshot 時点の volume/HLP/fee 分解
2. Dune `hyperliquid_hypercore` schema (活動別 event) で集約
3. 受取 HYPE tokens 時系列 vs 各活動 volume の線形回帰で寄与係数推定

→ **v0.2 では Dune SQL 骨格を Appendix A に起票、実行はユーザー Dune アカウントで将来実施**。実行タイミングは Step 2 入金判断前の Gate 3 fed-back サイクルが現実的。

### 4.4 定性的に判明している事実 (v0.1 継承)

- HLP depositor の **3× multiplier が最有効** (長期預け入れで高配布)
- Perp volume が主流、Season 2 で fee-weighted へ移行
- Referral は副次、大型 referral ネットワーク所有者のみ有効
- Top 500 receiver の **36.4% (182/500) が airdrop 後に全売却**、11% が買い増し (ASXN)
- 大口の多くは HLP + perp の複合アクティビティ

---

## 5. Top recipient 事例

### 5.1 最大単発 — `0xfe..fe` 系 system address (PANews / ASXN)

| 項目 | 値 |
|---|---|
| Wallet | `0xfe...fe` (PANews 記載、下位 2 桁のみ公開) |
| HYPE 保有 (airdrop 直後) | **8.5M HYPE** |
| HYPE 保有 (2026-04 現在) | **43.5M HYPE** ≈ $1.77B (HL Insurance fund system address `0xfefefefefefefefefefefefefefefefefefefefe`) |
| 解釈 | **Insurance fund 関連の system wallet** と推定 (spec v5 追加タスク 5 で確認済) |
| 示唆 | 最大単発「受取」は個人でなくプロトコル自体の system address。実質個人最大は $9.56M (次項) |

### 5.2 個人最大 — $9.56M 受取 wallet (PANews)

| 項目 | 値 |
|---|---|
| HYPE 受取 | **970,000** |
| USD 価値 (at $9.86) | **$9.56M** |
| 記事言及 | 「最大単発 $9.56M」= Starknet / Jupiter の上位エアドロ超 |
| 詳細活動 | 公開データなし (HLP + Power Trader 複合と推定) |

### 5.3 2TheMoon (Arkham 詳細記事)

| 項目 | 値 |
|---|---|
| HYPE 受取 | **508,985.86** |
| USD 価値 (at $8.39) | **$4.3M** |
| 獲得 points | 95,124 |
| 主活動 | 大型 Perpetual long BTC |
| 事故歴 | 2024-10 に $15M 清算 |
| post-airdrop 行動 | **一切売却なし** ($800/token の冗談 limit 以外) |

### 5.4 Top 10 詳細リストは個別公開なし

ASXN Hyperliquid Dashboard (JS SPA、WebFetch では取れず) は top 500 までアドレス単位で追跡しているが、SNS / 集約記事で具体個別公開されているのは **§5.1–5.3 の 3 件のみ**。残り 7 件分の詳細は §10 の継続調査 #2 対象。

ASXN の top 500 aggregate:
- 最大レンジ: **1.95M HYPE ≈ $44.6M** (airdrop 直後ではなく後知恵 all-time)
- 最小レンジ: 100,000 HYPE ≈ $2.8M

→ top 500 全体で $2.8M-$44.6M (airdrop 後の post-pump 価格含む) のレンジ。§6 で post-airdrop 行動を統合。

### 5.5 ASXN Top Volume ≠ S1 Airdrop Top Recipient (v0.3 追加)

ASXN homepage (hyperscreener.asxn.xyz/home) は **累計取引ボリューム Top 10** を public 公開しているが、**これは 2024-11-29 S1 airdrop 受給額 Top 10 とは別概念**。混同しないこと。

#### 差異の構造的理由

| 項目 | ASXN Top Volume | S1 Airdrop Top Recipient |
|---|---|---|
| 計測対象 | 累計取引ボリューム | 2024-11-29 snapshot 時点のポイント |
| 期間 | 全期間 (2023-10〜current) | 2023-10-31 〜 2024-09-29 (S2 終了) |
| 主要活動 | perp volume (post-airdrop 含む) | S1: perp / S2: perp+HLP+Power Trader+referral+staking |
| ユーザ像 | MM / HFT / プロ (高頻度) | 長期 HLP holder / Power Trader / 大型 perp (一発型可) |
| 公開性 | ASXN homepage public | HL 公式非公開、ASXN Dashboard の top 500 aggregate のみ |

#### ASXN Top Users By Volume (累計, 2026-04-24 時点抜粋)

| Rank | Address | Cumulative Volume |
|---|---|---|
| 1 | `0xecb6...2b00` | $241.83B |
| 2 | `0x023a...2355` | $226.24B |
| 3 | `0x162c...8185` | $175.79B |
| 4 | `0xc6ac...8e84` | $162.84B |
| 5 | `0x7b7f...dee2` | $149.89B |
| 6 | `0xe3b6...0acb` | $132.22B |
| 7 | `0xf910...0a2d` | $91.37B |
| 8 | `0xd911...961e` | $64.57B |
| 9 | `0x8e80...2804` | $62.89B |
| 10 | `0x09bc...410d` | $61.58B |

Top 10 合計 ~$1.37T = 全体 $4.30T の **32%** 寡占 → MM/HFT 像。S1 Top 10 とは overlap 未確認 (§10 継続調査 #2 で Route A 試行予定)。

**archive**: `scripts/data_cache/hl_asxn_homepage_20260424.md`

---

## 6. Post-airdrop 行動 (ASXN / Dune)

**Top 500 addresses の挙動**:

| 行動 | 比率 |
|---|---|
| 全売却 | 36.4% (182/500) |
| 買い増し | 11% |
| 部分保有 | 52.6% (残り) |

HODLing 率は **63.6%** → HYPE 価格支持層として機能。fair launch × 即時 unlock でも大量 dump が起きなかった構造的理由の 1 つ。

---

## 7. Gate 3 比較可能性評点 — HL1 の 1 次データ

spec v4 Gate 3 の比較可能性テスト (analyses Topic 3 評点表) への HL1 列 1 次データ:

| 指標 | HL1 実績 | HL2 への示唆 |
|---|---|---|
| プロトコル規模 | **高** ($1.8B @ unlock) | 大型配布動機、Sybil 検出強化を予想 |
| 参加形態類似性 | **高** (perp trading 主体) | touch 前提として類似、ただし第 2 弾はスコープ変更可能性あり |
| 競合密度 | **高** (94k wallets) | 第 2 弾はさらに増加予想 (保守推定) |
| **総合評点** | **高サブセット** | Gate 3 で 100% ポジ必須 |

**Gate 3 高サブセット**: `{HL1, EIGEN}`。HL1 は本書の定量データで「ポジ (高報酬)」と確定。EIGEN 側も並行で評価要。

---

## 8. HL2 戦略への示唆

| 示唆 | spec v4 反映状況 |
|---|---|
| perp trade が最大 point 源、ただし本戦略は **レバレッジ 1× + delta-neutral** で minimal exposure | Gate 2-1 既反映 |
| HLP deposit は最高 multiplier だが **カスタディ/価格変動リスク** | spec で **除外方針確定** |
| referral 副次、本戦略は **単一アドレス運用で活用不可** | Gate 2-4 既反映 |
| HYPE staking は最小コスト、「期間維持型」の価値高い | touch 設計候補 |
| HyperEVM 触り (Season 2 で導入) → TVL top 3 delta-neutral touch | spec 採用根拠、§7 論点 5 で解決済 |
| fair launch の即時 unlock は HODLer 基盤が厚いことを示す | Gate 1 期待値モデルで HYPE 価格前提として採用 |

---

## 9. データソース

### 1 次ソース (公式・準公式)

- [Hyperliquid Official Docs](https://hyperliquid.gitbook.io/hyperliquid-docs/)
- [Arkham Intel — Hyperliquid User Receives $4M Airdrop](https://info.arkm.com/research/hyperliquid-user-receives-4-million-airdrop)
- [Blockworks — Hyperliquid HYPE airdrop](https://blockworks.com/news/hyperliquid-hype-airdrop)
- [CoinMarketCap — Hyperliquid Airdrop Guide](https://coinmarketcap.com/academy/article/hyperliquid-airdrop-guide-what-is-hyperliquid-how-to-participate-and-what-it-means-for-defi)
- [CoinGecko Learn — Hyperliquid Airdrop](https://www.coingecko.com/learn/what-is-hyperliquid-and-what-the-hyperliquid-airdrop-means-for-defi)
- [PANews — Hyperliquid airdrop data](https://www.panewslab.com/en/articles/1m37x8gd)

### v0.2 追加 (Season 1/2 タイムライン搬入源)

- [PANews — How the Hyperliquid Points System Created the Most Successful Airdrop in History](https://www.panewslab.com/en/articles/zena4u1n) — Season 1 / Closed Alpha / Season 2 の credit 量・週数
- [Node Science Medium — Ultimate guide on Hyperliquid Airdrop Season 2](https://nodescience.medium.com/ultimate-guide-on-hyperliquid-season-2-07-19-updated-bb16870f4d98) — S2 eligibility 詳細
- [PassiveYieldLab — Hyperliquid Season 2 Airdrop Guide 2026](https://passiveyieldlab.com/blog/hyperliquid-season-2-airdrop-guide-2026/) — fee-weighted scoring / multiplier 説明
- [ChainCatcher — Hyperliquid $28,500 per person](https://www.chaincatcher.com/en/article/2154653) — 平均 / 最大 / top bracket %
- [ASXN dashboard (JS SPA、WebFetch 不可)](https://data.asxn.xyz/dashboard/hype) — top 500 aggregate (1.95M-100k HYPE レンジ)

### 集計ダッシュボード

- [Dune — Hyperliquid Stats (x3research)](https://dune.com/x3research/hyperliquid) — activity 分解 (WebFetch 403、UI 必要)
- [Dune — Hyperliquid Airdrop History](https://dune.com/queries/3456360/5808399) — WebFetch 403、UI 必要
- [ASXN HyperScreener](https://hyperscreener.asxn.xyz/) — top 500 address 詳細、UI 必要

### v0.3 追加 — Dune 1 次クエリ (2026-04-24 実行済)

- **Dune schema 実名**: `hyperliquid.market_data` のみ (Dune UI 左サイドバー `hyperliquid` namespace 目視確認、per-user table は non-existent)
- **実行済クエリ**: UMA listing 事件定量裏取り / HYPE 90 日 historical / HYPE APPROX_PERCENTILE stats — Appendix A.5 参照
- **archive**: 
  - `scripts/data_cache/hl_uma_incident_20240119_dune.md` — UMA 1.24%/h 事件 50 行 + 5 findings
  - `scripts/data_cache/hl_hype_90d_20260112_20260412_dune.md` — HYPE 91 行 + 19-列 precise stats + spec v7 plug-in table
- **Dune Free tier 制約 (1 次検証済)**: 2-min query timeout、CSV download paid-only、`information_schema.tables` は 2-min 超でタイムアウト → UI 左サイドバー目視が代替

### v0.3 追加 — ASXN UI 部分抽出 (2026-04-24 実行済)

- `scripts/data_cache/hl_asxn_homepage_20260424.md` — HL 全体規模 anchor + Top Volume Top 10 + Route A/B/B'/C 4 経路未実行明細
- ASXN Top Volume ≠ S1 Top Recipient の混同防止明記 (§5.5)

### 日本語分析

- `~/Desktop/CCナレッジ/wiki/sources/hyperliquid-airdrop-strategy.md` (加東たまお)
- `~/Desktop/CCナレッジ/wiki/sources/lutwidse-hyperliquid-analysis.md`
- `~/Desktop/CCナレッジ/wiki/sources/hyperliquid-lazy-airdrop.md`

### プロジェクト内関連

- [spec v4](superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md) — 親 spec
- `~/Desktop/CCナレッジ/wiki/analyses/hyperliquid-tail-safety-evidence.md` — Gate 2-1/2-2 典拠 (lutwidse 原典還元、10 項目チェックと併用)
- `~/Desktop/CCナレッジ/wiki/analyses/sybil-resistance-operations-guide.md` — Gate 2-4 典拠 (5000e12 原典還元)

---

## 10. 継続調査項目 (v0.3 → v1.0)

| # | 項目 | v0.3 状態 | v0.4 / v1.0 条件 |
|---|---|---|---|
| 1 | 活動タイプ別配布量の内訳 (perp / spot / HLP / referral / staking の %) | **closed (Dune 負結果)** — `hyperliquid.market_data` は per-user 情報を持たず、per-activity breakdown は Dune 経路で **実行不能**を 1 次確認。HL 公式 API + ASXN UI が代替。**bonus**: market_data は coin×minute granularity で funding/OI/px/vol を保持、§12 #2 裏取り + §13 spec v7 配分表 1 次データ化に活用確定 | — (closed) |
| 2 | Top 10 recipient の詳細 | **3/10 解決継続** (§5.1-5.3) **+ ASXN homepage partial** (Top Volume Top 10 抜粋済、`hl_asxn_homepage_20260424.md`)。ただし ASXN homepage は **S1 airdrop Top 10 を提供せず**、Route A/B/B'/C 4 経路を v0.4 送りとして同 archive に明文化 | **v0.4**: Route A (ASXN Traders > Profile 10 address 個別照会、~50 min) 優先試行 |
| 3 | Snapshot 時点 score 分布 | **概算解決** — wallet bracket (top 4.3% / bottom 57.0%)、中央値 64.53 / 平均 2,916 HYPE。score itself は HL 非公開 | v1.0: HL API `leaderboard` 等で score API 確認 |
| 4 | 地域別分布 (Japan 勢の受取総額) | **未解決** — 公開データなし、日本語 community 報告も散発的 | **v1.0 では除外** (Noise 判定確定) |
| 5 | Season 1 と Season 2 の配布比 | **解決** — S1: 26M credits / 26 週 (perp 純 volume 型) / S2: 12.6M credits / 18 週 (multi-activity + fee-weighted) | — |
| 6 | HL 第 2 弾細則発表後の再 finalize | **未解決** — HL 公式未発表、weekly Discord/Twitter monitoring (spec v6 Gate 2-6、`hl_monitoring_2026w17.md` W17 稼働) | v1.0: HL 公式第 2 弾アナウンス後 |
| **7 (v0.3 new)** | **spec v7 配分期待値表の 1 次データ裏取り** | **解決 — §13 参照** (HYPE 90d Dune 1 次データから $60/$50/$45/$40 到達確率と $20/$22 下抜け確率を確定、P25-P75 = $28.60-$37.18) | spec v7 bump 対象 |
| **8 (v0.3 new)** | **Tail Safety #2 UMA 定量裏取り** | **解決 — §12.1 #2 B → A 昇格** (Dune 1 次データで 1.24%/h FR max 確認、lutwidse 原典の 1%/h を超過、listing +3 business days extreme regime を定量確立) | — |

**v0.3 で完了した追加項目**:
- Dune 経路の per-user route 不能を 1 次確認 (#1 closed)
- market_data bonus で §12 #2 UMA 裏取り + §13 spec v7 配分 1 次データ化
- ASXN homepage partial (#2 部分進展)

**v0.4 条件** (推奨): Route A (ASXN Traders > Profile 経由の Top Volume 10 address 個別照会) 試行。50 min 作業で Top 10 recipient の S1 claim 有無 / holding size 推定が出る可能性。

**v1.0 条件**: HL 公式第 2 弾細則アナウンス後、spec v7 → spec v8 化と併せて最終 finalize。

---

## 11. spec v6 との接続

- 本ページは **spec v6 論点 4 の成果物 (v0.3)**
- Gate 3 比較可能性評点の HL1 列 1 次データ源
- `wiki/analyses/hyperliquid-tail-safety-evidence.md` の 10 項目チェックを **§12 に HL1 実績評価で当て込み**
- **§13 新設**で spec v7 配分期待値表への fed-back 1 次データを提供
- フェーズロードマップ:
  - **v0.1** (2026-04-22 初回): 骨格 + 基本データ (継続調査項目 #1-6 未着手)
  - **v0.2** (2026-04-22 session 2): S1/S2 タイムライン解明、Top 3 recipient 確定、Tail Safety 10 項目チェック HL1 評価完了、Dune SQL 骨格 Appendix A 起票 (仮 schema)
  - **v0.3** (2026-04-24 session 5): Dune 1 次クエリ 3 本実行 (UMA listing + HYPE 90d + HYPE precise stats)、ASXN homepage partial extraction、§12 #2 B→A 昇格、§13 spec v7 fed-back 新設、§10 #1 closed (Dune per-user route 不能)、§10 #2 4 経路明示
  - **v0.4**: ASXN Route A (Traders > Profile 10 address 個別照会) 試行 — Top 10 recipient の S1 claim 有無判定、~50 min 作業
  - **v1.0**: HL 公式第 2 弾細則アナウンス後、spec v7 → spec v8 化と併せて最終 finalize

---

## 12. Tail Safety 10 項目チェック — HL1 実績評価

本節は [`wiki/analyses/hyperliquid-tail-safety-evidence.md`](~/Desktop/CCナレッジ/wiki/analyses/hyperliquid-tail-safety-evidence.md) §10 の **8 項目チェックリスト** + §補足 2 項目 (Ethical 黒閃 / lutwidse 撤退事実) を、**HL1 で実際に起きた事象** で評価し、**HL2 spec v5 反映状況**と**追加示唆**を整理する。

評点基準:
- **HL1 実績**: A (発生確認) / B (構造は存在するが具体事例なし) / C (未検証)
- **spec v5 反映**: 反映済 / 部分反映 / **未反映 (fed-back 候補)**

### 12.1 チェック表

| # | 項目 | HL1 実績 (lutwidse 原典還元) | 評点 | spec v5 反映 | HL2 追加示唆 |
|---|---|---|---|---|---|
| 1 | 清算バッファ ±20% (低流動性 ±30%) | 2024-02 頃「最大 30% 乖離」清算髭事例発生。UMA 新台で店長 OI 80% → 1 時間 1% FR 異常値 | **A** | 反映済 (Gate 2-1) | 本戦略は lev 1× + delta-neutral fixed → **margin リスクゼロ**。 Gate 2-1 の ±20% バッファは touch プロトコル (Kinetiq/HyperLend 等) での **collateral 比率**にも適用要 |
| 2 | OI 上限接近銘柄への対応 | **2024-01-19 UMA listing で 1.24%/h FR (max) + 88% intraday range、3 日間 extreme regime を Dune 1 次データで実測** (`scripts/data_cache/hl_uma_incident_20240119_dune.md`)。lutwidse 原典「2024-02 UMA 1%/h」は月日記述 2-4 週ずれ、FR 水準は原典超 (**1.24%/h vs 1%/h**)。OI peak 176,759 → 42,243 (76% drop, 6d) で大口退出パターン確認 | **A+** (lutwidse 記述と Dune 1 次データで二重裏取り、v0.3 で B→A 昇格) | 反映済 (Gate 2-1) | **spec v6 Gate 2-1 に「listing +3 business days touch 禁止」の定量原則を追加検討** (v7 候補)。新規上場直後の低流動性銘柄は touch 対象外固定。spec v6「OI 70%+ 到達時 exit」を **monitoring loop に必須組込** |
| 3 | DDoS 補償シナリオ | 2024-02 末 DDoS 発生、店長 +30% 爆益、**運営は損失 + 含み益まで補償** (事例 1 件、Insurance fund 経由) | **A** | 反映済 (Gate 2-2、Insurance fund $1.77B 確認済) | **補償前提にしない**。Insurance fund 枯渇シナリオを kill-switch に組込。compensation_guaranteed=false を spec の runbook に明記 |
| 4 | 運営のメタ変動 (ポイント計算式) | 2024-01 〜 2024-04 で 4 回大幅調整、**2024-04 にポイント 1/5 に減少** (競争激化) | **A** | 反映済 (Gate 2-6 weekly monitoring、kill-switch 「points 2 週連続で前週比 50% 以下」) | メタ変動周期は **3-4 週**。1-3 ヶ月で支配的メタが変わる前提で spec の事後評価ループ (Gate 3 要件 5) を月次で強制 |
| 5 | Sybil 検出耐性 | 2024-04 時点「リファラル経路のみ」で弱い (lutwidse)。HL2 に向けて強化想定 | **B** (構造存在、HL1 で penalty 事例は公開されず) | 反映済 (Gate 2-4、3 軸分散は複垢しない本戦略では無関係) | 単一アドレス運用で Sybil 対策は不要。ただし **touch パターンの同質性**で「bot 判定」される懸念は別途あり (behavioral fingerprint) — spec v5 に未言及、**fed-back 候補 A** |
| 6 | HLP カウンターパーティ | HLP は流動性大半担う、清算 Liquidator Vault 統合、FR 爆益 +30%/日、**ドテン挙動発生** | **A** | 反映済 (TVL top 3 選定で HLP 除外、position < HLP AUM × 1% 概算) | HLP に触らない方針継続。ただし **HyperEVM protocol の backend が HLP 依存**の場合は間接的に counterparty risk — protocol 選定時に要確認 |
| 7 | 中央集権リスク (Jeff + Terra) | VC なし、運営自己資金。**Jeff の物理セキュリティ懸念** (2026-01 以降の拉致事件増で警護雇用)、validator 分散化未達 | **A** | 反映済 (Gate 2-2、position size <= acceptable loss) | founder custody 等価。**全プロトコル失効時の loss = position size 全額**を受容するポジションサイズ固定 (spec v5 $50 HL + $37 Backpack baseline は既にこの前提) |
| 8 | 脆弱性シナリオ | lutwidse が L1 バグ + 資金凍結の 2 件報告、**報酬 $100** (市場水準 $10k-$100k の 1/100-1/1000)、即修正済だが潜在脆弱性残存推定 | **A** | 部分反映 (Gate 2-2 潜在脆弱性の認識) | **低報酬 bug bounty は運営姿勢のサイン**。攻撃者インセンティブが相対的に高い → 未知の脆弱性が攻撃側で蓄積されている可能性 — spec v5 に「bounty 水準 watch」未記載、**fed-back 候補 B** |
| 9 補足 | Ethical — 黒閃 (他者清算誘発) | 2024-02 頃「他者清算への貢献度 = 黒閃の正体」判明。lutwidse 自身が「成行決済で背中を押す」運用を開示 | **A** | 反映済 (倫理的留意、本戦略は lev 1× + delta-neutral で clean) | 他者清算誘発は一切行わない方針継続。**将来の Sybil/Market manipulation 規制で clean traders 保護**が期待できる |
| 10 補足 | lutwidse 本人の撤退事実 | 著者が「一週間で 200 万円を稼いで一年かけて 200 万円を失った」と撤退、DeFi 離脱 | **A** | 反映済 (Protocol Incentive の期限付き受容) | **期限付き戦略**と割り切る。kill-switch を daily/weekly で稼働、機会コスト (Backpack APY 12-17%) を baseline として並行運用 |

### 12.2 集計

| 評点 | 件数 | % |
|---|---|---|
| A+ (lutwidse + Dune 1 次データ二重裏取り) | 1 / 10 (v0.3 で #2 昇格) | 10% |
| A (HL1 で実発生確認) | 8 / 10 | 80% |
| B (構造存在、事例なし) | 1 / 10 (#5 behavioral のみ) | 10% |
| spec v5 反映済 | 9 / 10 | 90% |
| spec v6 で追加反映 | 2 / 10 (#5 behavioral, #8 bounty) | 20% |
| **spec v6 総合カバー率** | **10 / 10** | **100%** |
| **spec v7 候補** (v0.3 追加) | 1 / 10 (#2 listing +3 days 定量ルール) | 10% |

### 12.3 spec v5 への fed-back 候補 — **v6 で反映済 (2026-04-22 session 2)**

**fed-back A — behavioral fingerprint Sybil** — ✅ **spec v6 Gate 2-4 に反映**
- 背景: 単一アドレス運用でも touch パターンの同質性 (同じ時間帯、同じ金額、同じプロトコル順) で bot 判定される懸念
- 反映内容: Gate 2-4 Sybil 対応原則を「behavioral fingerprint 対策として再整理」、3 軸 jitter (時刻 ±1-3h / 金額 ±30% / プロトコル順ランダム化) を明示
- 優先度: **中** → Step 3 touch 設計で具体運用を finalize

**fed-back B — bug bounty 水準 watch** — ✅ **spec v6 Gate 2-2 に反映**
- 背景: lutwidse の L1 bug 報告で $100 (市場水準 $10k-$100k) は運営の脆弱性対応姿勢が**攻撃者インセンティブ上相対的に有利**なサイン
- 反映内容: Gate 2-2 Custody に「bug bounty 水準 watch」を追加、閾値 $1k 未満が継続する場合 position 縮小 (配分 A→B→C シフト)、monitoring 記録先 = `hl_monitoring_YYYYww.md`
- 優先度: **低** → Step 2 入金後の weekly monitoring loop で継続運用

### 12.4 結論

HL1 で実発生した 10 項目中 9 項目が spec v5 で既反映。残る 2 項目 (#5 behavioral / #8 bounty) は **spec v6 (2026-04-22 session 2) で反映済**。**Gate 2 Tail Safety は HL1 の lutwidse 観察を 10/10 カバー**しており、spec v6 のまま Step 1 着手へ進んで問題なし。

**v0.3 追加**: UMA listing 事件を Dune 1 次データで定量裏取り (1.24%/h FR、OI collapse 76%、intraday range 88%)。spec v7 候補として「listing +3 business days touch 禁止」の定量原則を §13 に反映。

---

## 13. spec v7 fed-back candidates — Dune 1 次データ (v0.3 新設)

本節は v0.3 で実行した Dune 1 次クエリ結果を、**spec v6 配分期待値表の更新候補 (spec v7 bump 材料)** として整理する。archive: `scripts/data_cache/hl_hype_90d_20260112_20260412_dune.md`

### 13.1 HYPE 90 日 precise stats (Dune `hyperliquid.market_data` 実測)

| 指標 | 値 | 備考 |
|---|---|---|
| 期間 | 2026-01-12 〜 2026-04-12 | 91 日分 1-min snapshots |
| 90d low | **$20.515** | 2026-01-21 |
| 90d high | **$43.725** | 2026-03-18 |
| P10 (avg_px) | $24.52 | — |
| **P25 (avg_px)** | **$28.60** | 配分 B 下端 validated |
| **P50 (avg_px, 中央値)** | **$31.83** | 配分 B 中心 |
| **P75 (avg_px)** | **$37.18** | 配分 B 上端 |
| P90 (avg_px) | $39.32 | — |
| mean hourly FR | 0.00133%/h = **年 12%** (一方向保有) | delta-neutral では ~1/10 |
| 1-min max FR (全期間) | 0.0434%/h (2026-02-06 spike) | tail event |
| mean peak_oi | 23.0M HYPE | perp OI ≈ 274M airdrop の ~8.4% |

### 13.2 価格到達確率 (90d 実現)

| HYPE 価格 band | 90d 到達確率 | session 4 baseline | v0.3 1 次データ結論 |
|---|---|---|---|
| ≥ $60 | **0.0% (0/91)** | 配分 A トリガ | **$60+ は 90d 実現ゼロ**、配分 A は "条件付き (到達時のみ)" 明示 |
| $50-$60 | 0.0% (0/91) | — | 0 確認 |
| $45-$50 | 0.0% (0/91) | — | 0 確認 |
| $40-$45 | **16.5% (15/91)** | "判断要" | **現水準到達は通常 range 内、判断要 band 明細化** |
| **$28-$40** | **~59% (P25-P75 中心)** | **配分 B baseline** | **baseline 維持、P25=$28.60 下端 validated** |
| $22-$28 | ~13% | 配分 C 候補 | 配分 C band 実測値 |
| $20-$22 | **6.6% (6/91)** | 配分 C 強制境界 近接 | 強制境界 buffer 薄 (6.6% 実現、$22 下抜けは 90d 中 6 日) |
| < $20 | 0.0% (0/91) | 配分 C 強制 | 90d 実現 0、現 baseline は保守的 |

### 13.3 spec v7 bump 候補 3 点

#### 候補 #1 — 配分 A トリガ見直し (優先度: 中)
- **現 spec v6**: HYPE ≥ $60 → 配分 A ($450 HL / $0 BP)
- **v0.3 根拠**: 90 日 historical で **$45-$60 到達 0 日**
- **v7 提案**: 
  - option A: トリガを **$45+** に引き下げ (historical $45-$50 到達 0 日でも、通常 range $37-$40 からは近接)
  - option B: トリガ維持 ($60+) だが「**到達時のみ発動、通常時は配分 B baseline**」を明示し、**現状の default は B** と明記
- **option B 推奨**: historical 0% は「非通常 regime」の強いシグナル。トリガ引き下げは戦略の aggressiveness 上昇と同義、collateral exposure 増加リスク。**v6 "配分 A baseline 論" を "配分 B baseline + A は例外時" に書き換える方が整合的**

#### 候補 #2 — 配分 C 強制境界 buffer 見直し (優先度: 中)
- **現 spec v6**: HYPE < $20 → 配分 C 強制 ($150 HL / $350 BP)
- **v0.3 根拠**: 
  - 90 日 historical で $20 下抜け **0 日** (保守的 baseline 確認)
  - ただし **$22 下抜け 6.6% (6/91 日)、$20.52 到達** (2026-01-21)
  - $20 強制境界まで **buffer $0.52 (2.5%)** のみ
- **v7 提案**:
  - option A: 強制境界を **$22 未満**に引き上げ (historical ~6% 到達、implementation でアラート発動頻度 increase)
  - option B: 境界 $20 維持、ただし **$22 近接 (within 10%) での pre-emptive partial shift** (段階的移行) を monitoring ルールに追加
- **option B 推奨**: 強制境界 $20 は "明確な kill-switch" として価値あり。段階的な pre-emptive shift で配分精度向上が期待できる

#### 候補 #3 — FR コスト想定更新 (優先度: 低、実装影響は小)
- **現 spec v6**: FR コスト想定値が session 4 で未精緻
- **v0.3 根拠**: mean 0.00133%/h = **年 12% (一方向保有)**、delta-neutral では ~1/10 = 年 1.2%
- **v7 提案**: Gate 1 期待値モデルで FR コスト項を明示値化
  - 一方向保有 case: `fr_cost = 0.0133% × 24 × holding_days × multiplier` (holding_days 30 想定で 約 1%)
  - **delta-neutral (本戦略)**: `fr_cost ≈ 0.1-0.2% / 30 日` (receive/pay 相殺の残差)
- **期待値への影響**: 配分 B baseline 純収益性が僅かに改善 (session 4 推定より ~1%pt 好転)

### 13.4 v7 bump 推奨構成

| 候補 | 重要度 | spec v7 で反映すべき内容 |
|---|---|---|
| #1 A トリガ | 中 | 「配分 A baseline → 配分 B baseline」に書き換え + A は "$60+ 到達時のみ" 条件付き発動 |
| #2 C buffer | 中 | $22 近接 pre-emptive shift rule を monitoring loop に追加 |
| #3 FR コスト | 低 | Gate 1 モデルの FR コスト項を 1%/30 日 (1-way) / 0.1-0.2%/30 日 (delta-neutral) に明示値化 |

**v7 bump 条件**: 本 3 候補のいずれかが採用判断に到達する時。HL 公式第 2 弾発表を待たずに **HYPE 価格が $28-$40 baseline 外 (> $45 or < $25)** に移行した段階で strong trigger。

### 13.5 §7 Gate 3 比較可能性評点への反映

本 1 次データは spec v6 の Gate 3 HL1 列を以下で強化:

| 指標 | v0.2 値 | v0.3 実測更新 |
|---|---|---|
| HL1 プロトコル規模 | 高 ($1.8B @ unlock) | **$1.8B @ unlock → $7B+ (後知恵)、HYPE 6.2× 到達 ($6.86→$42.27)** |
| HL1 参加形態類似性 | 高 (perp trading 主体) | 同上 |
| HL1 競合密度 | 高 (94k wallets) | **現 1.20M users の 7.8%、S2 以降潜在受給者 92.2%** — HL2 は competition scaling 予想 |
| **総合評点** | 高サブセット | **高サブセット確定 (1 次データ裏取り済)** |

---

## Appendix A. Dune SQL 骨格 (v0.2 起票、将来ユーザー実行用)

**前提**: Dune v2 の Hyperliquid schema は 2024-Q4 以降で `hyperliquid_hypercore_*` / `hyperliquid_*` 系テーブルが段階的に追加されている。以下は **骨格テンプレ**で、実行時に `information_schema.tables` で正式 schema 名を確認して置き換える必要がある。

### A.1 Query — 活動タイプ別 volume 寄与率 (Season 2)

```sql
-- HL Season 2 (2024-05-29 〜 2024-09-29) の活動別 volume 集約
-- 目的: 配布 % の推定根拠となる relative contribution
WITH s2_window AS (
  SELECT TIMESTAMP '2024-05-29 00:00:00' AS s2_start,
         TIMESTAMP '2024-09-29 23:59:59' AS s2_end
),
perp_vol AS (
  SELECT user_address, SUM(volume_usd) AS vol_usd, 'perp' AS activity
  FROM hyperliquid_hypercore.perp_trades  -- 仮 schema、実行時確認要
  WHERE block_time BETWEEN (SELECT s2_start FROM s2_window)
                       AND (SELECT s2_end   FROM s2_window)
  GROUP BY 1
),
spot_vol AS (
  SELECT user_address, SUM(volume_usd) AS vol_usd, 'spot' AS activity
  FROM hyperliquid_hypercore.spot_trades  -- 仮 schema
  WHERE block_time BETWEEN (SELECT s2_start FROM s2_window)
                       AND (SELECT s2_end   FROM s2_window)
  GROUP BY 1
),
hlp_deposit AS (
  SELECT user_address, SUM(deposit_usd) AS vol_usd, 'hlp' AS activity
  FROM hyperliquid_hypercore.hlp_deposits  -- 仮 schema
  WHERE block_time BETWEEN (SELECT s2_start FROM s2_window)
                       AND (SELECT s2_end   FROM s2_window)
  GROUP BY 1
),
combined AS (
  SELECT * FROM perp_vol
  UNION ALL SELECT * FROM spot_vol
  UNION ALL SELECT * FROM hlp_deposit
)
SELECT activity,
       COUNT(DISTINCT user_address) AS n_users,
       SUM(vol_usd) AS total_vol_usd,
       SUM(vol_usd) / SUM(SUM(vol_usd)) OVER () AS pct_of_total
FROM combined
GROUP BY activity
ORDER BY pct_of_total DESC;
```

**期待される出力** (仮): perp 70-80% / HLP 10-15% / spot 5-10% 相当。これを配布 % の推定 prior として使う。

### A.2 Query — Top 50 airdrop recipient + 活動パターン

```sql
-- HL airdrop (2024-11-29) の top 50 recipient と主活動
WITH airdrop_claims AS (
  SELECT claimant_address, token_amount
  FROM hyperliquid_hypercore.airdrop_claims  -- 仮 schema、2024-11-29 に限定
  WHERE claim_date = DATE '2024-11-29'
  ORDER BY token_amount DESC
  LIMIT 50
),
user_activity AS (
  SELECT a.claimant_address,
         a.token_amount,
         COALESCE(p.vol_usd, 0) AS perp_vol,
         COALESCE(s.vol_usd, 0) AS spot_vol,
         COALESCE(h.vol_usd, 0) AS hlp_deposit,
         p.vol_usd / NULLIF(p.vol_usd + s.vol_usd + h.vol_usd, 0) AS perp_share
  FROM airdrop_claims a
  LEFT JOIN (SELECT user_address, SUM(volume_usd) AS vol_usd
             FROM hyperliquid_hypercore.perp_trades
             WHERE block_time < TIMESTAMP '2024-11-29'
             GROUP BY 1) p ON p.user_address = a.claimant_address
  LEFT JOIN (SELECT user_address, SUM(volume_usd) AS vol_usd
             FROM hyperliquid_hypercore.spot_trades
             WHERE block_time < TIMESTAMP '2024-11-29'
             GROUP BY 1) s ON s.user_address = a.claimant_address
  LEFT JOIN (SELECT user_address, SUM(deposit_usd) AS vol_usd
             FROM hyperliquid_hypercore.hlp_deposits
             WHERE block_time < TIMESTAMP '2024-11-29'
             GROUP BY 1) h ON h.user_address = a.claimant_address
)
SELECT * FROM user_activity
ORDER BY token_amount DESC;
```

**期待される出力**: top 10 の activity 分解 (spec v5 Gate 2-4 Sybil 判定材料として機能)。

### A.3 Query — Wallet size 分布 (bracket 集計)

```sql
-- HL airdrop 受取 HYPE 量の bracket 分布
WITH brackets AS (
  SELECT
    CASE
      WHEN token_amount < 16 THEN '01_0-16'
      WHEN token_amount < 64 THEN '02_16-64'
      WHEN token_amount < 256 THEN '03_64-256'
      WHEN token_amount < 1000 THEN '04_256-1000'
      WHEN token_amount < 4100 THEN '05_1000-4100'
      WHEN token_amount < 10000 THEN '06_4100-10k'
      ELSE '07_10k+'
    END AS bracket,
    token_amount
  FROM hyperliquid_hypercore.airdrop_claims
  WHERE claim_date = DATE '2024-11-29'
)
SELECT bracket,
       COUNT(*) AS n_wallets,
       COUNT(*) / SUM(COUNT(*)) OVER () AS pct,
       SUM(token_amount) AS total_hype,
       SUM(token_amount) / SUM(SUM(token_amount)) OVER () AS hype_pct
FROM brackets
GROUP BY bracket
ORDER BY bracket;
```

**期待される出力**: §3 の bracket 分布を 1 次データで裏取り (現状 ASXN UI 経由の 2 次引用)。

### A.4 実行手順 (ユーザー操作)

1. [Dune Analytics](https://dune.com/) に無料アカウント作成 (既存なら skip)
2. 新規 Query 作成 → A.1 の SQL を貼付
3. `information_schema.tables` で `table_name LIKE 'hyperliquid%'` を検索して実 schema 名に置換 (仮 schema は動かない)
4. 実行 → 結果を `docs/hl-airdrop-s1-retro-dune-results-YYYYMMDD.csv` として保存
5. v0.3 として retro.md §4.2 / §4.3 / §5 の定量データを更新
6. 実行を依頼する Claude セッションでは本 Appendix のクエリ ID を渡す (e.g. "Appendix A.1 の結果を §4.3 に反映して")

---

### A.5 動作確認済クエリ (v0.3 追加, 2026-04-24 Dune Free tier 実行完了)

**重要**: A.1-A.3 の仮 schema `hyperliquid_hypercore.*` は **存在しない**。Dune で実在するのは **`hyperliquid.market_data` のみ** (2026-04-24 UI 目視確認)。per-user / airdrop claim / activity type 分解は **Dune 経路で取得不能** (§10 #1 closed)。以下は market_data の coin×minute granularity データから導出可能なクエリ集。

#### A.5.1 実 schema 発見経路

```sql
-- ❌ タイムアウト (Free tier 2-min 制約)
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema LIKE 'hyperliquid%'
LIMIT 10;
-- → query duration exceeded 120 seconds
```

→ Dune UI 左サイドバー `Tables > hyperliquid` namespace を目視展開し、`market_data` のみ表示されることを確認 (所要 5 秒)。

#### A.5.2 schema 範囲確認クエリ (動作確認済)

```sql
SELECT 
  coin, 
  MIN(time) AS first_snapshot, 
  MAX(time) AS last_snapshot, 
  COUNT(*) AS n_rows
FROM hyperliquid.market_data
WHERE coin IN ('UMA', 'HYPE', 'BTC')
GROUP BY coin;
```

**実測結果** (2026-04-24):
| coin | first_snapshot | last_snapshot | n_rows |
|---|---|---|---|
| BTC | 2023-05-31 | 2026-04-23 | 約 1,536,000 (1-min × 1,066 日) |
| UMA | 2024-01-19 | 2026-04-23 | 約 1,202,000 (1-min × 834 日) |
| HYPE | 2024-12-05 | 2026-04-23 | 約 717,000 (1-min × 498 日) |

#### A.5.3 UMA listing 事件 1 次裏取りクエリ (§12 #2 昇格根拠)

```sql
SELECT
  DATE_TRUNC('day', time)  AS day,
  MAX(ABS(funding))        AS max_abs_hourly_fr,
  AVG(ABS(funding))        AS avg_abs_hourly_fr,
  MAX(open_interest)       AS peak_oi,
  AVG(open_interest)       AS avg_oi,
  MAX(mark_px)             AS day_high,
  MIN(mark_px)             AS day_low,
  MAX(day_ntl_vlm)         AS peak_daily_vlm
FROM hyperliquid.market_data
WHERE coin = 'UMA'
  AND time >= TIMESTAMP '2024-01-19'
  AND time <= TIMESTAMP '2024-04-30'
GROUP BY 1
ORDER BY max_abs_hourly_fr DESC
LIMIT 50;
```

**実測結果**: 50 行 archive = `scripts/data_cache/hl_uma_incident_20240119_dune.md`。核心は **2024-01-19 max_abs_hourly_fr = 0.01242 = 1.24%/h**、lutwidse 原典 1%/h を上回る。

#### A.5.4 HYPE 90 日 daily aggregate クエリ (§13 配分表 1 次データ)

```sql
SELECT
  DATE_TRUNC('day', time)  AS day,
  AVG(mark_px)             AS avg_px,
  MIN(mark_px)             AS low_px,
  MAX(mark_px)             AS high_px,
  AVG(open_interest)       AS avg_oi,
  MAX(open_interest)       AS peak_oi,
  AVG(ABS(funding))        AS avg_abs_hourly_fr,
  MAX(ABS(funding))        AS max_abs_hourly_fr,
  MAX(day_ntl_vlm)         AS peak_daily_vlm
FROM hyperliquid.market_data
WHERE coin = 'HYPE'
  AND time >= TIMESTAMP '2026-01-12'
  AND time <= TIMESTAMP '2026-04-12'
GROUP BY 1
ORDER BY day;
```

**実測結果**: 91 行 archive = `scripts/data_cache/hl_hype_90d_20260112_20260412_dune.md`。

#### A.5.5 HYPE precise percentile stats クエリ (§13.1 plug-in)

```sql
WITH daily AS (
  SELECT
    DATE_TRUNC('day', time) AS day,
    AVG(mark_px)       AS avg_px,
    MIN(mark_px)       AS low_px,
    MAX(mark_px)       AS high_px,
    AVG(ABS(funding))  AS avg_fr,
    MAX(ABS(funding))  AS max_fr,
    MAX(open_interest) AS peak_oi
  FROM hyperliquid.market_data
  WHERE coin = 'HYPE'
    AND time >= TIMESTAMP '2026-01-12'
    AND time <= TIMESTAMP '2026-04-12'
  GROUP BY 1
)
SELECT
  COUNT(*)                                     AS n_days,
  APPROX_PERCENTILE(avg_px, 0.10)              AS p10_avg,
  APPROX_PERCENTILE(avg_px, 0.25)              AS p25_avg,
  APPROX_PERCENTILE(avg_px, 0.50)              AS p50_avg,
  APPROX_PERCENTILE(avg_px, 0.75)              AS p75_avg,
  APPROX_PERCENTILE(avg_px, 0.90)              AS p90_avg,
  MIN(low_px)                                  AS abs_min,
  MAX(high_px)                                 AS abs_max,
  SUM(CASE WHEN high_px >= 60 THEN 1 ELSE 0 END) AS hit_60_up,
  SUM(CASE WHEN high_px >= 50 THEN 1 ELSE 0 END) AS hit_50_up,
  SUM(CASE WHEN high_px >= 45 THEN 1 ELSE 0 END) AS hit_45_up,
  SUM(CASE WHEN high_px >= 40 THEN 1 ELSE 0 END) AS hit_40_up,
  SUM(CASE WHEN low_px  <= 22 THEN 1 ELSE 0 END) AS hit_22_down,
  SUM(CASE WHEN low_px  <= 20 THEN 1 ELSE 0 END) AS hit_20_down,
  AVG(avg_fr)                                  AS mean_hourly_fr,
  MAX(max_fr)                                  AS max_hourly_fr_1min,
  AVG(peak_oi)                                 AS mean_peak_oi,
  MIN(peak_oi)                                 AS min_peak_oi,
  MAX(peak_oi)                                 AS max_peak_oi
FROM daily;
```

**実測結果**: 1 行 (19 列)、§13.1 の plug-in table 全数値の直接出典。Trino `APPROX_PERCENTILE` は Dune Free tier でサポート確認済 (34 秒で完了、credit <1)。

#### A.5.6 v0.4 以降の applicable クエリ候補

1. **他 coin listing day 同パターン検証** (§12 #2 サンプル拡張)
   ```sql
   WITH listing_days AS (
     SELECT coin, MIN(time) AS listing_day
     FROM hyperliquid.market_data
     WHERE coin IN ('ARB', 'AVAX', 'SOL', 'OP', 'MATIC')
     GROUP BY coin
   )
   SELECT md.coin, DATE_TRUNC('day', md.time) AS day,
          MAX(ABS(md.funding)) AS max_abs_fr
   FROM hyperliquid.market_data md
   JOIN listing_days ld ON md.coin = ld.coin
   WHERE md.time BETWEEN ld.listing_day AND ld.listing_day + INTERVAL '3' DAY
   GROUP BY 1, 2
   ORDER BY max_abs_fr DESC;
   ```

2. **HYPE 1-year vol regime 分析** (configuration stability 検証)
   ```sql
   SELECT
     DATE_TRUNC('month', time) AS month,
     STDDEV(mark_px) / AVG(mark_px) AS cv,
     APPROX_PERCENTILE(mark_px, 0.90) - APPROX_PERCENTILE(mark_px, 0.10) AS p10_p90_range
   FROM hyperliquid.market_data
   WHERE coin = 'HYPE'
     AND time >= TIMESTAMP '2025-04-01'
   GROUP BY 1
   ORDER BY 1;
   ```

3. **Funding rate tail event catalog** (§12 tail watch 拡張)
   ```sql
   SELECT coin, time, funding, open_interest, mark_px, day_ntl_vlm
   FROM hyperliquid.market_data
   WHERE ABS(funding) >= 0.005  -- 0.5%/h 以上
     AND time >= TIMESTAMP '2024-01-01'
   ORDER BY ABS(funding) DESC
   LIMIT 100;
   ```

**実行推定時間**: 各 30 秒〜2 分、Dune Free tier で完結可能。
