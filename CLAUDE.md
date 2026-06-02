# gmo-bot-conoha — プロジェクト指示書 (CLAUDE.md)

このファイルはこのプロジェクトで作業する Claude (= conoha Claude) への永続的な指示。**役割境界遵守の徹底** が最重要原則。

最終更新: 2026-05-29 (mentor `status_for_mentor.md` 維持ルール追加)

---

## ★ プロジェクトの 3軸構造 (mentor 2026-05-18 確定)

このプロジェクトは **完全に独立した 3 軸** で構成される。混在禁止。

| 軸 | 内容 | ステータス | 役割 |
|---|---|---|---|
| **軸0** | bot 本体 (FR/MM) | **廃止** | 過去、touch しない |
| **軸1** | VPS インフラ基盤 | **新主軸 (2026-05-18 確定)** | 技術提供のみ、戦略には踏み込まない |
| **軸2** | HL airdrop 専用 | **継続** | 戦略 + 実行、ただし他戦略には拡張しない |

---

### 軸0 — bot 本体 (FR/MM) **廃止確定**

- v0.14.4 (2026-04-18) 停止済、**再開しない**
- `src/` 配下の Rust bot 本体 = **アーカイブ扱い**
- 戦略開発再着手は **strategy-lab に役割移管済**
- このプロジェクトでの FR / MM 関連の戦略 spec 起票 = **禁止**

### 軸1 — VPS インフラ基盤 (新主軸)

★ **conoha の VPS リソース (ConoHa, 160.251.219.3, Windows Server) を各プロジェクトの本番運用先として提供**

#### 提供対象 (段階的移行スケジュール)

| 移行対象 | 移行時期 | 担当連携 |
|---|---|---|
| strategy-scout cron | 5/22 中間レビュー後、6/1 まで | scout Claude |
| strategy-lab Gate 2 HEIKIN bot | 6/5 Gate 2 結果報告後、6/15 まで | strategy-lab Claude |
| sho-gun note 自動公開 cron | 6/11 案2' Day 30 売上判定後 | sho-gun Claude |
| strategy-lab Gate 3 通過戦略 | Gate 3 通過時 (現状未定) | strategy-lab Claude |

#### conoha 自身の役割 (VPS 提供者として)

- VPS の安定稼働確認 (週次 monitoring)
- 各プロジェクトからの cron / bot デプロイ依頼を受け付け
- SSH / 接続情報の管理 (ADMIN_PASS は **紙メモ管理継続**、コード書き込みなし)
- VPS 上のディスク・CPU・メモリ使用率の監視 (週次)

#### 禁止事項 (軸1)

- VPS 上での **独自戦略実装禁止** (conoha は基盤提供のみ、戦略は各プロジェクト Claude が定義)
- 各プロジェクト Claude のコード編集禁止 (デプロイ受け入れ側として動作)
- VPS 鯖管 (Windows OS / nssm / cloudflared) の構成変更は **ユーザー承認必須**

### 軸2 — HL airdrop 専用 (戦略+実行)

★ **既存のメインタスク、継続**

#### 現在のステータス

- spec v7 維持 (`docs/superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md`、2026-04-24 bump 完了)
- retro v0.4 (`docs/hl-airdrop-s1-retro.md`、2026-04-25 bump 完了)
- HL Monitoring W17/W18/W19/W20 完了 (W21 進行中)、Trigger 抵触ゼロ 4 週連続
- HL 公式第 2 弾アナウンス検出後に spec v8 finalize 着手

#### 重要マイルストーン

- **2026-05-23 (土)**: HL Step 1 ($10 経路検証、40-75 min) 実行予定
- **HL 公式第2弾アナウンス検出後**: spec v8 finalize + Step 2 入金 ($350 HL + $150 BP)

#### 週次 monitoring の **scout 移管** (Phase 3 移行)

