# HL エアドロップ戦略 (Protocol Incentive Arbitrage) 設計

## ステータス

**DRAFT v4 (2026-04-22)** — MEXC FR 撤退確定 + 未解決論点 1/3/5 解決 + Gate 2 Custody 定量化 + ToS 日本制限確認。

### v4 の更新内容 (MEXC Gate 1 FAIL 確定 + 一次情報取得完了)

- **MEXC Gate 1 確定 FAIL**: n=52 両シナリオ (baseline fee 0.02% / incentive on fee 0.0%) ともに DSR(N=10)=0.50/0.52, DSR(N=50)=0.000。Gate 1 総合 FAIL 確定 → FR 撤退、HL ピボット本格着手段階へ
- **論点 1 解決 (HYPE 価格)**: 現在 **$40.56 (2026-04-21)** / MCap $9.67B / FDV $41.7B / 循環 238M / 上限 1.00B / ATH $59.26 (2025-09, 現在 -26.9%)。spec 想定 $20 は保守ケース、感応度テーブルを Gate 1 に追記
- **論点 3 解決 (Backpack APY)**: 2025-12 末の日本対応版 APY は **BTC 12% / USDC 17% (floating, 7 日ロール)**。spec 記載「4-5%」は機会費用を過小評価していた。$37 Backpack baseline の年間期待 = $4.44 (BTC) / $6.29 (USDC) が Gate 1 合格境界
- **論点 5 解決 (TVL top 3)**: HyperEVM native + HLP 除外 + Multi-chain protocol 除外で top 3 = **Kinetiq kHYPE $745M / Hyperliquid HLP $367M (除外) / HyperLend $343M**。データ源は DefiLlama API `api.llama.fi/protocols`, snapshot は入金直前, 更新周期は月次
- **追加タスク 5 解決 (Insurance fund)**: System address `0xfefefefefefefefefefefefefefefefefefefefe` / HL API `spotClearinghouseState` で **HYPE 43.5M tokens (≈$1.77B)** + stablecoins $20K 保有確認。DDoS 補償余力は HLP TVL の 30% ($110M) を大幅超過
- **追加タスク 6 一部解決 (ToS)**: URL `https://app.hyperliquid.xyz/terms` (SPA 本文は別途取得要)。Datawallet 経由で **日本は制限対象外** 確認 (2025-04-06 更新)。restricted は US 全州 / Ontario / Russia / DPRK / Iran / Cuba / Syria
- **論点 2, 4 は継続論点**: (2) 第 2 弾 snapshot date / 細則は **公式未発表**、weekly Discord/Twitter monitoring を Gate 2 (b) 2-6 に組み込み。(4) 第 1 弾データ分析は Step 1 経路検証と並行タスクに位置付け

### v3 の更新内容 (raw 還元 analyses 2 件起票完了、spec に具体パラメータ反映)

- **Gate 2 (a) 2-1 Tail risk**: lutwidse 原典還元 `wiki/analyses/hyperliquid-tail-safety-evidence.md` の 10 項目チェックリストを直接参照。特に:
  - 清算 ±20% バッファ (低流動性銘柄では ±30%) を明示 — 本 spec のレバレッジ 1 倍固定と併記
  - OI 上限時のクロスマージン化シナリオ (UMA 新台事例、店長証拠金 $70 億) を明示
  - 黒閃パターン = 他者清算への貢献度、倫理的留意
- **Gate 2 (a) 2-2 Custody risk**: DDoS 時補償は事例 1 件で将来保証なし、を明記。Insurance fund 規模を事前確認タスクに追加
- **Gate 2 (a) 2-4 Sybil**: 5000e12 原典還元 `wiki/analyses/sybil-resistance-operations-guide.md` を参照。**重要な wiki 発見として「プロ botter も 3 軸具体値を開示しない」事実を spec に明記**
- **Gate 1 trials**: `count_n_trials()` を `scripts/dsr_check.py` に実装済。`--auto-n-trials` で自動計算可能
- **EXP_SUMMARY**: テンプレート化済 (`docs/EXP_SUMMARY_TEMPLATE.md`)。本 spec の Gate 1 結果は本テンプレートで記録

