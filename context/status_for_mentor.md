# gmo-bot-conoha 現状 (for mentor)

最終更新: 2026-06-16 (session 34、mentor 6/15 月次レビュー 7 項目裁定を反映 — spec v7→v8 bump 完了)

## 一行サマリ

軸2 (HL airdrop) 継続。**mentor 6/15 月次レビュー裁定を受領し spec v7→v8 bump 完了** (`2026-06-16-conoha-monthly-review-7items.md`)。反映 3 件 — **#8 HF cluster trigger 閾値再校正** (active-only HF% → 安定分母 `HF_core_share = S_HF/D_nonjailed`、Active 数正規化)、**#9 Gate 3 要件5 事後評価ループ補強**、**#10 要件2/3/4 軽微補強 bundle**。保留・見送り — bot/note cron の VPS 移行 (mentor 見送り)、scout 移管 retry (park)。**#4 ConoHa plan upgrade のみ殿判断待ち** (mentor 推奨=見送り)。HYPE $59.78 $60 直下振動で配分 B baseline 維持。

## 進行中の主要タスク

- **spec v8 bump 完了 (2026-06-16)** — #8/#9/#10 を反映 (`docs/superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md` v8、653→712 行)。第 2 弾アナウンス後の期待値 finalize (v9 / v8-final) は外部トリガ待ち
- **軸2 HL Monitoring** — Trigger 抵触ゼロ継続。次回 weekly は W26 (6/22)。**HF cluster は v8 #8 で新指標 `HF_core_share` に再校正済** (2026-06-16 live 49.16%、安定分母評価)、W26 から新指標で記録。HYPE $59.78 $60 直下振動 (配分 A 未到達)
- **軸1 VPS Phase 3 移行 — mentor 裁定で保留** — HEIKIN bot 移行 (verdict(3) 保留 + strategy-lab 維持モード降格、非稼働 bot 移行に価値なし) / note cron 移行 (sho-gun 6/28 判定待ち) ともに見送り。受け入れ側として処理なし
- **#4 ConoHa plan upgrade 殿判断待ち** — mentor 推奨=見送り (移行保留で根拠消失)。殿の最終判断後 status に 1 行記録
- **HL Step 2 入金判断** — HL 公式第 2 弾アナウンス検出後にユーザー承認 + 配分確定、現状アナウンス 12 週連続未公開で待機

## 直近の重要な動き

