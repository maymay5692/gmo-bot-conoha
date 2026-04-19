# HL エアドロップ戦略 (Protocol Incentive Arbitrage) 設計

## ステータス

**DRAFT v2 (2026-04-20)** — Gate 1 数値は FR 撤退確定後に埋める。本 spec は骨格を先行確定する。

v2 の更新内容 (wiki-query 回答 + `wiki/analyses/dsr-protocol-incentive-operations-guide-2026-04-20.md` 準拠):
- Gate 1: universe 事前宣言を明示、Protocol Incentive 両シナリオ記録を必須化
- Gate 2: 標準 5 項目フレーム (analyses 推奨) + HL 固有 1 項目の階層構造に再編成。Hedge omission を **4-Pitfall (2) Execution のサブ項目** として分類
- Gate 3: 「過去 8 件 50% ポジ」の緩和条件を破棄し、**クロスセクショナル OOS 事前宣言式 5 要件** フレームに差し替え

## 背景

- **Bitget FR 裁定**: Gate 1 FAIL 確定 (Sharpe 0.435, DSR=0, clean window n=67)
- **MEXC FR 裁定**: n=19 暫定で Gate 1 FAIL 寄り (Sharpe 0.996 / DSR N=10 PASS / DSR N=50 FAIL, fee-free replay でも変化なし)
- **FR 撤退の場合**、ハンドオフ P1-1 の HL エアドロ戦略がピボット第一候補
- Hyperliquid 第 2 弾エアドロ確定 (38.888%、HYPE 20 USD 換算で 80〜90 億 USD)

## エッジ仮説

- 分類: **Protocol Incentive Arbitrage** (wiki `concepts/protocol-incentive-arbitrage.md`)
- Ilmanen 2 分類の外側、Sharpe 1 → 50 の事例が wiki `sources/hft-trader-edge-attribution.md` に記録あり
- 本質: **PnL 単独で測ると負でも、インセンティブ込みで正になる構造**
- 消えない理由: HL が市場インフラとして持続的に参加者を求める限り、後から入る参加者への配布が継続する

## 参加条件 (wiki `sources/hyperliquid-airdrop-strategy.md` 加東たまお式)

1. Arbitrum → ETH/USDC 準備
2. Hyperliquid 入金
3. HyperEVM Transfer
4. エコシステム全体に分散参加 (TVL 高 + ポイント制プロトコル優先)
5. 定期的な touch (1 回では不十分)

---

## Gate 1 (Accountability)

**方針**: リターン stream を 2 段階で評価する。

### 指標 1 — 粗リターン (PnL のみ)

- HL trading 自体の手数料 / spread / 価格変動損
- 想定: **ほぼ 0 〜 小幅マイナス** (delta-neutral に近い touch を繰り返す場合)
- Sharpe 計算不可 (touch 頻度が低くサンプル数不足)

### 指標 2 — インセンティブ込みリターン

- 粗リターン + エアドロ期待値 (割当推定 × HYPE 推定価格)
- 割当推定の計算基礎:
  - 第 1 弾配布実績 (31% of supply, 94k wallets)
  - 第 2 弾 38.888% のうち自分の占有比
  - 占有比は「TVL 投入 × 期間 × プロトコル数」で相対決定される想定 (正式ルール未公表、wiki 5000e12 流の 3 軸 IP/Gas/時刻は本戦略では関係なし、複垢しないため)
- **Sharpe は touch 頻度単位ではなく「戦略インスタンス単位」で評価**: 戦略丸ごと 1 instance、外部ベンチマーク (HYPE buy & hold) との差分で測る

### trial_count_N (analyses Topic 1 準拠)

- **Universe 事前客観宣言**: HyperEVM プロトコルから TVL top 3 を事前に固定 → selection bias なし
- **N = 1** が基本 (単一戦略、パラメータ最適化なし)
- 「touch 頻度・金額・分散プロトコル数」の組合せを暗黙に比較したとみなし、控えめに N=5
- DSR シナリオ: `[1, 5, 10]` (全シナリオ PASS で Gate 1 通過)
- EXP_SUMMARY 記録必須フィールド (analyses Topic 1 推奨):
  ```yaml
  trials:
    n_params: 5
    universe_filter_source: ex-ante
    prior_universe_size: <TVL top N の N>
    final_universe_size: 3
    n_trials_effective: 5
  ```

### Protocol Incentive 両シナリオ記録 (analyses Topic 2 準拠)