### v2 の更新内容 (wiki-query 回答 + `wiki/analyses/dsr-protocol-incentive-operations-guide-2026-04-20.md` 準拠)

- Gate 1: universe 事前宣言を明示、Protocol Incentive 両シナリオ記録を必須化
- Gate 2: 標準 5 項目フレーム (analyses 推奨) + HL 固有 1 項目の階層構造に再編成。Hedge omission を **4-Pitfall (2) Execution のサブ項目** として分類
- Gate 3: 「過去 8 件 50% ポジ」の緩和条件を破棄し、**クロスセクショナル OOS 事前宣言式 5 要件** フレームに差し替え

## 背景

- **Bitget FR 裁定**: Gate 1 FAIL 確定 (Sharpe 0.435, DSR=0, clean window n=67)
- **MEXC FR 裁定**: **n=52 で Gate 1 FAIL 確定** (baseline: Sharpe 0.787 / DSR(N=10) 0.4995 / DSR(N=50) 0.000, incentive on: Sharpe 0.791 / DSR(N=10) 0.5151 / DSR(N=50) 0.000。両シナリオ FAIL, fee override 差分は +$0.51 のみで Protocol Incentive 効果ほぼゼロ)
- **FR 撤退確定** → 本 spec の HL エアドロ戦略が正式ピボット
- Hyperliquid 第 2 弾エアドロは tokenomics 上 38.888% が未配分状態で確保 (**公式は snapshot date / 細則未発表**、コミュニティは「期待値」として扱う)。現価 $40.56 換算で **$15.76B 相当** の pool

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
  - 第 1 弾配布実績 (31% of supply, 94k wallets, 平均 $28,500 at peak, **56.6% が ≤100 tokens**)
  - 第 2 弾 38.888% のうち自分の占有比
  - 占有比は「TVL 投入 × 期間 × プロトコル数」で相対決定される想定 (正式ルール未公表、wiki 5000e12 流の 3 軸 IP/Gas/時刻は本戦略では関係なし、複垢しないため)
- **HYPE 価格感応度テーブル** (基準: $40.56, 2026-04-21):

  | シナリオ | HYPE 価格 | 期待値倍率 | 備考 |
  |---|---|---|---|
  | 楽観 (+50%) | $60.84 | 1.5× | ATH $59.26 近傍 |
  | **baseline (0%)** | **$40.56** | **1.0×** | **現在、v4 基準** |
  | 保守 (-30%) | $28.39 | 0.7× | $20→$28 |
  | ストレス (-50%) | $20.28 | 0.5× | spec v3 までの基準価格 |
  | 破壊 (-70%) | $12.17 | 0.3× | 配布時点の下落織込み |

  Gate 1 PASS/FAIL 境界は「インセンティブ込み期待値 > 粗リターン欠損 + 機会費用 (Backpack baseline)」で計算。ストレス以下ではほぼ全シナリオで Backpack 併用の方が優位。

- **Sharpe は touch 頻度単位ではなく「戦略インスタンス単位」で評価**: 戦略丸ごと 1 instance、外部ベンチマーク (HYPE buy & hold) との差分で測る

### trial_count_N (analyses Topic 1 準拠)

- **Universe 事前客観宣言**: HyperEVM プロトコルから TVL top 3 を事前に固定 → selection bias なし
- **TVL top 3 選定基準 (v4 確定)**:
  - フィルタ: HyperEVM native protocol + **HLP 除外** (HLP は trading vault、delta-neutral touch 前提と整合しない) + **Multi-chain protocol 除外** (Morpho, Curve, Pendle 等は HyperEVM 特化とみなさない)
  - データ源: DefiLlama API `https://api.llama.fi/protocols`, filter `chains contains "Hyperliquid L1"`
  - snapshot 時刻: **入金直前** (Step 2 時点) のスナップショットを記録
  - 更新周期: **月次** (touch 設計 Step 3 の週次 touch とは独立)
  - Tie-break: TVL 同値時は 7d TVL 成長率高い側
  - **2026-04-22 時点の参考値** (DefiLlama API): Kinetiq kHYPE $745M / Hyperliquid HLP $367M (除外) / HyperLend $343M → **top 3 = Kinetiq / HyperLend / (Felix or 第3候補、入金直前に再取得)**
