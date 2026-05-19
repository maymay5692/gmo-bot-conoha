---
title: HL Monitoring scout 移管準備ドラフト
purpose: mentor 3軸役割再定義 (2026-05-18 確定) に基づく HL 週次 monitoring の scout / conoha 分担定義
status: v0.2 draft (2026-05-18 v0.1 → 2026-05-19 session 17 で conoha 側 position paper 追加、5/22 scout 擦り合わせ叩き台、6/1 試験移管開始予定)
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

## ★ conoha 側 position paper (叩き台、session 17 = 2026-05-19 追加)

5/22 中間レビューで上記 5 論点を効率化するため、conoha 側の position を事前に明文化。**叩き台のため scout 意見次第で flex 可**、特に scout 側の運用負荷観点 (cron / WebSearch 頻度 / 通知作法) は scout 提案を優先。

### 論点 1: データ受け渡し方法 — **push (scout → 共有 path) 推奨**

**conoha 提案**: scout が raw データを共有 path に push、conoha は独立タイミングで読みに行く (pull 方式は採用しない)。

**根拠**:
- pull 方式だと毎週月曜の scout 採取時刻に合わせて conoha が monitoring 採取スクリプトを起動する必要、scheduling 結合度高い (互いの障害が片方の採取漏れに直結)
- push なら scout 側のタイミングで自由に置けて、conoha は読みに行く時間を独立確保可能
- 障害時の影響範囲も限定 (scout 側障害 → conoha 側は既存 push データで動作継続)

**共有 path 候補 (scout 選択)**:
- (a) `~/Desktop/hl-monitoring-shared/` 新規 dir、Mac ローカル両方アクセス可、git non-tracked — **conoha 推奨** (シンプル、scout の cron が Mac ローカルなら adopt 容易)
- (b) `~/Desktop/CCナレッジ/wiki/raw/` 配下に scout-side branch (read-only) — wiki 還元と同経路、ただし wiki は raw 読み取り専用ルールで scout が書く整合性に注意
- (c) `/tmp/hl_scout_w{XX}.json` (揮発性、再起動で消失) — 非推奨

**ファイル形式**: md or JSON、scout 選択。HYPE 価格 / 公式アナウンス検出有無は JSON、HL 公式新着投稿のテキストは md がそれぞれ最適。週次フォルダ構造 `hl_scout_w{XX}/` 内に複数ファイル分離もあり得る。

### 論点 2: アナウンス検出時の即日通知経路 — **file watch + mentor 経由の二重化**

**conoha 提案**: scout がアナウンス検出時、(a) 共有 path に通知 file を即時 push + (b) mentor に即日通知。conoha は両方を fail-safe として受け取る。

**根拠**:
- file watch 単独: conoha 側がチェック頻度を上げる必要、定期 polling のみだと通知 lag (最大 24h) 発生
- mentor 経由単独: 人間チェーンの可用性 (mentor 不在時間帯) に依存、即時性に欠ける
- 二重化: 通常時は file watch で即日検出、conoha 不在 (Mac off) でも mentor → conoha 経路で取りこぼし防止

**通知 file 形式 (conoha 推奨)**:
- path: `~/Desktop/hl-monitoring-shared/announcements/2026-MM-DD-{event}.md`
- 必須項目: 検出時刻 / source URL / 抜粋 (snapshot date があれば明示) / scout 判定 (確度 high / mid / low)
- conoha 側はファイル作成 mtime を file watch でトリガ (Mac cron + `find -mmin -X` で簡易検出可)

### 論点 3: データ source 一致確認 — **monitoring file に scout source も併記**

**conoha 提案**: conoha 側 monitoring file (`hl_monitoring_2026wXX.md`) の各指標欄に「source」列を追加し、scout 採取値と conoha 採取値を両方記載 (差分があれば検出可能)。

**根拠**:
- HYPE 価格は CoinGecko / CoinMarketCap / Dune 等で僅かに差分あり (タイムスタンプ / aggregation 差)、両者の source 明示が前提
- 試験移管期間 (5/22 → 6/5 推奨、論点 5 参照) で 2 週連続一致なら正式移管 OK 判定
- 不整合発見時 (例: HYPE 価格 ±5% 以上の差分) は要因分析 (採取時刻 / source / pricing model 差)、調査後 single source に統一

**conoha 採取 source (現状確認、scout に共有)**:
- HYPE 価格: CoinGecko `/api/v3/simple/price?ids=hyperliquid` (USD spot, market_cap, 24h_change)
- Insurance fund: HL `/info` POST `spotClearinghouseState` (HYPE / USDC / USDE / USDT0 / USDH)
- Validator: HL `/info` POST `validatorSummaries` (Active 数 / Top 10 / HF cluster)

### 論点 4: scout 障害時の fallback — **24h 検知ルール + conoha 一時代替**

**conoha 提案**: scout からの監査 ping が週次 1 回もない場合 (mentor + ユーザーから通知)、24h 以内に conoha が scout 担当指標も一時採取。復旧後は scout に戻す。

**根拠**:
- scout 担当指標 (HL 公式追跡 + HYPE 価格 + アナウンス検出) は conoha も手動採取可能 (週次 5-10 min 追加)
- 業務継続性 (BCP) 観点で必須、scout 障害が長期化しても monitoring 継続
- 復旧基準: scout から正常採取再開の通知 + 共有 path への push 再開

**24h 検知トリガ案**:
- scout が毎週月曜 12:00 JST に「採取完了 ping」(空 file: `~/Desktop/hl-monitoring-shared/health/2026-MM-DD-ok.txt`) を push
- conoha が翌火曜 12:00 JST にチェック、24h 以上前の ping しかなければ scout 障害判定
- mentor + ユーザーに通知 → 一時代替開始

### 論点 5: 5/22 → 6/1 試験移管 — **2 週間並走 (5/22-6/5) 提案**

**conoha 提案**: mentor 確定の 6/1 から 4 日延長して **5/22-6/5 (2 週間並走)**。

**根拠**:
- 1 週並走 (5/22-5/29) だと 1 サンプルのみ、数値整合確認の統計信頼性低い
- 2 週並走 (5/22-6/5) で 2 サンプル取得、scout 採取と conoha 採取の source 一致と timing 一致を両方確認可能
- 仮に 1 週目で違いが見つからなくても、2 週目で異常検出する可能性 (e.g. weekend / weekday の HYPE 価格 timing 差)
- cost: 並走で conoha 側にわずかな追加採取コスト (週次 3-5 min × 2 週) のみ、scout 側は通常採取

**並走判定基準 (conoha 提案)**:
- 2 週連続で HYPE 価格 ±2% 以内、HL 公式追跡の重大投稿 catchup 漏れゼロ、アナウンス検出有無一致
- 上記 OK なら 6/6 から正式移管、scout 単独採取に移行
- 不整合あれば mentor 判断で追加並走 1 週

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
