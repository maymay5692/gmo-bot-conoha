---
title: HL Monitoring scout 移管準備ドラフト
purpose: mentor 3軸役割再定義 (2026-05-18 確定) に基づく HL 週次 monitoring の scout / conoha 分担定義
status: v0.1 draft (2026-05-18, 5/22 中間レビューで scout Claude と擦り合わせ予定)
parent: CLAUDE.md 軸2 (HL airdrop 専用)
---

# HL Monitoring scout 移管準備ドラフト

## 背景

mentor 2026-05-18 確定の 3軸役割再定義 (`CLAUDE.md`) で、HL 週次 monitoring の一部を scout に移管。理由:

- conoha は軸1 (VPS インフラ基盤) を新主軸化、軸2 (HL airdrop) は spec v7 知見の集中保持に絞る
- scout は web 巡回ベースの軽量タスクが本領、HL 公式アカウント追跡や HYPE 価格採取に最適
- Trigger 判定の最終評価は spec v7 を深く知る conoha が継続 (戦略判断の集中)

## 分担定義 (mentor 確定基準準拠)

### scout 移管対象 (web 巡回ベース、軽量)

| 指標 | 採取方法 | 採取頻度 | 移管理由 |
|---|---|---|---|
| **HL 公式アカウント追跡** | WebSearch / WebFetch | 週次 + 改定告知時即日 | web 巡回が本領 |
| **HYPE 価格 (spot + 24h change + market cap)** | `curl coingecko/v3/simple/price?ids=hyperliquid` | 週次 | API 単発、軽量 |
| **公式アナウンス検出 (第 2 弾 snapshot date)** | WebSearch 集約サイト × 3-5 (airdrops.io / passiveyieldlab / coinlaunch / hyperliquid-airdrop.github.io) | 週次 + 改定告知時即日 | web 巡回が本領、spec v8 化 trigger は conoha へ |

### conoha 継続 (spec v7 知見集中)

| 指標 | 採取方法 | 採取頻度 | 継続理由 |
|---|---|---|---|
| **Insurance fund 残高 (HYPE / USDC / USDE / USDT0 / USDH)** | `curl HL info spotClearinghouseState` | 週次 | spec v7 Gate 2-2 知見 + Ethena/USDE 流動性危機相関リスク文脈 |
| **Validator 分散化 (Active 数 / Top 1-5 / HF cluster)** | `curl HL info validatorSummaries` + python 計算 | 週次 | spec v7 Gate 2-1 知見 + HF cluster watch (>55% 継続 2 週 trigger) |
| **Bug bounty 水準** | WebFetch `hyperliquid.gitbook.io/bug-bounty-program` + Immunefi/HackerOne spot check | 月次 (4 週おき) | 改定告知判断 |
| **ToS / Privacy Policy 更新** | ブラウザ手動目視 `app.hyperliquid.xyz/terms` (SPA、WebFetch 不可) | 月次 (月最終週月曜) | spec v7 §5.3-5.4 知見 |
| **TVL Top 3 月次 snapshot** | `curl https://api.llama.fi/protocols` + HyperEVM native filter | 月次 | HyperEVM ecosystem 構造判断 |
| **HYPE 90 日 historical statistics** | `curl coingecko/v3/coins/hyperliquid/market_chart?days=90` + python 統計計算 | 月次 | spec v7 配分判断の定量根拠 + retro §13 historical 期間 update |

### conoha 専担 (移管対象外)

| 判定 / 出力 | 担当 | 理由 |
|---|---|---|
| **Trigger 抵触最終判定** | conoha | spec v7 知見の集中、scout は raw データ提供のみ |
| **配分シナリオ判定 (A/B/C)** | conoha + ユーザー | spec v7 配分判断ロジック |
| **spec v7 → v8 finalize 判断** | conoha + ユーザー (mentor 報告) | 戦略意思決定 |
| **retro v0.4 → v0.5 update 判断** | conoha + ユーザー | 戦略文書管理 |
| **週次 monitoring ファイル (`hl_monitoring_2026wXX.md`) 編集** | conoha | spec v7 と相互参照、scout はファイル read-only |

## 連携プロトコル (案)

### 毎週月曜 (scout → conoha への raw データ提供)

scout は以下を実行し、JSON / md 形式で raw データを conoha が読める path に置く:

1. HYPE 価格 (`/tmp/hl_hype_w{XX}.json` or scout-side fixed path)
2. HL 公式アカウント新着投稿 (Blog / Twitter / Discord) を WebSearch 集約
3. 第 2 弾アナウンス検出有無 (YES/NO + 検出時は URL + 抜粋)

conoha は scout データ + 自身の採取 (Insurance / Validator) を統合し、Trigger 判定 + 週次 monitoring ファイルに記録。

### 即日 trigger (アナウンス検出時)

scout が第 2 弾アナウンス検出時、即座に conoha に通知 (ファイル or mentor 経由):
- conoha が spec v8 finalize 着手判断
- 影響範囲評価 (Step 2 入金タイミング再考慮)

### 月次 (scout の負担を上げる場合の候補、5/22 以降検討)

- TVL Top 3 月次 snapshot を scout に移管? → 単発 curl + filter で軽量、scout 領域として妥当だが HyperEVM filter ロジックは conoha 知見、移管時はロジック transfer 要
- ToS 月次目視を scout に移管? → SPA ブラウザ目視のため scout も自動化困難、両者ともユーザー手動依頼、現状維持が妥当

## 5/22 中間レビュー時の論点

mentor + scout + conoha の 3 者擦り合わせで以下を確定:

1. **データ受け渡し方法**: scout が conoha が読める path に置くか、conoha が scout の output を pull するか
2. **アナウンス検出時の即日通知経路**: mentor 経由 (人間 in the loop) or file watch (ローカル) or 別経路
3. **データ source 一致確認**: 同一指標を両者が採取して不整合がないか (scout HYPE 価格 vs conoha 採取値 等)
4. **scout 採取の冗長性**: scout 障害時に conoha が一時的に scout 担当指標も採取する fallback 有無
5. **5/22 → 6/1 までの試験移管**: scout が monitoring 担当指標を試験採取、conoha 採取と並走させて一致確認

## 移管完了の判定基準 (案)

- scout が 4 週連続で安定採取 + conoha 採取値と整合
- scout 障害時の fallback 経路が機能
- Trigger 検出時の通知経路が機能
- → mentor 承認で正式移管

## 関連

- `CLAUDE.md` — プロジェクト 3軸役割定義
- `scripts/data_cache/hl_monitoring_2026wXX.md` — 週次 monitoring ファイル (gitignored)
- spec v7: `docs/superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md`
- mentor prompt: `~/Desktop/my mentor/prompts/2026-05-18-conoha-role-redefinition.md`
