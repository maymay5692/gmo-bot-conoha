# gmo-bot-conoha 現状 (for mentor)

最終更新: 2026-07-14 (session 37、W29 weekly 採取 + W27/W28 catch-up + #4 close)

## 一行サマリ

軸2 (HL airdrop) 継続。**2026-07-14 W29 weekly 採取完了 + W27/W28 catch-up 実施**。HYPE **$63.98** ($70 台ピーク $71.06 から -10% 反落だが **$60 維持継続**、$60 超は 6/21 起点で 3 週相当)。ただし配分 A 確定は「Step 2 入金時点判定」= 第 2 弾アナウンス検出後のため **配分 B baseline 維持・実弾移動なし** は不変。HF_core_share **48.49%** (6/21 48.91% → 緩やかに低下、~6.5pt headroom)、Insurance HYPE 45.80M 微増、第 2 弾 **15 週連続未公開**、全 Trigger 抵触ゼロ。TVL 月次取得済 (Kinetiq $925M / HyperLend $431M / stHYPE $189M、Morpho $272M 台頭)。**#4 ConoHa plan upgrade は 6/22 殿判断で見送り確定・close**。ToS 月次 + Privacy Policy は W27 スキップで W30 (7/20 前後) に繰り越し。7/15 前後 mentor 月次レビュー入力準備完了。

## 進行中の主要タスク

- **軸2 HL Monitoring** — W29 weekly 採取完了 (7/14)。全 Trigger 抵触ゼロ継続。**W27 (6/29) はスキップ、W28 (7/6) は agmsg push のみ (独立ファイル欠落)** → W29 で推移表に catch-up 取り込み済。次回 weekly は W30 (7/20 前後)、**ToS 月次 + Privacy Policy を W27 繰り越し分として実施予定**。記録: `hl_monitoring_2026w29.md`
- **spec v8 維持** — 第 2 弾アナウンス後の finalize (v9 / v8-final) は外部トリガ待ち (15 週連続未公開)
- **HL Step 2 入金判断** — 第 2 弾アナウンス検出後にユーザー承認 + 配分確定。現状待機
- **軸1 VPS Phase 3 移行** — mentor 裁定で保留継続 (HEIKIN bot / note cron ともに見送り)。受け入れ側として処理なし
- **#4 ConoHa plan upgrade** — **close 済** (下記)

## 直近の重要な動き

- 2026-07-14: **W29 weekly 採取 + W27/W28 catch-up** — HYPE **$63.98** (W28 $71.06 から -10% 反落、$60 維持継続)。HF_core_share **48.49%** (S_HF 212.97M / D_nonjailed 439.21M、counts total=33 active=27 jailed=5)、Insurance HYPE **45,795,504** (+1.02%)、USDE ≈$680 低位、第 2 弾 15 週連続未公開、全 Trigger 抵触ゼロ。TVL 月次: Kinetiq $925.1M(-2.5%) / HyperLend $430.8M(-6.9%) / stHYPE $189.0M(+5.9%)、**Morpho Blue $272.4M 台頭** (stHYPE 超え、次回月次で Top 3 定義算入可否判断)。記録: `hl_monitoring_2026w29.md`
- 2026-07-14: **#4 ConoHa plan upgrade = 6/22 殿判断で見送り確定・close** — mentor relay `2026-06-22-conoha-4-plan-upgrade-verdict.md` の裁定 (見送り確定) を status 反映。VPS Memory は引き続き watch (tight だが単一 workload で安定)。再検討トリガー = bot/note cron の VPS 移行再浮上時
- 2026-07-06: **W28 採取 (agmsg push のみ、独立ファイル欠落を W29 で確認)** — HYPE $71.06 ($60 維持 2 週継続)、HF_core_share 48.58% 横ばい、第 2 弾 14 週未発表、全 Trigger 抵触ゼロ。status/ハンドオフ/commit は当時未反映 → 本 W29 で catch-up
- 2026-06-29: **W27 weekly スキップ** (ToS 月次 / Privacy Policy 含む未採取)。session 36 が W28 のみで中途終了した cadence 逸脱
- 2026-06-21: W26 interim 採取 — HYPE $69.97 $60 明確上抜け、HF_core_share 48.91% 正式初記録、第 2 弾 13 週未公開

## mentor に確認したいこと

殿マター (#4 plan upgrade) は **close 済** (6/22 殿判断=見送り確定を反映)。現在 blocking 依頼なし。明日 (7/15 前後) 月次レビュー向けの判断依頼 3 件:

- [宛先: mentor][目標日:7/15 (月次レビュー)][blocking:N] (1) W27 スキップ + session 36 中途終了の cadence 逸脱報告
  6/29 W27 weekly (ToS 月次 / Privacy Policy 含む) が未採取、7/6 W28 は agmsg push のみで独立ファイル・status・commit が欠落 (session 36 中途終了)。W29 (7/14) で推移表 catch-up + status/ハンドオフ更新 + commit まで復旧済。ToS/Privacy は W30 繰り越し。**再発防止** = 次セッション handoff 規律 (session-boundary.md 締め手順) を徹底で自走可。mentor の追加是正指示があれば受ける。
- [宛先: mentor][目標日:7/15][blocking:N] (2) TVL Top 3 定義への Morpho Blue $272.4M 算入可否
  W29 TVL 月次で **Morpho Blue $272.4M が native lending として台頭** し stHYPE $189M を上回った。ただし Morpho は汎用 multi-chain lending 実装で「HyperEVM native 純度」は Kinetiq/HyperLend/stHYPE より低い。Top 3 定義に含めるか (順位再編) / 参考枠のまま維持するか、mentor 裁定を仰ぎたい。conoha 推奨 = **次回月次 (8 月中旬) まで参考枠のまま観察** (単月台頭で入替判断は早い、8 月継続なら Top 3 算入検討)。
- [宛先: mentor][目標日:7/15][blocking:N] (3) mentor 月次レビュー入力の追加取得指標
  現在の月次レビュー入力は W29 (HYPE / HF_core_share / Insurance / 第2弾 / TVL Top3) + FR monitor 常駐報告 + #4 close 報告 + cadence 逸脱報告。mentor 側で追加取得すべき指標 (Anchorage/Nansen 個別 validator 動向詳細、HYPE 90d re-fetch、その他) があれば指示を仰ぎたい。conoha 推奨 = **現行入力で必要充足** (Trigger 抵触ゼロ継続で新規深掘り指標の必然性なし)。

## 次のマイルストーン

- 2026-07-15 前後: **mentor 月次レビュー** (W29 monitoring + TVL 月次 = 入力準備完了)
- 2026-07-20 前後: **W30 weekly + ToS 月次 + Privacy Policy** (W27 繰り越し分を回収)
- HL 公式第 2 弾アナウンス検出時 (外部トリガ): spec v9 / v8-final finalize + Step 2 入金 (要ユーザー承認)

## 機構的健全性

- **GMO bot v0.14.4** — 取引停止モード継続 (4/18 以降)、再開なし、資金 ~30,500 JPY
- **VPS (ConoHa Windows Server, 160.251.219.3)** — 本セッション未再確認 (前回 6/21: CPU 19.4% / Disk free 72GB / Memory available 122MB tight watch)。軸1 週次 health check は 3 週ぶり未実施 → 要すれば別途 `/status` 確認
- **HL Monitoring API 全系統正常** — CoinGecko / hyperliquid.xyz info / DeFiLlama 全アクセス OK (W29 採取で確認)
- **Trigger 抵触** — ゼロ継続 (HF_core_share 48.49% ~6.5pt headroom、HYPE $63.98 例外 band だが入金時点判定で B 維持、実弾移動なし)
- **FR monitor 系スクリプト手動常駐 (7/14 殿確認済み=意図稼働)** — `fr_monitor.py` / `mexc_fr_monitor.py` / `hl_fr_monitor.py` が caffeinate で常駐 (6/26 頃〜、crontab 登録ではなく手動起動)。中身は funding rate の paper trade 監視 (**実弾なし**)、軸0 bot 本体の再開ではない。**7/14 殿確認で意図した稼働と確定** → conoha は触らず記録のみ継続
- **Step 1 経路 A2** — 検証済 (5/24)、Step 2 で再利用可能
- **kill 抵触** — なし
- **異常** — なし (cadence 逸脱 = W27 スキップは catch-up 済)
