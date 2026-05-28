# gmo-bot-conoha 現状 (for mentor)

最終更新: 2026-05-29 (5要件カバレッジ自己評価レポート作成直後)

## 一行サマリ

軸2 (HL airdrop) 継続、配分 B baseline 維持 9 週連続 (HYPE $57.21)、HF cluster trigger 解消。本日 mentor 5/29 依頼で 5 要件カバレッジ自己評価完了 (**4◯+1△**、要件 5 事後評価ループに spec v8 #9 候補ギャップ)。

## 進行中の主要タスク

- **軸2 HL Monitoring** — W25 採取完了、Trigger 抵触ゼロ 9 週連続。次回 W26 (6/22 予定)
- **mentor 6/15 月次レビュー回答反映待ち** — `docs/mentor-monthly-review-20260615.md` v0.1 で判断依頼 5 項目を起票済 (+ 本日 5 要件レポートで #6 候補追加)
- **5 要件カバレッジ自己評価完了** — `docs/conoha-5-requirements-coverage-20260529.md` v0.1、要件 5 のみ △ で spec v8 #9 として mentor 上申候補
- **軸1 VPS Phase 3 移行** — 6/5 strategy-lab Gate 2 結果 + 6/11 sho-gun 案2' Day 30 売上判定の mentor confirmation 待ち
- **HL Step 2 入金判断** — HL 公式第 2 弾アナウンス検出後にユーザー承認 + 配分確定、現状アナウンス 11 週連続未公開で待機

## 直近の重要な動き (3日以内)

- 2026-05-29: mentor 5/29 依頼で 5 要件カバレッジ自己評価レポート作成 (`docs/conoha-5-requirements-coverage-20260529.md`)
- 2026-05-29: mentor `status_for_mentor.md` 維持ルール追加 + 本ファイル新規作成 (commit `d51102c`)
- 2026-05-28: CLAUDE.md に起動時ナレッジスキャン追加 (mentor 5/28 依頼、commit `423fc43`)

## mentor に確認したいこと

`docs/mentor-monthly-review-20260615.md` v0.1 の判断依頼 **6 項目** (5/29 #6 追加):

1. **spec v8 fed-back #8 起票可否** — HF cluster trigger 閾値再校正 (55% → 57% / Active 数正規化 / 絶対 stake +20% trigger 追加 / 起票せず のいずれを採用するか)。conoha 推奨は案 B (Active 数正規化)
2. **6/5 strategy-lab Gate 2 結果** — bot 移行検討開始可否、bot サイズ実測共有予定
3. **6/11 sho-gun 案2' Day 30 売上判定結果** — note cron 移行を 6/15 以降に着手するか
4. **ConoHa plan upgrade 判断** — Memory 1GB → 2GB or 4GB の予算決定を conoha 単独判断で進めて良いか
5. **scout monitoring 移管 retry** — 完全撤回で固定するか、別タイミングで retry するか
6. **★ spec v8 fed-back #9 起票可否** (5/29 5要件カバレッジ自己評価から) — 要件 5 事後評価ループ補強の 3 アクション: (a) log フォーマット template 確定 (b) prior 更新ルール明文化 (c) HL2 配布完了直後の事後評価 (retro v0.6 bump) プロセス annotation。conoha 推奨は 3 アクション全採用 (優先度: 中)

## 次のマイルストーン

- 2026-06-15: mentor 月次レビュー (報告書 v0.1 送付済、回答待ち)
- 2026-06-22 前後: W26 monitoring + ToS 月次確認 (last_updated 改定有無)
- 2026-07-15 前後: 次回 mentor 月次レビュー (W29 monitoring + TVL 月次再取得同期)
- HL 公式第 2 弾アナウンス検出時 (外部トリガ): spec v8 finalize + Step 2 入金 (要ユーザー承認)

## 機構的健全性

- **GMO bot v0.14.4** — 取引停止モード継続 (4/18 以降)、再開なし、資金 ~30,500 JPY (XRP 50 売却済)
- **VPS (ConoHa Windows Server, 160.251.219.3)** — 安定稼働 34+ 日、cloudflared / bot-manager 正常、CPU 19.4% / Disk free 72GB / Memory available 122MB (要 watch)
- **HL Monitoring API 全系統正常** — coingecko / hyperliquid.xyz info / DeFiLlama 全アクセス OK
- **Trigger 抵触** — ゼロ 9 週連続 (HF cluster 55% trigger も W25 で解消)
- **Step 1 経路 A2** — 検証済 (5/24、$18.35 着金、エラーなし)、Step 2 で再利用可能
- **kill 抵触** — なし
- **異常** — なし