- **N = 1** が基本 (単一戦略、パラメータ最適化なし)
- 「touch 頻度・金額・分散プロトコル数」の組合せを暗黙に比較したとみなし、控えめに N=5
- DSR シナリオ: `[1, 5, 10]` (全シナリオ PASS で Gate 1 通過)
- `scripts/dsr_check.py --auto-n-trials` で自動計算:
  ```bash
  python3 scripts/dsr_check.py --path <hl_paper_trades.csv> \
      --auto-n-trials --n-params 5 --universe-filter-source ex-ante \
      --trial-scenarios 1,5,10 \
      --output /tmp/hl-gate1.json
  ```
- EXP_SUMMARY 記録必須フィールド (analyses Topic 1 推奨、[docs/EXP_SUMMARY_TEMPLATE.md](../../EXP_SUMMARY_TEMPLATE.md)):
  ```yaml
  trials:
    n_params: 5
    universe_filter_source: ex-ante
    prior_universe_size: 1    # ex-ante なので 1
    final_universe_size: 1    # ex-ante なので 1
    n_trials_effective: 5     # count_n_trials(5, 'ex-ante') の結果
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
- **機会費用 (v4 更新)**: Backpack JP の 2025-12 以降日本対応版 APY = **BTC 12% / USDC 17% (floating, 7 日ロール)**
  - $37 Backpack baseline の年間期待リターン = **$4.44 (BTC担保) / $6.29 (USDC lending)**
  - HL 側は $50 が 1 年で $10+ 期待値を出せるかが合格境界 (= 年率 20% 超、HYPE 割当 × baseline price で算定)
  - Backpack の確実性 > HL の不確実な期待値の場合、資金配分を Backpack 側に寄せる意思決定が妥当

---

## Gate 2 (Tail Safety) — 標準 5 項目 + HL 固有 1 項目

出典: `wiki/analyses/dsr-protocol-incentive-operations-guide-2026-04-20.md` Topic 4。
標準フレーム (5 項目) は analyses 推奨、(b) は HL 固有拡張。

### (a) 標準 5 項目 (analyses 推奨フレーム)

#### 2-1. Tail risk ( 4-Pitfall #4 Tail )

**典拠**: `wiki/analyses/hyperliquid-tail-safety-evidence.md` §2 §3 §7 (lutwidse 原典還元)

- **de-peg / HYPE 価格変動**: 配布時点で想定の 50% 以下に下落するシナリオ。ストレス: HYPE -70% で インセンティブ期待値 × 0.3 で再評価 → Gate 1 PASS 維持できるか
- **清算カスケード**: 自ポジションは **レバレッジ 1 倍固定** (touch 目的、クロスマージン禁止)
  - レバレッジを使う場合でも **本来の清算価格から ±20% のバッファ必須** (lutwidse 原典で最大 30% 乖離事例あり。低流動性銘柄では ±30% を下限とする)
  - 「パンピー → botter → パチカス参入 → ありえない清算髭 → 巻き添え全滅」の連鎖モデルを認識 (本戦略は巻き添え側に立たないことを最優先)
- **OI 上限時のクロスマージン化シナリオ**: 新台/虚無台で OI 上限到達時、店長証拠金がクロスマージン化 + 決済は Taker のみ (スプレッド最大 10%)
  - UMA 新台事例 (2024-02): 店長が OI 8 割占有、1 時間 1% FR、店長証拠金 $70 億
  - **対策**: OI 上限 70% 接近銘柄はポジション整理。新台 launch 直後は触らない
- **HLP 流動性供給はしない**: 本戦略のスコープ外。DDoS 事例 (2024-02) で +30%/日 爆益を観測したが、逆サイドのリスクは同量
- **黒閃パターンへの倫理的留意**: lutwidse 観察では「他者清算への貢献度」が高ポイント。**本戦略は touch 目的で積極的な他者清算誘発を行わない** (Sybil 判定/規制リスク)

#### 2-2. Custody risk ( 4-Pitfall 外、独立項目 )

**典拠**: `wiki/analyses/hyperliquid-tail-safety-evidence.md` §4 §8 §9

- HL 自体が破綻 / 撤退 / セキュリティ侵害するシナリオ
- **DDoS 時の運営補償**: 2024-02 末事例で運営が損失 + 含み益まで補償 (Insurance fund 充当)
  - ただし**事例 1 件、将来の保証なし** — spec では「補償あり前提にしない」設計とする
- **Insurance fund 現況 (v4 確定)**:
  - System address: `0xfefefefefefefefefefefefefefefefefefefefe` (on-chain, validator quorum required)
  - 取得手段: HL API `POST /info` body `{"type":"spotClearinghouseState","user":"<address>"}`
  - **保有資産 (2026-04-22 取得)**: HYPE 43.5M tokens + USDC $4,025 + USDE $9,902 + USDT0 $6,556 + USDH $2,806 + 小口多数
  - **HYPE 換算価値**: 43.5M × $40.56 = **≈$1.77B** (L1 最流動資産で保有)
  - DDoS 補償余力: HLP TVL の 30% (≈$110M) を大幅超過、2024-02 再現事例の損失補填は可能
  - **ただし市場暴落時**: HYPE 価格連動で担保価値も縮小 → ストレス時 (HYPE -50%) で $0.88B、(-70%) で $0.53B。破綻シナリオ下の実効余力は縮小前提
  - 2024-08-12 以降 trading fee の一部が HLP + Insurance fund に分配 → 時系列で残高は増加方向
- **Jeffrey Yan 単一点リスク**: VC なし個人開発体制 (Chameleon Trading 流) の継承
  - 物理セキュリティ懸念: 2026-01 以降の拉致事件増加で創業者警護雇用 (`wiki/sources/jeffrey-yan-hyperliquid-profile.md`)
  - **対策**: ポジションサイズ = プロトコル全面崩壊時の許容損失以下
- **Validator 分散化は未達 (2024-04 時点)**: 「現状の Hyperliquid は DEX とは言い難い」(lutwidse)
- **限度額**: 資金 13,060 JPY の **最大 50% ($50 前後)** に制限 (後述 kill-switch で再確認)

#### 2-3. Incentive 喪失シナリオ ( 4-Pitfall #4 Tail 拡張 )

- 配布キャンセル、条件変更、遅延、縮小
- **v4 確認結果**: HL tokenomics 上 38.888% は未配分として存在するが、**第 2 弾 snapshot date / 配布細則は公式未発表**。コミュニティは「期待値」として扱う
- 現時点でポイント対象と推定される 4 活動: perp trading / spot trading / HYPE staking / HyperEVM participation (参考: 外部ガイド調べ、HL 公式の正式アナウンスではない)
- モニタリング: HL 公式 Discord / Twitter / Blog の週次レビュー (Gate 2 (b) 2-6 の weekly monitoring と統合)
- Gate 1 の「インセンティブなし」シナリオ Sharpe が本項目の定量化そのもの

#### 2-4. Sybil 検出 → リワード剥奪 ( 4-Pitfall 外、独立項目 )

**典拠**: `wiki/analyses/sybil-resistance-operations-guide.md` §6 §7 (5000e12 原典還元)

- **複垢しない前提**だが、**単一アドレスで活動量過少の場合も Sybil 判定される可能性**
- **wiki 発見**: Sybil 耐性 3 軸 (IP/Gas/時刻) の具体パラメータは**プロ botter も開示していない** (競合回避・検出回避・規制回避のため)
  - 本 spec でも具体値は機密扱い、原則のみ spec に記載
  - 参考として lutwidse 2024-04 時点の HL Sybil 検出は「リファラル経路のみ」だが、HL 第 2 弾では間違いなく強化される
- **本戦略の Sybil 対応原則**:
  - 手動 touch + 人間らしいタイミング / 金額ばらつき
  - IP は自宅 residential (VPS 禁止、単一アドレスなので IP 分散も不要)
  - 時刻 jitter: cron は使わず、±1〜3 時間の手動実行ばらつき
  - 金額ばらつき: $10 中心に ±30% の乱数ばらつき (bot 規則性を避ける)
- **ToS 適合性確認 (v4)**:
  - ToS URL: `https://app.hyperliquid.xyz/terms` (SPA 本文は別途取得要、puppeteer 等で取得し `scripts/data_cache/hl_tos_YYYYMMDD.md` に保存)
  - **日本 = 制限対象外** (Datawallet 2025-04-06 確認)。restricted = US 全州 / Ontario / Russia / DPRK / Iran / Cuba / Syria
  - KYC-free で 180+ 国からアクセス可能
  - **本戦略 (単一アドレス + residential IP + 手動 touch) は ToS 範囲内**