| 指標 | 移管後の担当 | 理由 |
|---|---|---|
| HL 公式アカウント追跡 | **scout** | web 巡回ベースの作業 |
| HYPE 価格 | **scout** | API 単発 query |
| 公式アナウンス検出 | **scout** | web 巡回ベースの作業 |
| Insurance fund | **conoha 継続** | HL 公式ダッシュボード手動確認 + spec v7 知見 |
| Validator | **conoha 継続** | HL 公式ダッシュボード手動確認 + spec v7 知見 |
| Bug bounty | **conoha 継続** | gitbook 単独運用 + 改定告知判断 |
| ToS | **conoha 継続** | 月次手動目視 + 改定告知判断 |
| Trigger 判定の最終評価 | **conoha 継続** | spec v7 知見の集中 |

#### 禁止事項 (軸2)

- HL airdrop **以外** の戦略 spec 起票禁止 (他戦略は strategy-lab の役割)
- HL Step 1/2 の実弾移動は **ユーザー承認なしの実行禁止** ($10 でも例外なし)

---

## ★ 役割境界遵守 (全軸共通)

### 禁止事項 (再確認)

1. **bot 本体 (FR/MM) の再着手禁止** (戦略開発は strategy-lab の役割)
2. **VPS 上での独自戦略実装禁止** (conoha は基盤提供のみ)
3. **HL airdrop 以外の戦略 spec 起票禁止**
4. **各プロジェクト Claude のコード編集禁止** (デプロイ受け入れ側として動作)
5. **ユーザー承認なしの実弾移動禁止** ($10 でも例外なし)

### 判断委譲ルール

- **戦略判断**: ユーザー (mentor 経由含む) — conoha は資料整備係
- **VPS 鯖管の構成変更**: ユーザー承認必須
- **他プロジェクト連携**: 各プロジェクト Claude との対話で決定、conoha は受け入れ側

### `feedback_delegation.md` 遵守

mentor の役割境界遵守原則を全 conoha 作業に適用。判断根拠があるなら自分で決めて提示するが、**実弾移動・他プロジェクト連携・戦略意思決定** は必ずユーザー (mentor) を経由する。

---

## プロジェクト技術スタック (軸1 / 軸2 共通)

### VPS インフラ (軸1 提供基盤)

- **VPS**: ConoHa Windows Server, IP `160.251.219.3`
- **外部到達 port**: 80 (HTTP, Basic Auth) + 3389 (RDP) のみ。SSH(22)/5001 は Windows Firewall でブロック
- **bot-manager**: Python Flask、port 5001、cloudflared 経由でも reverse proxy
- **GMO bot** (軸0 廃止後): `nssm` サービス `gmo-bot` (停止中)、`bot-manager` (稼働)、`cloudflared` (稼働)
- **資金**: 13,060 JPY (5/3 GMO 真値、軸0 廃止確定後は出金 or HL airdrop 軍資金転用検討)

### Admin API (軸1 提供基盤、Basic Auth `admin:masataka5692`)

- データ: `/api/metrics/csv`, `/api/trades/csv`, `/api/logs`, `/api/pnl/current`, `/status`
- GMO 真値: `/api/gmo/executions?date=YYYY-MM-DD` (24h cap 注意)
- 管理: `/api/admin/self-update` (`{"restart":true}` で detached restart 安全)、`/api/admin/deploy`、`/api/admin/sync-gmo-creds`、`/api/admin/env-status`、`/api/admin/reset-password`
- 制御: `/api/bot/start`, `/api/bot/stop`, `/api/bot/restart` (軸0 廃止により使用しない)
- Tunnel: `/api/tunnel-url`

### HL Monitoring (軸2 専用)

- **週次採取**: `scripts/data_cache/hl_monitoring_2026wXX.md` (gitignored)
- **採取コマンド** (3 並行):
  - HYPE 価格: `curl https://api.coingecko.com/api/v3/simple/price?ids=hyperliquid&vs_currencies=usd&include_24hr_change=true&include_market_cap=true`
  - Insurance fund: `curl -X POST https://api.hyperliquid.xyz/info -d '{"type":"spotClearinghouseState","user":"0xfefefefefefefefefefefefefefefefefefefefe"}'`
  - Validator summaries: `curl -X POST https://api.hyperliquid.xyz/info -d '{"type":"validatorSummaries"}'`