- 2026-06-16: **mentor 6/15 月次レビュー 7 項目裁定受領 + spec v7→v8 bump 完了**。#8 (HF cluster 閾値再校正、案B 安定分母 `HF_core_share`、effort max で正規化式設計 + live validatorSummaries で 3 候補検証 → 安定分母方式採用、検証 `scripts/data_cache/hl_hf_cluster_recalibration_20260616.md`)、#9 (要件5 事後評価ループ補強)、#10 (要件2/3/4 bundle) を反映。保留: bot/note cron 移行・scout retry。#4 plan upgrade は殿判断待ち
- 2026-06-14: **6/14 interim monitoring 採取 (6/15 月次レビュー前日の鮮度確保)** — ★ HF cluster **49.09%** (Active 24→27 復帰で分母拡大、HF 絶対 stake 213M 不変のまま % が 54.9→49.1 へ -5.8pt 急落)。W23-W24 >55% が分母縮小由来の振動だったと復帰後数値で確証 = **spec v8 #8 案 B の決定的エビデンス**。HYPE $59.78 ($60 直下振動、配分 A 未到達)、第 2 弾 12 週連続未公開、全 Trigger 抵触ゼロ。記録: `hl_monitoring_2026w26_interim_20260614.md`
- 2026-06-03: **agmsg Phase 2 書き手側 append 配線を CLAUDE.md に追記** (mentor 6/3 指示 `2026-06-03-agmsg-phase2-writeside-rollout.md`) — status を「mentor に押し込むべき差分」付きで更新したとき `agmsg-append.sh gmo-bot-conoha …` を 1 行呼ぶ配線。宛先=殿/blocking=Y で osascript 通知自動、`[-x] && … || true` ガード付き。commit `aa63d16`
- 2026-06-02: **status「mentor に確認したいこと」7 項目を判断依頼フォーマットに変換** (session 31)、CLAUDE.md にフォーマット記法追記
- 2026-05-29: **session 30 interim monitoring 採取** — ライブ HYPE $61.20 ($60 上抜け、配分 A watch 再アーム)、HF cluster 54.92% (55% 未満維持)、第 2 弾アナウンス未公開継続。session 30 は W26 (6/22) 予定より早く起動したため週次ではなく interim ラベルで記録
- 2026-05-29: mentor 5/29 5要件応答受領、月次レビュー報告書 v0.1 → v0.2 bump (#6 spec v8 #9 + #7 spec v8 #10 候補追加)
- 2026-05-29: 5 要件カバレッジ自己評価レポート作成 (`docs/conoha-5-requirements-coverage-20260529.md`、commit `9798e9b`)
- 2026-05-29: mentor `status_for_mentor.md` 維持ルール追加 + 本ファイル新規作成 (commit `d51102c`)
- 2026-05-28: CLAUDE.md に起動時ナレッジスキャン追加 (mentor 5/28 依頼、commit `423fc43`)

## mentor に確認したいこと

6/15 月次レビューの判断依頼 7 項目は **全て裁定済** (`~/Desktop/my mentor/prompts/2026-06-16-conoha-monthly-review-7items.md`)。#8/#9/#10 → spec v8 反映完了。bot/note cron 移行 → 見送り。scout retry → park。残る要確認は 1 件 (殿マター):

- [宛先: 殿][カテゴリ1][目標日:—][blocking:N] ConoHa plan upgrade 予算決定 (mentor 推奨=見送り)
  mentor 裁定で bot/note cron 移行がともに保留 → plan upgrade の根拠 (Phase 3 複数プロジェクト受け入れ) が当面消失。mentor 推奨=見送り。VPS Memory available 122MB は tight だが単一 workload (HL monitoring) で 34 日安定稼働。殿の最終判断待ち、判断が出たら status に 1 行記録。

## 次のマイルストーン

- 2026-06-22 前後: W26 monitoring (HF_core_share 新指標で初記録) + $60 継続判定 + ToS 月次確認 (6/29) + Privacy Policy 取得
- 2026-06-28: sho-gun 案2' Day 30 判定 (note cron 移行再検討トリガ、conoha 受け入れ側)
- 2026-07-15 前後: 次回 mentor 月次レビュー (W29 monitoring + TVL 月次再取得同期)
- HL 公式第 2 弾アナウンス検出時 (外部トリガ): spec v9 / v8-final finalize + Step 2 入金 (要ユーザー承認)

## 機構的健全性

- **GMO bot v0.14.4** — 取引停止モード継続 (4/18 以降)、再開なし、資金 ~30,500 JPY (XRP 50 売却済)
- **VPS (ConoHa Windows Server, 160.251.219.3)** — 安定稼働 34+ 日、cloudflared / bot-manager 正常、CPU 19.4% / Disk free 72GB / Memory available 122MB (要 watch)
- **HL Monitoring API 全系統正常** — coingecko / hyperliquid.xyz info 全アクセス OK (6/14 interim 採取で確認)
- **Trigger 抵触** — ゼロ継続 (HF cluster は v8 #8 で安定分母指標 `HF_core_share` に再校正済、2026-06-16 live 49.16%、~6pt headroom。active 数振動による誤発火構造を解消)
- **Step 1 経路 A2** — 検証済 (5/24、$18.35 着金、エラーなし)、Step 2 で再利用可能
- **kill 抵触** — なし
- **agmsg Phase 2 (書き手側) 配線** — 6/3 完了、status 差分更新時に mentor へ自動 push (殿の運搬ゼロ)
- **異常** — なし