**必須**: Sharpe / DSR をインセンティブ **あり / なし** の両方で計算し、双方を Gate 2 Tail Safety に記録する。

- インセンティブあり: HYPE 配布期待値 + HL trading 手数料無料/割引を含むリターン stream で再計算
- インセンティブなし: 配布キャンセル / 遅延を想定した baseline
- `dsr_check.py --fee-rate 0.0` 等で fee override して PnL 再生成し、各シナリオの Sharpe/DSR を出力

### 合格基準

- 粗リターン PSR > 0.5 (マイナスでも小幅に抑えられていれば許容)
- **インセンティブあり / なし 両シナリオ** の Sharpe/DSR を記録
- インセンティブ込み期待値 > 粗リターン欠損 + 機会費用
- 機会費用 = 同額を Backpack JP レンディング (APY 4-5%) に置いた場合のリターン (`sources/european-crypto-guide-2026.md`)

---

## Gate 2 (Tail Safety) — 標準 5 項目 + HL 固有 1 項目

出典: `wiki/analyses/dsr-protocol-incentive-operations-guide-2026-04-20.md` Topic 4。
標準フレーム (5 項目) は analyses 推奨、(b) は HL 固有拡張。

### (a) 標準 5 項目 (analyses 推奨フレーム)

#### 2-1. Tail risk ( 4-Pitfall #4 Tail )

- **de-peg / HYPE 価格変動**: 配布時点で想定の 50% 以下に下落するシナリオ。ストレス: HYPE -70% で インセンティブ期待値 × 0.3 で再評価 → Gate 1 PASS 維持できるか
- **清算カスケード**: 自ポジションは **レバレッジ 1 倍固定** (touch 目的、クロスマージン禁止)。HLP (Hyperliquid Liquidity Pool) への流動性供給はしない (wiki `lutwidse-hyperliquid-analysis.md` で DDoS 時の補償有無が不透明、詳細は raw/ 還元待ち)

#### 2-2. Custody risk ( 4-Pitfall 外、独立項目 )

- HL 自体が破綻 / 撤退 / セキュリティ侵害するシナリオ
- 過去事例: DDoS 攻撃 (補償有無は wiki `lutwidse-hyperliquid-analysis.md` で言及のみ、`analyses/hyperliquid-tail-safety-evidence.md` 起票後に具体的 tail パラメータを反映予定)
- 限度額: 資金 13,060 JPY の **最大 50% ($50 前後)** に制限 (後述 kill-switch で再確認)

#### 2-3. Incentive 喪失シナリオ ( 4-Pitfall #4 Tail 拡張 )

- 配布キャンセル、条件変更、遅延、縮小
- HL 公式アナウンスが「第 2 弾 38.888%」を明言済だが、**配布ルールの細則は未公開**
- モニタリング: HL 公式 Discord / Twitter / Blog の週次レビュー
- Gate 1 の「インセンティブなし」シナリオ Sharpe が本項目の定量化そのもの

#### 2-4. Sybil 検出 → リワード剥奪 ( 4-Pitfall 外、独立項目 )

- 複垢しない前提だが、**単一アドレスで活動量過少の場合も Sybil 判定される可能性**
- 対策: 手動 touch + 人間らしいタイミング / 金額ばらつき (詳細は下記「Sybil リスク管理」)
- `analyses/sybil-resistance-operations-guide.md` (5000e12 raw 還元) 起票後に具体的パラメータを反映予定

#### 2-5. Hedge omission / 構造完全性 check ( 4-Pitfall #2 Execution のサブ項目 )

出典: claude-bridge `2026-04-19-tomui-OMG-airdrop-FRASYM-EVENT.md`、analyses Topic 4 で Execution pitfall サブ項目に分類決定。

- **delta-neutral を意図した戦略で片脚を省略していないか**
- HL で long 持ちっぱなしで FR を継続支払いしていないか (FR が年率 100% 超の時期)
- ヘッジコストを惜しむ行為は「期待値向上」ではなく「ロット制約緩和の放棄」
- **本戦略のヘッジ方針**:
  - touch は **現物 buy & hold (Spot)** を基本とし、perp は使わない
  - やむを得ず perp を使う場合は CEX (Backpack / Bybit) で逆ヘッジを張る
  - FR 支払いシナリオを損益計算に含める

### (b) HL 固有拡張 (analyses 外、本 spec で追加)

#### 2-6. 契約レジーム変更 ( 4-Pitfall #1 Regime 拡張 )