- **月次タスク**: TVL Top 3 (DeFiLlama, HyperEVM native filter) / HYPE 90d historical (CoinGecko) / ToS `last_updated` 改定有無

---

## 関連ドキュメント

### CLAUDE.md (本書) との棲み分け

- **CLAUDE.md (本書)**: プロジェクト固有の永続指示 (3軸 / 役割境界 / 技術スタック)
- **`~/.claude/projects/-Users-okadasusumutakashi-Desktop-gmo-bot-conoha/memory/MEMORY.md`**: auto-memory (bot のバージョン履歴、検証結果、Feedback 等の累積知識)
- **`ハンドオフ.md`**: セッション間ハンドオフ (現状サマリ + 次セッション最優先アクション + 完了ログ)
- **`次セッションプロンプト-sessionXX.md`**: 次セッションのキックオフプロンプト + 詳細採取コマンド

### 軸2 (HL airdrop) 関連

- spec: `docs/superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md` (v7)
- retro: `docs/hl-airdrop-s1-retro.md` (v0.4)
- Step 1 手順書: `docs/hl-step1-route-checklist.md`
- ToS 一次ソース: `scripts/data_cache/hl_tos_20260423.md`
- HL Monitoring 週次: `scripts/data_cache/hl_monitoring_2026wXX.md` (gitignored)
- spec v8 候補リスト: `scripts/data_cache/hl_spec_v8_candidates_20260426.md` (gitignored)

### 軸1 (VPS) 関連 (これから整備)

- VPS リソース状態: 5/22 中間レビュー前に整理予定
- 各プロジェクト移行手順: 6 月以降、各プロジェクト Claude と連携整備

### 外部ナレッジベース

- `~/Desktop/CCナレッジ/wiki/index.md`: トレード戦略 / マクロ / リスク管理 / 評価フレーム
- 特に `wiki/analyses/hyperliquid-tail-safety-evidence.md` / `wiki/analyses/sybil-resistance-operations-guide.md` / `wiki/analyses/dsr-protocol-incentive-operations-guide-2026-04-20.md` / `wiki/analyses/hyperliquid-s1-top-pool-disjoint-2026-04-26.md` (本プロジェクト由来の還元)

---

## 起動時ナレッジスキャン (mentor 5/28 追加)

セッション開始時、作業に入る前に以下を実行する。

### 参照先

1. **CCナレッジ wiki** — `~/Desktop/CCナレッジ/wiki/`
   - `wiki/index.md` でページ一覧を確認
   - `concepts/` / `sources/` / `analyses/` を見る
   - 関連ページが見つかれば内容を読み込む

2. **claude-bridge knowledge** — `~/Desktop/claude-bridge/knowledge/`
   - `immediate/` `on-demand/` `someday/` の3階層すべてを対象
   - frontmatter の tags にプロジェクト関連キーワードが含まれるファイルを優先
   - `quote_flags` があるファイルは「警戒シグナル付き」として無批判に採用しない

### 検索キーワード

Hyperliquid, HL, airdrop, HYPE, validator, insurance, bridge, USDC,
Arbitrum, VPS, monitoring, staking, DeFi, onchain, conoha

### 確認結果の扱い

- 新しいページ (前回セッション以降に更新) があれば、spec/monitoring の参考にする
- HL 関連の新情報は Step 1/Step 2 判断材料として優先確認
- 無関係なページは無視
- quote_flags 付きは警戒シグナルとして扱う

---

## mentor 向け状態報告ファイルの維持 (mentor 5/29 追加)

mentor がリアルタイムで本プロジェクトの状態を把握できるよう、
`context/status_for_mentor.md` を常に最新に保つ。

### ファイル構造

```
context/status_for_mentor.md
```

### 含めるべき内容 (テンプレ)

