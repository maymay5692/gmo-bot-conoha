---
title: Hyperliquid 第 1 弾エアドロ 後知恵分析 (HL S1 Retro)
strategy_id: hl-airdrop-pivot
purpose: HL 第 2 弾戦略 Gate 3 比較可能性評点の 1 次データ。spec v4 論点 4 着手に対応
status: draft v0.1
date: 2026-04-22
sources: 外部レポート (Arkham / Blockworks / PANews / CoinMarketCap / ASXN / 加東たまお / lutwidse)
---

# HL 第 1 弾エアドロ 後知恵分析 (v0.1)

本書は [docs/superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md](superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md) v4 の **論点 4 着手成果物**。Gate 3 比較可能性評点の HL1 列データ源として機能。外部レポート集約による後知恵分析で、v0.1 は骨格 + 基本データ、継続調査項目は §10 に列挙。

---

## 1. 概要

| 項目 | 値 |
|---|---|
| 配布日 | 2024-11-29 |
| 総供給量 | 310M HYPE (全 1B 上限の **31%**) |
| 受取 addresses | **94,000+** wallets (274M tokens) |
| 総価値 at unlock | **$1.8B** (当時最大規模のエアドロ) |
| 平均受取 | $45,000 (snapshot) / $28,500 (peak) / 現在 ≈ 1 億円弱 (加東たまお) |
| Unlock 形態 | fair launch (VC 配分ゼロ、即時フル unlock、multiplier 分のみ vesting) |

---

## 2. 活動基準 (Hyperliquid Points)

Season 1 (〜2023) / Season 2 (〜2024-11) の 2 期間でポイント累積。基礎は place / fill / manage orders の実動作。

| 活動 | 条件 | 倍率 | 備考 |
|---|---|---|---|
| Perpetual futures trading | $1,000+ cumulative volume | 基本資格 | 主流 |
| Spot market trading | — | 基本資格 | 補助 |
| **HLP vault deposit** | — | **3×** | 最高倍率 |
| Top 5% fee payer | — | **2×** | Power Trader |
| Referral | 5+ active referrals | 基本資格 | 単一アドレスでは非適用 |
| HYPE staking | Season 1 → Season 2 snapshot 維持 | 基本資格 | 低コスト |

- **Season 2 変更点**: 純 volume 型 → **fee-weighted scoring** (高品質 trader 優遇)
- **Multiplier vesting**: HLP 3× + Power Trader 2× は claim 後 **6 ヶ月 linear vesting**

---

## 3. 受取分布 (wallet サイズ別)

CoinGecko / CoinMarketCap 集計 (2024-11 時点、HYPE ≈ $3.9 at airdrop):

| 受取 HYPE tokens | holders 比率 |
|---|---|
| 16-64 | 20.6% |
| 64-256 | 20.6% |
| 256-1,000 | 12.8% |
| 1,000-4,100 | 8.2% |
| ≤100 合算 | **56.6%** |
| 最大単発 | $9.56M |

長尾分布、中央値は **64-256 tokens** レンジ。

---

## 4. 活動タイプ別配布 (判明範囲)

**正確な活動タイプ別の配布量内訳は公開データ未取得**。現時点で判明している定性情報:

- HLP depositor の **3× multiplier が最有効** (長期預け入れで高配布)
- Perp volume が主流、Season 2 で fee-weighted へ移行
- Referral は副次、大型 referral ネットワーク所有者のみ有効
- Top 500 receiver の **36.4% (182/500) が airdrop 後に全売却**、11% が買い増し (ASXN)
- 大口の多くは HLP + perp の複合アクティビティ

→ §10 の継続調査項目 #1 で Dune SQL による内訳推定を予定

---

## 5. Top recipient 事例

### 2TheMoon (Arkham 詳細記事)

| 項目 | 値 |
|---|---|
| HYPE 受取 | 508,985.86 |
| USD 価値 (at $8.39) | $4.3M |
| 獲得 points | 95,124 |
| 主活動 | 大型 Perpetual long BTC |
| 事故歴 | 2024-10 に $15M 清算 |
| post-airdrop 行動 | **一切売却なし** ($800/token の冗談 limit 以外) |

### 別ソース (CoinGecko)

最大単発受取 **$9.56M** (2024-11 HYPE 価格での換算)。

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

### 集計ダッシュボード (v0.2 で SQL 補完対象)

- [Dune — Hyperliquid Stats (x3research)](https://dune.com/x3research/hyperliquid)
- [Dune — Hyperliquid Airdrop History](https://dune.com/queries/3456360/5808399)
- [ASXN HyperScreener](https://hyperscreener.asxn.xyz/)

### 日本語分析

- `~/Desktop/CCナレッジ/wiki/sources/hyperliquid-airdrop-strategy.md` (加東たまお)
- `~/Desktop/CCナレッジ/wiki/sources/lutwidse-hyperliquid-analysis.md`
- `~/Desktop/CCナレッジ/wiki/sources/hyperliquid-lazy-airdrop.md`

### プロジェクト内関連

- [spec v4](superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md) — 親 spec
- `~/Desktop/CCナレッジ/wiki/analyses/hyperliquid-tail-safety-evidence.md` — Gate 2-1/2-2 典拠 (lutwidse 原典還元、10 項目チェックと併用)
- `~/Desktop/CCナレッジ/wiki/analyses/sybil-resistance-operations-guide.md` — Gate 2-4 典拠 (5000e12 原典還元)

---

## 10. 継続調査項目 (v0.2 → v1.0)

1. **活動タイプ別配布量の内訳** (perp / spot / HLP / referral / staking の配分 %) — Dune SQL で推定
2. **Top 10 recipient の詳細** (wallet size, activity pattern, post-airdrop 保有状況)
3. **Snapshot 時点 score 分布** (Dune からの 1 次集計)
4. **地域別分布** (Japan 勢の受取総額、日本語 community 報告)
5. **Season 1 と Season 2 の配布比** (point 期間別、fee-weighted 変更の影響評価)
6. **HL 第 2 弾細則発表後の再 finalize** (v1.0 化)

---

## 11. spec v4 との接続

- 本ページは **spec v4 論点 4 の 1 次着手成果物 (v0.1)**
- Gate 3 比較可能性評点の HL1 列 1 次データ源
- `wiki/analyses/hyperliquid-tail-safety-evidence.md` の 10 項目チェックと併用
- 次フェーズ:
  - **v0.2**: §10 の継続調査項目 1-5 を Dune SQL 等で補完
  - **v1.0**: HL 公式第 2 弾細則発表後、spec v5 と併せて最終 finalize
