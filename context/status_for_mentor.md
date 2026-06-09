# gmo-bot-conoha 現状 (for mentor)

最終更新: 2026-06-10 (session 32 ハンドオフ作成 + agmsg Phase 2 書き手側配線追加; monitoring 実状態は 2026-05-29 session 30 から変化なし)

## 一行サマリ

軸2 (HL airdrop) 継続。**5/29 interim 採取でライブ HYPE $61.20 = $60 上抜け検出 → 配分 A watch 再アーム** (ただし「$60 超 2 週継続」未確認、配分変更の根拠にはならず W26 6/22 で継続判定)。HF cluster 54.92% で 55% 未満維持 (分母振動確定を補強)。5/29 mentor 応答で **spec v8 #9 ◯ 承認**、月次レビュー v0.2 bump 完了。6/15 で #8 + #9 + #10 候補を並列判断予定。

## 進行中の主要タスク

- **軸2 HL Monitoring** — W25 採取完了 + **5/29 interim 採取** (`hl_monitoring_2026w25_interim_20260529.md`、週次系列とは別ラベル)、Trigger 抵触ゼロ継続。次回 weekly は W26 (6/22 予定)。**interim で HYPE $60 上抜け → 配分 A watch 再アーム**
- **mentor 6/15 月次レビュー回答反映待ち** — `docs/mentor-monthly-review-20260615.md` v0.2 で判断依頼 7 項目を起票済 (#6 #7 追加、5/29 mentor 5要件応答反映)
- **5 要件カバレッジ自己評価完了 + mentor 承認済** — `docs/conoha-5-requirements-coverage-20260529.md` v0.1、要件 5 補強 (spec v8 #9) 3 アクション全採用 ◯ 承認、6/15 で最終起票確定
- **軸1 VPS Phase 3 移行** — 6/5 strategy-lab Gate 2 結果 + 6/11 sho-gun 案2' Day 30 売上判定の mentor confirmation 待ち
- **HL Step 2 入金判断** — HL 公式第 2 弾アナウンス検出後にユーザー承認 + 配分確定、現状アナウンス 11 週連続未公開で待機

## 直近の重要な動き

- 2026-06-03: **agmsg Phase 2 書き手側 append 配線を CLAUDE.md に追記** (mentor 6/3 指示 `2026-06-03-agmsg-phase2-writeside-rollout.md`) — status を「mentor に押し込むべき差分」付きで更新したとき `agmsg-append.sh gmo-bot-conoha …` を 1 行呼ぶ配線。宛先=殿/blocking=Y で osascript 通知自動、`[-x] && … || true` ガード付き。commit `aa63d16`
- 2026-06-02: **status「mentor に確認したいこと」7 項目を判断依頼フォーマットに変換** (session 31)、CLAUDE.md にフォーマット記法追記
- 2026-05-29: **session 30 interim monitoring 採取** — ライブ HYPE $61.20 ($60 上抜け、配分 A watch 再アーム)、HF cluster 54.92% (55% 未満維持)、第 2 弾アナウンス未公開継続。session 30 は W26 (6/22) 予定より早く起動したため週次ではなく interim ラベルで記録
- 2026-05-29: mentor 5/29 5要件応答受領、月次レビュー報告書 v0.1 → v0.2 bump (#6 spec v8 #9 + #7 spec v8 #10 候補追加)
- 2026-05-29: 5 要件カバレッジ自己評価レポート作成 (`docs/conoha-5-requirements-coverage-20260529.md`、commit `9798e9b`)
- 2026-05-29: mentor `status_for_mentor.md` 維持ルール追加 + 本ファイル新規作成 (commit `d51102c`)
- 2026-05-28: CLAUDE.md に起動時ナレッジスキャン追加 (mentor 5/28 依頼、commit `423fc43`)

## mentor に確認したいこと

`docs/mentor-monthly-review-20260615.md` v0.2 の判断依頼 7 項目 (5/29 v0.2 で #6/#7 追加)。`~/.claude/rules/mentor-reporting-format.md` 形式:

- [宛先: mentor][目標日:6/15][blocking:N] spec v8 fed-back #8 起票可否 (HF cluster trigger 閾値再校正)
  conoha 推奨は案 B (Active 数正規化)。W23-W24 の >55% は分母縮小由来で W25 に 54.95% 復帰し trigger 解消済。閾値再校正を spec v8 に正式組込すべきか 6/15 で判断願いたい。
- [宛先: mentor][目標日:6/5][blocking:N] 6/5 strategy-lab Gate 2 結果共有 → bot 移行検討開始可否
  Gate 2 結果に応じ HEIKIN bot の Mac→VPS 移行検討を開始してよいか。conoha は受け入れ側、結果共有待ち。
- [宛先: mentor][目標日:6/11][blocking:N] 6/11 sho-gun 案2' Day 30 売上判定 → note cron 移行可否
  売上判定に応じ note 自動公開 cron の Mac→VPS 移行を開始してよいか。conoha は受け入れ側、結果共有待ち。
- [宛先: 殿][カテゴリ1][目標日:6/15][blocking:N] ConoHa plan upgrade 予算決定 (1GB → 2GB or 4GB)
  新規月額支出が発生するため殿判断 (小額 OpEx のため殿が mentor に委任する選択も可)。VPS Memory available 122MB で 要 watch、Phase 3 で複数プロジェクト受け入れ予定。conoha 推奨は memory 逼迫度を 6/15 まで再計測のうえ 2GB から検討。
- [宛先: mentor][目標日:6/15][blocking:N] scout monitoring 移管 retry の可否 (完全撤回 or retry)
  scout 共有パス未作成で 6/1 本移管は延期済。完全撤回するか再試行するか方針判断願いたい。
- [宛先: mentor][目標日:6/15][blocking:N] spec v8 fed-back #9 (要件 5 事後評価ループ補強) 反映の最終承認
  mentor 5/29 で 3 アクション全採用 ◯ 承認済。6/15 で spec v8 への反映を最終承認願いたい。
- [宛先: mentor][目標日:6/15][blocking:N] spec v8 fed-back #10 候補 (要件 2/3/4 軽微補強 bundle) の採否
  conoha 推奨は bundle 採用 (#10 として 3 補強一括 release、優先度 中)。mentor 5/29 で「6/15 で総合判断」承認済。

## 次のマイルストーン

- 2026-06-15: mentor 月次レビュー (報告書 v0.1 送付済、回答待ち)
- 2026-06-22 前後: W26 monitoring + ToS 月次確認 (last_updated 改定有無)
- 2026-07-15 前後: 次回 mentor 月次レビュー (W29 monitoring + TVL 月次再取得同期)
- HL 公式第 2 弾アナウンス検出時 (外部トリガ): spec v8 finalize + Step 2 入金 (要ユーザー承認)

## 機構的健全性

- **GMO bot v0.14.4** — 取引停止モード継続 (4/18 以降)、再開なし、資金 ~30,500 JPY (XRP 50 売却済)
- **VPS (ConoHa Windows Server, 160.251.219.3)** — 安定稼働 34+ 日、cloudflared / bot-manager 正常、CPU 19.4% / Disk free 72GB / Memory available 122MB (要 watch)
- **HL Monitoring API 全系統正常** — coingecko / hyperliquid.xyz info 全アクセス OK (5/29 interim 採取で確認)
- **Trigger 抵触** — ゼロ継続 (HF cluster 55% trigger 解消後も interim 54.92% で 55% 未満維持)
- **Step 1 経路 A2** — 検証済 (5/24、$18.35 着金、エラーなし)、Step 2 で再利用可能
- **kill 抵触** — なし
- **agmsg Phase 2 (書き手側) 配線** — 6/3 完了、status 差分更新時に mentor へ自動 push (殿の運搬ゼロ)
- **異常** — なし