- **運営による強制抽選リスク** (5000e12 の SoSoValue 事例):
  - 突然のルール変更で残り配布を強制抽選化される事例あり
  - **対策**: 配布確定 → 即 claim → 即売却 70% をルール化 (詳細は [EXP_SUMMARY_TEMPLATE.md](../../EXP_SUMMARY_TEMPLATE.md) の期待値モデル参照)
- **倫理境界の明文化** (analyses §7):
  - ToS 違反回避 (HL 公式 ToS の定期レビュー)
  - OFAC/SEC 規制動向の監視
  - detection-evasion エンジニアリング (グレー領域) は本戦略では実施しない

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
- **Weekly monitoring 統合 (v4)**: 以下を週次で手動確認し `scripts/data_cache/hl_monitoring_YYYYww.md` に記録
  - HL 公式 Discord アナウンス
  - HL 公式 Twitter (@HyperliquidX)
  - HL 公式 Blog / Docs の diff
  - HYPE 価格 / 24h 変動率
  - Insurance fund 残高 (HL API `spotClearinghouseState` で `0xfefe...` 確認)
  - HyperEVM TVL top 3 の順位変動 (universe 事前宣言の検証)
  - ToS 本文 diff (本文取得スクリプト確定後)

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

1. ~~HYPE 推定価格の感応度分析~~ → **v4 で解決** (現在 $40.56 / spec v3 基準 $20 は保守ケース、感応度テーブルを Gate 1 指標 2 に追記)
2. ~~HL 公式配布ルール細則公開時期~~ → **v4 で確認** (公式未発表、weekly monitoring に組み込み。外部依存のため「継続観察中」で固定)
3. ~~Backpack JP 資金配分比~~ → **v4 で解決** (Backpack APY 12-17% を採用、$50 HL / $37 Backpack は Backpack baseline 優位で再配分余地あり。入金前に再検討)
4. **[残存]** 第 1 弾配布データの具体分析方針: **Step 1 経路検証と並行で着手**、外部レポート (CoinGecko Learn / PANews / Arkham Intel) 引用方針を v4 採用、活動タイプ別配布量の 1 次集計は Step 2 入金判断前に完了
5. ~~HyperEVM プロトコル TVL top 3 の選定基準~~ → **v4 で解決** (HyperEVM native + HLP 除外 + Multi-chain protocol 除外、DefiLlama API 月次 snapshot)

