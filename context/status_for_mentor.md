# gmo-bot-conoha 現状 (for mentor)

最終更新: 2026-07-24 (session 38、W30 weekly 採取 + mentor 7/16 verdicts 3 件反映 + judgment queue 全 close)

## 一行サマリ

軸2 (HL airdrop) 継続。**2026-07-24 W30 weekly 採取完了 + mentor 7/16 verdicts 3 件全反映**。**HYPE $57.62 = $60 割れ検出** (W29 $63.98 → -10.0%、$60 上抜け 3 週維持を離脱、配分 A 例外 band から後退)。ただし実弾判定は入金時点なので **配分 B baseline 維持・実弾移動なし** は不変 (第 2 弾 16 週未公開で Step 2 未発火)。HF_core_share **49.01%** (W29 48.49% → +0.52pt、~6.0pt headroom to 55%)、Insurance HYPE 45.998M (+0.44%)、全 Trigger 抵触ゼロ。mentor 判断依頼 3 件 (cadence / Morpho / 追加指標) は **7/16 verdicts で全 close**、次回判定は 8 月中旬 W33 TVL 月次 (Morpho stHYPE 超え 2 回連続判定)。**ToS 月次 + Privacy Policy は 3 回連続 carry over** (SPA 自動取得不能、user 手動コピペ依頼中)。

## 進行中の主要タスク

- **軸2 HL Monitoring** — W30 weekly 採取完了 (7/24、標準予定 7/20 から 4 日遅延だが cadence 正常)。全 Trigger 抵触ゼロ継続。**HYPE $60 割れ** (W29 $63.98 → W30 $57.62)。次回 weekly は W31 (7/27 前後)。**ToS 月次 + Privacy Policy は W27/W29/W30 で 3 回連続未取得** = user 手動コピペで解消予定。記録: `hl_monitoring_2026w30.md`
- **spec v8 維持** — 第 2 弾アナウンス後の finalize (v9 / v8-final) は外部トリガ待ち (16 週連続未公開)
- **HL Step 2 入金判断** — 第 2 弾アナウンス検出後にユーザー承認 + 配分確定。現状待機
- **軸1 VPS Phase 3 移行** — mentor 裁定で保留継続 (HEIKIN bot / note cron ともに見送り)。受け入れ側として処理なし
- **mentor 判断依頼 queue** — **空** (7/16 verdicts 3 件全 close)

## 直近の重要な動き

- 2026-07-24: **W30 weekly 採取 + mentor 7/16 verdicts 3 件反映** — **HYPE $57.62 = $60 割れ検出** (W29 比 -10.0%、24h -2.62%、mcap $12.82B)。HF_core_share **49.01%** (S_HF 213.11M / D_nonjailed 434.83M、counts total=34 active=27 jailed=6)、Insurance HYPE **45,998,222** (+0.44%、5 週連続微増)、USDE $6,311 ($680 → +828% 反発だが依然 $1M trigger の 1/158)、第 2 弾 16 週連続未公開 (Node Science 7/19 update ガイドが最新、公式沈黙継続)、全 Trigger 抵触ゼロ。副次情報: HL ETF net outflow $698k on 7/21 (単日、トレンド判定不可)。TVL 個別再取得は 8 月中旬 W33 に予定 (月次 cadence 維持)。**mentor 7/16 verdicts 反映**: (1) cadence 逸脱=追認、(2) Morpho=参考枠観察 + 8 月に stHYPE 超え 2 回連続なら算入検討 (native 純度維持 + Morpho 常設参考行が事前見解)、(3) 追加指標=なし、深掘りはイベント駆動。記録: `hl_monitoring_2026w30.md`
- 2026-07-16: **mentor verdicts 3 件受領** — `~/Desktop/my mentor/prompts/2026-07-16-conoha-monthly-3-verdicts.md`。判断依頼 queue が空になり、次の mentor 判断は 8 月中旬の Morpho 判定まで待機
- 2026-07-14: W29 weekly 採取 + W27/W28 catch-up 実施 — HYPE $63.98 ($60 維持継続)、HF_core_share 48.49%、全 Trigger 抵触ゼロ、TVL 月次取得 (Kinetiq $925.1M / HyperLend $430.8M / stHYPE $189.0M、Morpho Blue $272.4M 台頭)
- 2026-07-14: #4 ConoHa plan upgrade = 6/22 殿判断で見送り確定・close 反映
- 2026-06-21: W26 interim 採取 — HYPE $69.97 $60 明確上抜け、HF_core_share 48.91% 正式初記録

## mentor に確認したいこと

現在なし (7/16 verdicts で 3 件全 close、blocking 依頼なし、殿マターなし)。

次回発生予定:
- **8 月中旬 W33 (TVL 月次)**: Morpho Blue が stHYPE を 2 回連続で超えていたら Top 3 算入判定を再上申 (mentor 事前見解 = native 純度維持 + Morpho 常設参考行 = 案 a を推奨)
- **~2026-09**: 第 2 弾 6 ヶ月未公開に達したら「待機前提の月次再点検」を月次アジェンダに 1 行追加 (verdict 3 の軽い観察指示)

## 次のマイルストーン

- 2026-07-27 前後: **W31 weekly** (ToS 月次 + Privacy Policy を user 手動取得込みで実施予定 = 3 回連続 carry over を解消)
- 2026-08-中旬 前後: **W33 weekly + TVL 月次 + Morpho 判定 (2 回目 stHYPE 超え確認)**
- ~2026-09: **第 2 弾 6 ヶ月未公開再点検** (mentor verdict 3 の月次アジェンダ 1 行追加)
- HL 公式第 2 弾アナウンス検出時 (外部トリガ): spec v9 / v8-final finalize + Step 2 入金 (要ユーザー承認)

## 機構的健全性

- **GMO bot v0.14.4** — 取引停止モード継続 (4/18 以降)、再開なし、資金 ~30,500 JPY
- **VPS (ConoHa Windows Server, 160.251.219.3)** — 本セッション未再確認 (前回 6/21: CPU 19.4% / Disk free 72GB / Memory available 122MB tight watch)。軸1 週次 health check は 4 週ぶり未実施 → 要すれば別途 `/status` 確認
- **HL Monitoring API 全系統正常** — CoinGecko / hyperliquid.xyz info 全アクセス OK (W30 採取で確認)。DeFiLlama は W30 未実行 (TVL 月次は W33 に予定)
- **Trigger 抵触** — ゼロ継続 (HF_core_share 49.01% ~6.0pt headroom、HYPE $57.62 で $60 割れ = 配分 A 例外離脱だが実弾判定は入金時点で B 維持、実弾移動なし、18 週連続 目安)
- **FR monitor 系スクリプト手動常駐 (7/14 殿確認済み=意図稼働)** — `fr_monitor.py` / `mexc_fr_monitor.py` / `hl_fr_monitor.py` が caffeinate で常駐継続。中身は funding rate の paper trade 監視 (**実弾なし**)、軸0 bot 本体の再開ではない。conoha は触らず記録のみ継続
- **Step 1 経路 A2** — 検証済 (5/24)、Step 2 で再利用可能
- **kill 抵触** — なし
- **異常** — なし (ToS/Privacy 3 回連続 carry over は SPA 制約に起因、user 手動対応で解消可能)