出典: claude-bridge FRASYM-EVENT 即時実行推奨 #1。

- HL の API 仕様変更、手数料体系変更、証拠金ルール変更、配布条件変更の監視
- kill-switch 条件: 「仕様変更アナウンスから 24h 以内に戦略見直し」
- サバイバーシップバイアス規則 (取引所レベル): HL が存続している前提で評価していることを明示トラック

---

## Gate 3 (OOS 再現性) — クロスセクショナル OOS 事前宣言式

**構造的困難** — 本戦略は単一イベント (第 2 弾配布) が対象で、時系列 IS/OOS split 不可能。

出典: `wiki/analyses/dsr-protocol-incentive-operations-guide-2026-04-20.md` Topic 3 のフレームに準拠。wiki `concepts/factor-zoo.md` の **事前宣言 (pre-registration)** 原則を継承。

### 要件 1. サンプル事前宣言

**N = 8 件** のクロスセクショナル OOS サンプル:

| # | 事例 | 年 | 除外/採用理由 |
|---|---|---|---|
| 1 | UNI | 2020 | DEX エアドロの原点、形式的類似は低い |
| 2 | DYDX | 2021 | CEX→perp、参加形態は perp trade 類似 |
| 3 | APT | 2022 | chain-level、参加形態は低類似 |
| 4 | ARB | 2023 | L2、on-chain activity 条件、競合密度は類似 |
| 5 | JTO | 2023 | Solana DEX、HL エコシステムと構造的類似 |
| 6 | JUP | 2024 | Solana DEX aggregator、参加形態中類似 |
| 7 | EIGEN | 2024 | restaking、参加要件明確、HL に最も近い設計 |
| 8 | HL 第 1 弾 | 2024 | **最重要比較対象**。同プロトコルの前例 |

FTX 絡みのエアドロ事例は **取引所破綻の影響**を受けているため除外 (サバイバーシップバイアス規則)。

### 要件 2. 比較可能性テスト

analyses Topic 3 の評点表をそのまま採用:

| 事例 | プロトコル規模 | 参加形態類似 | 競合密度類似 | **総合** |
|---|---|---|---|---|
| HL1 | 高 | 高 | 高 | **高** |
| EIGEN | 高 | 中 | 高 | **高** |
| JTO | 中 | 高 | 中 | 中 |
| JUP | 高 | 中 | 中 | 中 |
| APT | 中 | 低 | 中 | 中 |
| ARB | 高 | 低 | 高 | 中 |
| DYDX | 中 | 高 | 低 | 中 |
| UNI | 高 | 低 | 低 | 中 |

**高サブセット = {HL1, EIGEN}** の 2 件。

### 要件 3. 層別閾値 (spec 事前宣言)

- **高サブセット (HL1, EIGEN)**: **100% ポジティブ必須** (2/2)。1 件でもネガなら HL2 はイベント特殊性疑いで要再検討
- **全 8 件**: **62% 以上ポジティブ** (5/8 以上)

### 要件 4. 反証条件 (spec 事前宣言)

- 高サブセットの 1 件でもネガ → Gate 3 FAIL 再検討 (戦略保留)
- 全 8 件で 5 件未満ポジ → Gate 3 FAIL (戦略破棄候補)
- 両方 PASS なら Gate 3 PASS として HL2 実行に進む

### 要件 5. 事後評価ループ

- HL2 配布完了後、実際の結果を `analyses/hyperliquid-airdrop-retro-2026.md` (仮称) に記録
- 比較可能性評点の事後 validation (想定外れ事例を log 化)
- 次のエアドロ戦略 spec の prior 更新に使用 (ベイズ更新 rule は未確定、claude-bridge 側で検討中)

### 補足: 一次データ取得方針

- UNI, DYDX, APT, ARB: 公開レポート + wiki `sources/token-airdrop-feature.md` を 1 次資料として再分析
- JTO, JUP, EIGEN: 2024 年発生、公開分析が豊富。外部リサーチを引用
- **HL 第 1 弾** (2024/11, 31%): 最重要比較対象。wiki `sources/hyperliquid-airdrop-strategy.md` + `sources/lutwidse-hyperliquid-analysis.md` + 外部レポートで受取ユーザー構成 / 活動タイプ別割当量を分析

---

## 実装ステップ

### Step 1 — 経路検証 ($10 相当)