---

## 関連ファイル

### プロジェクト内

- `scripts/dsr_check.py` — Gate 1 検定。`count_n_trials()` 実装済、`--auto-n-trials` で自動 N 計算
- `scripts/backtester/dsr.py` — DSR 核算モジュール (`expected_max_sr` / `deflated_sharpe_ratio`)
- `docs/EXP_SUMMARY_TEMPLATE.md` — 本 spec の Gate 1 結果記録用テンプレート (v1.0)
- `docs/superpowers/specs/2026-03-29-dsr-introduction-design.md` — DSR 導入設計
- `ハンドオフ.md` P1-1 HL エアドロ (第一候補) の詳細行動計画

### wiki 1 次典拠

- **`wiki/analyses/dsr-protocol-incentive-operations-guide-2026-04-20.md`** — 本 spec v2/v3 の最上位典拠 (Topic 1-4)
- **`wiki/analyses/hyperliquid-tail-safety-evidence.md`** — Gate 2 (a) 2-1 / 2-2 の 10 項目パラメータ出典 (lutwidse 原典還元、v3 で新規参照)
- **`wiki/analyses/sybil-resistance-operations-guide.md`** — Gate 2 (a) 2-4 の Sybil 運用原則と「3 軸非開示」の典拠 (5000e12 原典還元、v3 で新規参照)