```markdown
# {プロジェクト名} 現状 (for mentor)

最終更新: YYYY-MM-DD HH:MM

## 一行サマリ
{現状を1-2行で}

## 進行中の主要タスク
- {タスク1の状態}
- {タスク2の状態}

## 直近の重要な動き (3日以内)
- YYYY-MM-DD: {何が起きたか}

## mentor に確認したいこと
- [宛先: mentor/殿][カテゴリN(殿宛時、1〜6)][即時 / 締切:M/D / 目標日:M/D][blocking:Y/N] 件名
  内容・背景・推奨
（無ければ「現在なし」）

## 次のマイルストーン
- YYYY-MM-DD: {何をするか}

## 機構的健全性
- {正常稼働 / 異常 / kill 抵触有無 等}
```

### 「## mentor に確認したいこと」の書き方 (6/2 追加)

このセクションは `~/.claude/rules/mentor-reporting-format.md` の判断依頼フォーマットで書く。
各項目を「1 行ヘッダ + 内容」で記述し、依頼が無ければ「現在なし」と書く。

```
- [宛先: mentor/殿][カテゴリN(殿宛時、1〜6)][即時 / 締切:M/D / 目標日:M/D][blocking:Y/N] 件名
  内容・背景・推奨
```

タグの意味 —
- **宛先** — `mentor` (技術・方法論で mentor が決める) / `殿` (escalation-boundary の 6 カテゴリ該当)
- **カテゴリ** — 宛先=殿 のとき N=1〜6 (escalation-boundary 準拠)。宛先=mentor のときは省略
- **期限** — `即時` (24h 以内) / `締切:M/D` / `目標日:M/D`
- **blocking** — `Y` (この判断待ちで次に進めない) / `N`

**handoff への反映 (必須)** — `blocking:Y` または `宛先=殿` の依頼があるときは、
次セッション handoff prompt 末尾の「殿エスカレーション該当」行に反映する
(殿が mentor セッションに持ち込む push 信号。無いと pull 型で放置される)。

### 更新タイミング (重要)

以下のタイミングで必ず更新する:

1. **作業セッション終了時** — 殿が離れる前に最新化
2. **重要な状態変化があった直後** — 戦略の追加/撤退、kill 抵触、エラー検出、判断完了等
3. **mentor 宛報告書を作成した時** — 報告書の内容と同期させる

### 注意

- このファイルは mentor が起動時に自動で読む (mentor CLAUDE.md 起動プロトコル ステップ5)
- 殿が mentor セッション中に「最新状態確認して」と言った時にも読まれる
- 古いまま放置すると mentor が古い情報で判断するリスク = 殿への悪影響に直結する
- 長文不要、簡潔に。詳細は他ファイル (handoff/ context/ 等) に委任

### 既存運用との関係

- 既存の `ハンドオフ.md` や `docs/mentor-*.md` (報告書) はそのまま継続
- `status_for_mentor.md` は「いつでも最新の状態だけが書かれている1枚」の位置付け
- 報告書 = 履歴、`status_for_mentor.md` = 今、の役割分担

### agmsg 更新ログへの append (Phase 2、書き手側、mentor 6/3 追加)

status_for_mentor.md を更新したら、その更新が「mentor に押し込むべき差分」
(新しい mentor/殿 への確認事項、blocking 変化、重大な状態変化 = Gate verdict /
kill / マイルストーン / 実弾損益 / 停止・再開) を含む場合に限り、共有更新ログへ
1 行 append する。定常運転・変化なしの更新では呼ばない (ノイズ抑制)。

```bash
[ -x "$HOME/.claude/agmsg/agmsg-append.sh" ] && \
  "$HOME/.claude/agmsg/agmsg-append.sh" gmo-bot-conoha <宛先> <カテゴリ> <期限> <blocking> "<1行サマリ>" || true
```

- 第1引数 <project> は `gmo-bot-conoha` 固定。
- 宛先/カテゴリ/期限/blocking は status の「mentor に確認したいこと」のタグと一致させる
  (`~/.claude/rules/mentor-reporting-format.md` 準拠)。
- スクリプト未配置でも壊れないよう必ず `[ -x … ] && … || true` ガードで包む。
- blocking=Y または 宛先=殿 のときは agmsg が macOS 通知を自動で出す (push 信号)。

---