- bitflyer → Bybit USDC → Arbitrum → Hyperliquid
- 参考: wiki `sources/jeffrey-yan-hyperliquid-profile.md` + `sources/hyperliquid-hft-bot.md`
- 各ステップの手数料 / 所要時間 / ETH ガス代を計測
- MEXC Gate 1 結論待ちの期間に着手可能 (sunk cost $10 相当で収まる)

### Step 2 — 入金判断

- MEXC Gate 1 結論確定後に本体入金
- 初期投入: $50 (= 約 7,500 JPY、資金の 58%)
- 残り $37 (約 5,500 JPY) は Backpack JP レンディング baseline として保持

### Step 3 — touch 設計

- 週次 touch (毎週日曜 JST 22:00)
- プロトコル: HL 本体 + HyperEVM の TVL top 3
- ポジション: 各プロトコル $10 相当、delta-neutral (spot or offsetting perp on CEX)
- 手動実行 → 慣れたら自動化検討

### Step 4 — モニタリング

- HL 公式アナウンス週次チェック (Discord / Twitter / Blog)
- HYPE 価格、TVL、HLP 利回りの日次ログ
- 自ポジションの健全性 (清算距離、FR 支払累計) 週次ログ

---

## Kill-switch 条件

以下のいずれかが発生したら戦略停止 + 資金引き上げ:

1. HL 手数料体系変更アナウンス
2. HL セキュリティインシデント (ハック / 凍結 / 引き出し停止)
3. HYPE 価格 -50% 以上 (30 日間)
4. HLP 流動性 -50% 以上 (30 日間) — HL 全体のエコシステム縮小シグナル
5. 自ポジション含み損 -30% 以上
6. 配布条件の重大変更アナウンス
7. Sybil 検出警告 (アカウントへの個別通知)

---

## Sybil リスク管理

本戦略は **単一アドレス運用** (複垢しない) を前提。よって:

- IP 分散 / Gas パターン / 時刻分散 (wiki `5000e12-crypto-programming-collection.md`) は **適用対象外**
- 代わりに「1 アドレスに活動を集中させ、活動量で割当を稼ぐ」設計
- リスク: **活動量過少で Sybil 扱い** (アクティビティが bot 判定閾値以下)
- 対策: 手動 touch + 人間らしいタイミング / 金額ばらつき

---

## 未解決論点

1. HYPE 推定価格の感応度分析 (20 USD 基準は保守 or 楽観 ?)
2. HL 公式配布ルール細則公開時期の見込み
3. Backpack JP レンディング併用時の資金配分比 ($50 HL / $37 Backpack は妥当か)
4. 第 1 弾配布データの具体分析方針 (外部レポート引用 or 自前分析)
5. HyperEVM プロトコル TVL top 3 の選定基準 (動的更新方針)

---

## 関連ファイル

- `scripts/dsr_check.py` — Gate 1 検定 (N_trials シナリオ化済、本 spec の Gate 1 でも使う)
- `ハンドオフ.md` P1-1 HL エアドロ (第一候補) の詳細行動計画
- **wiki `analyses/dsr-protocol-incentive-operations-guide-2026-04-20.md`** — 本 spec v2 の 1 次典拠 (Topic 1-4)
- wiki `concepts/protocol-incentive-arbitrage.md`
- wiki `concepts/3-gate-review.md` / `concepts/4-pitfall-checks.md` / `concepts/factor-zoo.md` (事前宣言)
- wiki `sources/hyperliquid-airdrop-strategy.md` (加東たまお)
- wiki `sources/hyperliquid-lazy-airdrop.md` (ズボラ)
- wiki `sources/lutwidse-hyperliquid-analysis.md` (内部解剖、raw 還元 `analyses/hyperliquid-tail-safety-evidence.md` 起票待ち)
- wiki `sources/5000e12-crypto-programming-collection.md` (raw 還元 `analyses/sybil-resistance-operations-guide.md` 起票待ち)
- wiki `sources/jeffrey-yan-hyperliquid-profile.md` (ブリッジ経路)
- wiki `sources/hyperliquid-hft-bot.md` (API 接続)
- claude-bridge `2026-04-19-tomui-OMG-airdrop-FRASYM-EVENT.md` (Gate 2 Hedge omission check 根拠)

---

## 次アクション

1. MEXC n=30 到達 + Gate 1 再検定 (FR 撤退確定の前提条件)
2. FR 撤退確定後、Step 1 (経路検証 $10) 着手
3. 並行して本 spec の未解決論点 1-5 を詰める
4. Step 2 (入金) は経路検証完了 + 第 1 弾データ分析完了後