### wiki 概念

- `wiki/concepts/protocol-incentive-arbitrage.md` (エッジ分類)
- `wiki/concepts/3-gate-review.md` (Gate 3 単一イベント OOS 節)
- `wiki/concepts/4-pitfall-checks.md` (Hedge omission = Execution サブ項目)
- `wiki/concepts/factor-zoo.md` (事前宣言 pre-registration)
- `wiki/concepts/deflated-sharpe-ratio.md` (N_trials 判定表)

### wiki ソース

- `wiki/sources/hyperliquid-airdrop-strategy.md` (加東たまお 上陸手順)
- `wiki/sources/hyperliquid-lazy-airdrop.md` (ズボラ 3 戦略)
- `wiki/sources/lutwidse-hyperliquid-analysis.md` (内部解剖、原典)
- `wiki/sources/5000e12-crypto-programming-collection.md` (エアドロ bot 技術、原典)
- `wiki/sources/jeffrey-yan-hyperliquid-profile.md` (創業者取材、ブリッジ経路)
- `wiki/sources/hyperliquid-hft-bot.md` (API 接続)
- `wiki/sources/sen-perpdex-reflection.md` (競合 PerpDEX 分析)

### claude-bridge

- `2026-04-19-tomui-OMG-airdrop-FRASYM-EVENT.md` (Gate 2 Hedge omission check 根拠)

---

## 次アクション

### v4 完了項目 (2026-04-22 セッション)

- [x] MEXC n=52 Gate 1 再検定 (両シナリオ FAIL 確定、FR 撤退決定)
- [x] 論点 1 (HYPE 価格感応度) — Gate 1 指標 2 に感応度テーブル追加
- [x] 論点 3 (Backpack 資金配分) — APY 12-17% を Gate 1 合格境界に反映
- [x] 論点 5 (TVL top 3 選定基準) — HyperEVM native + HLP 除外 + Multi-chain 除外
- [x] 追加 5 (Insurance fund) — $1.77B 相当 (HYPE 43.5M tokens) を Gate 2-2 定量化
- [x] 追加 6 一部 (ToS) — 日本制限対象外 確認、本文取得は puppeteer 化で別タスク

### v4 残タスク (次セッション以降)

1. **Step 1 — 経路検証 $10** (実資金移動、ユーザー承認で着手): bitflyer → Bybit USDC → Arbitrum → Hyperliquid の手数料 / 所要時間 / ETH ガス代計測
2. **論点 4 着手** (Step 1 と並行): 第 1 弾配布データの外部レポート集約 → `docs/hl-airdrop-s1-retro.md` (仮称) に作成。高サブセット {HL1, EIGEN} の比較可能性評点の 1 次データ源
3. **ToS 本文取得スクリプト**: `app.hyperliquid.xyz/terms` の SPA を puppeteer or playwright で取得し `scripts/data_cache/hl_tos_YYYYMMDD.md` に保存。週次 diff cron は本文取得手段確定後に別 commit
4. **HL 第 1 弾 10 項目チェック** (Gate 2 tail-safety-evidence の lutwidse 還元): 第 1 弾データ分析完了後に当て込み
5. **Step 2 — 入金判断**: Step 1 + 論点 4 完了 + HL 公式第 2 弾アナウンス or タイミング判断 → 初期 $50 HL / $37 Backpack (APY 差分を踏まえて再配分検討)
6. **Step 3/4 — touch 設計 + モニタリング**: 週次手動 touch、Discord/Twitter/Blog/Insurance fund/TVL top 3 を `hl_monitoring_YYYYww.md` で週次記録