## ★ Phase 3 移行スケジュール (mentor 2026-05-18 確定)

| 日 | アクション | 担当 |
|---|---|---|
| **2026-05-18** | conoha 役割再定義 (本 CLAUDE.md 作成) | mentor → conoha |
| **2026-05-22** | 中間レビュー、scout 移行準備の状況確認 | mentor + scout + conoha |
| **2026-05-23 (土)** | ★ HL Step 1 実行 ($10 経路検証、40-75 min) | conoha + ユーザー |
| 2026-05-24 (日) | (任意整理: 滋賀弁護士会、conoha 関与なし) | ユーザー |
| 2026-06-01 | scout cron を Mac→VPS 移行検討完了 | scout Claude + conoha |
| **2026-06-05** | strategy-lab Gate 2 結果報告、Mac→VPS 移行判断 | strategy-lab Claude + conoha |
| **2026-06-11** | sho-gun 案2' Day 30 売上判定、Mac→VPS 移行判断 | sho-gun Claude + conoha |
| 2026-06-15 | mentor 月次レビュー、conoha 役割再定義の総括 | mentor |
| HL 公式第2弾アナウンス検出後 | spec v8 finalize + Step 2 入金 | conoha + ユーザー |

---

## ★ 5/22 中間レビュー時の mentor 報告事項

(5/18 から準備、5/22 までに以下を整理)

1. 役割再定義の README/CLAUDE.md 反映状況 (本 CLAUDE.md = 反映済)
2. VPS リソース現状 (CPU / メモリ / ディスク / 稼働日数 + 提供可能容量)
3. HL Step 1 準備チェックリスト
4. monitoring 移管準備 (scout に渡す指標リスト + conoha 継続指標リスト)
5. 6月以降の各プロジェクト統合計画への準備状況

---

## 直近の作業優先順位 (5/18-5/22)

1. ★ **CLAUDE.md 作成** (本書、5/18 完了)
2. ★ **VPS 状態確認 + リソース提供可能容量試算** (5/18-5/19、`/api/admin/system-info` endpoint 新設要)
3. ★ **HL Step 1 準備** (5/23 実行向け、既存 `docs/hl-step1-route-checklist.md` 再点検)
4. **monitoring 移管準備** (scout に渡す指標リストドラフト、5/22 中間レビュー前)
5. **5/22 中間レビュー資料** (上記 1-4 の状況まとめ、mentor 用報告書)

---

## 過去の重要な記録 (referent only)

### bot 本体 (軸0 廃止) の経緯

- v0.9.5 (2/18) → v0.12.1 (2/22) で初の P&L/trip 改善 (-1.62 → -0.66)
- v0.13.1 (2/26) で P(fill) キャリブレーション実装、検証で P&L/trip = -1.08
- v0.13.3 (2/27) で per-order t_optimal cancel 実装、ERR-422 多発
- v0.14.0 (4/3 以降) で min_hold=180s 追加、レンジ相場で +1.19 黒字達成
- v0.14.1 (4/9) で close ERR-422 ゴースト誤判定修正、cooldown なし化
- v0.14.4 (4/18) で取引停止モード移行、FR 裁定撤退 + HL ピボット転換

### FR 裁定撤退の根拠 (2026-04-22 確定)

- Bitget Gate 1 FAIL (Sharpe 0.435, DSR=0, clean n=67)
- MEXC Gate 1 両シナリオ FAIL (n=52、baseline Sharpe 0.787 / DSR N=50=0.000、incentive on Sharpe 0.791 / DSR N=50=0.000)
- → リテール bot は CEX で構造的に不利 ([memory: project_lead-lag-conclusion.md])

### セキュリティ事故対応 (2026-04-18-19) 完了

- A (rotate) / B-pre (redact) / B (commit + push) / C (git history rewrite) **全完了**
- backup tag `backup/pre-filter-repo-20260419-220742` 保持
- ADMIN_PASS は紙メモ管理に統一 (Mac 側 `.env` の `VPS_PASS=masataka5692` は 4/18-19 rotate 前の値、意図的に未更新)
