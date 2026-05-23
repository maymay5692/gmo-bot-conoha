---
title: HL Step 1 経路検証 — 実作業チェックリスト v0.3 (経路 A、bitbank → Arbitrum → HL)
purpose: spec v7 Step 1 ($10-15 経路検証) の経路 A 実作業手順 + 事前見積もり + 落とし穴 (5/22 中間レビュー B1 承認)
status: v0.3 (2026-05-22 中間レビュー B1 確定で起票 → session 21 = 2026-05-23 finalize、5/30 (土) 実行待ち)
parent: docs/superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md v7 §Step 1 ★ 2026-05-22 update
predecessor: docs/hl-step1-route-checklist.md (v0.2.2 archived、MEXC 経路、構造的盲点エビデンス保持)
scheduled_execution: **2026-05-30 (土)** JST 朝、mentor 5/22 B2 確定
related:
  - docs/mentor-mid-review-20260522.md section (3) ★ 5/22 B1-B5 確定
  - scripts/data_cache/retro_v0.5_candidates_20260519.md 候補 #7 (経路再設計 + Explore subagent 結果)
  - scripts/data_cache/route-redesign-research-20260521.md (Explore 全文 + 1 次ソース URL)
---

# HL Step 1 経路検証 — 実作業チェックリスト v0.3 (経路 A)

本書は [spec v7](superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md) Step 1 の経路 A 実作業手順書。**2026-05-22 中間レビュー B1 で mentor が経路 A を採用承認 ◎、B2 で Step 1 = 5/30 (土) 確定**。ユーザーがブラウザ UI + MetaMask + Arbiscan を見ながら各区間を進める際の checkpoint + 落とし穴 + 事前見積もり。

**実行予定**: 2026-05-30 (土) 朝、所要 20-40 min、$12-15 USDC 投入 (= ¥1,800-2,200、HL 最小預入 5 USDC + 安全マージン)。**mentor 役割境界遵守: 実弾移動はユーザー承認必須、conoha は経路 checklist 整備までで実行はユーザー手動 + 都度承認**。

## 経路 A (3 つの variant、user の bitbank 出金対応で確定)

### Path A1 (最短): bitbank が **USDC Arbitrum One 直接出金** 対応の場合 (要確認)

```
bitbank (JPY)
   ↓ ① JPY → USDC 購入 (取引所 or 販売所)
bitbank USDC wallet
   ↓ ② bitbank → MetaMask (Arbitrum One) USDC 送付
MetaMask Arbitrum USDC
   ↓ ③ HL bridge contract に USDC deposit
Hyperliquid L1 (HyperCore) USDC ← 最終到達点
```

### Path A2 (中庸): bitbank が **ETH Arbitrum One 直接出金** 対応 (Explore 調査済、2023/10/8 実装)

```
bitbank (JPY)
   ↓ ① JPY → ETH 購入
bitbank ETH wallet
   ↓ ② bitbank → MetaMask (Arbitrum One) ETH 送付
MetaMask Arbitrum ETH
   ↓ ③ MetaMask Arbitrum で ETH → USDC swap (Uniswap or 他 DEX)
MetaMask Arbitrum USDC
   ↓ ④ HL bridge contract に USDC deposit
Hyperliquid L1 (HyperCore) USDC ← 最終到達点
```

### Path A3 (fallback): bitbank が **Ethereum mainnet のみ** 対応の場合

```
bitbank (JPY)
   ↓ ① JPY → ETH (or USDC) 購入
bitbank ETH/USDC wallet
   ↓ ② bitbank → MetaMask (Ethereum mainnet) 送付
MetaMask Ethereum ETH/USDC
   ↓ ③ Across bridge (Ethereum → Arbitrum)、必要なら ETH → USDC swap
MetaMask Arbitrum USDC
   ↓ ④ HL bridge contract に USDC deposit
Hyperliquid L1 (HyperCore) USDC ← 最終到達点
```

→ Path A1 が最短 + 最安、Path A2 は Uniswap swap で +$0.5-2 gas、Path A3 は Across bridge で +$0.8-5 手数料

---

## 事前準備チェックリスト

### 必須アカウント

- [x] **bitbank 既存アカウント** (2026-05-21 user 確認済、開設済 + 本人確認完了)
- [x] **MetaMask wallet** (session 19 #4 確認済、seed phrase 保管済)
- [ ] **Hyperliquid アカウント** (app.hyperliquid.xyz、bridge deposit 後の reception 確認に必要)

### 必須残高

- [ ] **bitbank に JPY 2,500 円以上** (¥1,800-2,200 投入 + マージン)
- [ ] **MetaMask Arbitrum 上に ETH 約 0.001 以上** (gas 用、$3-4 相当)
  - Path A1: 不要 (USDC 直接送付なので gas は HL bridge deposit のみ、$0.10 程度)
  - Path A2: 自動 (bitbank から ETH を Arbitrum で受け取った時点で gas に充当可能)
  - Path A3: Across bridge 完了時点で Arbitrum 上に ETH 残ることが多い、不足分は Across で別途 bridge

### 必須情報確認 (5/30 前夜まで、5/29 (金) 夜に最終チェック)

- [ ] **HL bridge contract address**: `0x2df1c51e09aecf9cacb7bc98cb1742757f163df7` を [Arbiscan](https://arbiscan.io/address/0x2df1c51e09aecf9cacb7bc98cb1742757f163df7) で再確認 (5/21 #6 で実施済、5/30 前夜に再目視推奨)
- [ ] **HL 最小預入 5 USDC** (下回ると永久損失)
- [ ] **bitbank USDC / ETH の Arbitrum One ネットワーク出金対応** を 5/30 前夜までに確認 ([bitbank 出金画面] → ETH or USDC → ネットワーク選択肢に「Arbitrum One」あるか目視)
  - **Path A1 確定条件**: bitbank で USDC 出金時に「Arbitrum One」選択肢あり
  - **Path A2 確定条件**: bitbank で ETH 出金時に「Arbitrum One」選択肢あり (Explore 結果で確認、2023/10/8 実装)
  - **Path A3 確定条件**: 上記いずれもない場合、Ethereum mainnet 経由
- [ ] **Native USDC contract on Arbitrum**: `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` を確認 (5/21 #8 で実施済、bridged USDC.e と区別)
- [ ] **Across bridge UI 動作確認** (Path A3 のみ): [across.to](https://across.to) で wallet connect + Ethereum → Arbitrum USDC bridge UI が機能することを 5/30 前夜に確認

---

## 区間①: bitbank で JPY → ETH (or USDC) 購入

### 5/30 実行手順

#### Path A1/A2 共通 (ETH 購入の場合)

1. bitbank にログイン → 「取引所」(板取引、推奨) で **ETH/JPY ペア** 選択 (販売所はスプレッド広いので避ける)
2. **指値推奨** (現在価格 ±0.5% 以内)、成行は急変時のスリッページリスクあり
3. JPY 2,500 円相当を ETH 購入 (~0.006-0.008 ETH @ $400/ETH 想定、相場により変動)
4. 約定確認後、「資産」→「ETH」で残高確認

#### Path A1 専用 (USDC 購入の場合)

1. bitbank で「取引所」で **USDC/JPY ペア** 選択 (利用可能なら)
2. 板買い指値で USDC 13-15 相当購入

### 落とし穴

- **販売所スプレッド**: bitbank の販売所は 1-3% spread。必ず「取引所」板買い
- **レート変動**: 購入後送金前に数%動く可能性あり、マージン見込む
- **bitbank の取り扱い銘柄**: 2026-05 時点で ETH は確実、USDC は時期次第。USDC が取り扱いなしなら Path A2 確定

### 完了条件

- [ ] bitbank の ETH (or USDC) 残高が ¥2,000 相当 (=$13-15) 以上

---

## 区間②: bitbank → MetaMask 送付

### 共通手順 (Path A1/A2/A3)

1. MetaMask 起動 → 右上のネットワーク選択
   - **Path A1/A2**: **Arbitrum One** ネットワーク選択
   - **Path A3**: Ethereum Mainnet ネットワーク選択
2. 画面上部のアドレスを copy
3. bitbank → 「出金」→ ETH (or USDC) 選択
4. **アドレス管理** で初回なら新規登録: 受取人名 + 住所 + 送付目的 (2022/4/1 義務化、トラベルルール対象外でも個人ウォレット送付に必要)
5. ネットワーク選択: **Arbitrum One** (Path A1/A2) or **Ethereum mainnet** (Path A3)
6. 送付先アドレス: MetaMask copy アドレスを貼付
7. 金額入力 → 確認画面で **アドレス + ネットワーク** 両方確認
8. 2FA 入力 → 送付実行

### Critical な注意点

- **ネットワーク間違いで永久損失**: bitbank の出金ネットワーク選択は明示的に「Arbitrum One」を選ぶこと、ERC20 (Ethereum mainnet) を選ぶと Arbitrum wallet に届かない (アドレスは同じだが別ネットワーク)
- **少額テスト送付**: 初回は $1-3 相当でテスト送付 → 着金確認後に本送付推奨 (Path A1/A2)
- **bitbank 出金手数料**: ETH 0.005 ETH (~$2)、USDC は不明 (時期確認)

### 所要時間

- bitbank 出金処理 (内部審査): 数分〜数時間 (初回はやや長い可能性)
- ネットワーク確定: Arbitrum 数分、Ethereum 5-15 分

### 完了条件

- [ ] MetaMask の正しいネットワーク (Arbitrum One or Ethereum) に ETH/USDC 着金確認 ([Arbiscan](https://arbiscan.io) または [Etherscan](https://etherscan.io) で tx confirmation)

---

## 区間③: (必要時) ETH → USDC swap on Arbitrum (Path A2 のみ)

### 5/30 実行手順

1. MetaMask が Arbitrum One ネットワークであることを確認
2. [Uniswap](https://app.uniswap.org) にアクセス、wallet connect
3. ネットワーク Arbitrum One 選択
4. From: ETH、To: USDC (native USDC `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` を選択、Bridged USDC.e ではない)
5. Amount: 全 ETH の 70-80% (gas 残し)
6. Swap → MetaMask 署名 + tx 実行

### 落とし穴

- **bridged USDC.e を選んでしまう**: Uniswap の USDC が複数あるので contract address で照合 (native は `0xaf88d065e77c8cC2239327C5EDb3A432268e5831`)
- **slippage**: 0.5% 以下推奨、設定確認

### 完了条件

- [ ] MetaMask Arbitrum 上の USDC (native) 残高 $7-13 程度

---

## 区間③' (Path A3 専用): Across bridge で Ethereum → Arbitrum

### 5/30 実行手順 (Path A3 fallback の場合のみ)

1. [Across (across.to)](https://across.to) にアクセス、MetaMask wallet connect
2. From chain: Ethereum、To chain: Arbitrum
3. Asset: ETH or USDC (bitbank で購入したもの)
4. Amount: 全額 (gas 残し、bitbank ETH 0.001 程度は Ethereum gas 用に残す)
5. Quote 確認 → Across の **手数料が $0.8-5 内** であることを確認 (時期により変動)
6. Bridge → MetaMask 署名 + tx 実行
7. 15-30 分待機、MetaMask Arbitrum で着金確認

### 落とし穴

- **Across 手数料急騰**: Ethereum gas 高騰時に $10+ になる可能性、その場合は Stargate / Synapse / Arbitrum 公式 bridge と比較
- **bridge UI 詐欺サイト**: 必ず across.to のドメインを確認 (Arbitrum 公式 docs の link 経由推奨)

### 完了条件

- [ ] MetaMask Arbitrum 上の USDC (native) 残高 $7-13 程度

---

## 区間④: Hyperliquid bridge に USDC deposit

### 手順 (Hyperliquid 公式 UI 経由、推奨)

1. [app.hyperliquid.xyz](https://app.hyperliquid.xyz) にアクセス
2. MetaMask を connect → ネットワークが **Arbitrum One** であることを確認
3. 初回なら HL アカウント作成 (wallet 接続のみで OK、KYC は trading 前で個別判断)
4. 「Deposit」ボタン → USDC 選択
5. 金額入力 (Arbitrum 上の USDC 残高の 5 USDC 以上、推奨 $7-13 全額)
6. **EIP-2612 Permit 署名** (approve tx 不要、署名のみで完了)
7. MetaMask ポップアップで **署名** (gas なし) + **deposit tx** (Arbitrum gas $0.05-0.10)
8. tx confirm 後、HL の UI balance に反映 (1-3 分)

### 手動経由 (非推奨)

MetaMask から直接 bridge contract `0x2df1...f163df7` に USDC `transfer()` も可能だが、**EIP-2612 Permit を使わないと approve tx 余計に必要**。公式 UI 経由推奨。

### 落とし穴

- **5 USDC 未満で送ると永久損失**
- **bridge contract address を手入力すると typo リスク**: Arbiscan で contract 検証マーク確認 ([リンク](https://arbiscan.io/address/0x2df1c51e09aecf9cacb7bc98cb1742757f163df7))
- **EIP-2612 Permit 署名は tx ではない**: MetaMask で「Sign」と表示される、これは正常
- **Arbitrum gas 用の ETH 残高不足**: tx 失敗、ETH 0.001 以上確保

### 完了条件

- [ ] Hyperliquid UI に USDC 残高が反映 ($7-13 程度)

---

## 事前見積もり表 (Path A2 想定、最も標準的)

| 区間 | 固定手数料 | レート変動 | 所要時間 | 致命的リスク |
|---|---|---|---|---|
| ① bitbank JPY→ETH | spread 0.1-0.5% (取引所) | spread 0.1-0.5% | 1-5 分 | なし |
| ② bitbank→MetaMask ETH (Arbitrum) | $0-5 (bitbank ETH 出金手数料、時期次第) | ≈0 | 数分-数時間 | **ネットワーク誤選択** → 永久損失 |
| ③ ETH→USDC swap (Uniswap on Arbitrum) | $0.5-2 (Arbitrum gas) + spread 0.05% | spread 0.05% | 1 分 | **bridged USDC.e を選択** → HL 受け取り不可 |
| ④ Arb→HL bridge | Arb gas ≈$0.05-0.10 | ≈0 | 1-3 分 | **5 USDC 未満** → 永久損失 |
| **合計 (Path A2)** | **$0.6-7.1 + spread** | | **10-30 分** | |

**$12-15 USDC 投入時の最終到達額**: $8-13 (手数料 + spread で $2-4 減)

### Path A1 (USDC 直接対応の場合) 試算

| 区間 | 固定手数料 | 所要時間 |
|---|---|---|
| ① bitbank JPY→USDC | spread 0.1-0.5% | 1-5 分 |
| ② bitbank→MetaMask USDC (Arbitrum) | bitbank USDC 出金手数料 (時期次第、$0-5) | 数分-数時間 |
| ③ Arb→HL bridge | Arb gas ≈$0.05-0.10 | 1-3 分 |
| **合計 (Path A1)** | **$0.05-5.1** | **5-15 分** |

**$12-15 USDC 投入時の最終到達額**: $9-14 (Path A2 より高効率)

### Path A3 (Ethereum mainnet 経由) 試算

| 区間 | 固定手数料 | 所要時間 |
|---|---|---|
| ① bitbank JPY→ETH/USDC | spread 0.1-0.5% | 1-5 分 |
| ② bitbank→MetaMask (Ethereum mainnet) | bitbank Ethereum 出金手数料 + Ethereum gas $0-10 | 5-15 分 |
| ③ Across bridge (Ethereum → Arbitrum) | $0.8-5 (Across 手数料) + Ethereum gas $5-15 | 15-30 分 |
| ④ Arb→HL bridge | Arb gas ≈$0.05-0.10 | 1-3 分 |
| **合計 (Path A3)** | **$6-30 + spread** | **25-55 分** |

**$15-20 USDC 投入時の最終到達額**: $5-13 (Ethereum gas が支配的、Path A1/A2 より劣る)

---

## 全工程の所要時間 (Path A2 想定、手動実作業ベース)

- 事前準備 (MetaMask Arbitrum 確認 + bitbank ログイン): 5-10 分
- 実作業 (区間①-④): 10-30 分
- 確認作業 (Arbiscan 等で各区間の tx 検証): 5-10 分
- **合計**: 20-50 分 / 1 回 (Path A1 なら 15-30 分、Path A3 なら 30-60 分)

旧 MEXC 経路 (v0.2.2 40-75 分) から大幅短縮。

---

## トラブルシュート

### bitbank → MetaMask 着金しない

1. bitbank の出金履歴で tx hash 確認 (完了扱い?)
2. [Arbiscan](https://arbiscan.io/tx/<hash>) or [Etherscan](https://etherscan.io/tx/<hash>) で tx 成功確認
3. tx success なら MetaMask のトークンを手動追加 (native USDC = `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` on Arbitrum)
4. **ネットワーク誤選択だった場合**: 同じアドレスが別ネットワーク (Ethereum / Polygon / BSC) 上で残高を持つ可能性、各ネットワークで MetaMask を切り替えて確認
5. 48h 以上経過で bitbank サポートに問い合わせ (tx hash + amount + 送付先アドレス + ネットワーク)

### USDC が Arbitrum wallet にあるが Uniswap で swap できない

1. MetaMask の network が Arbitrum One か再確認
2. Uniswap で USDC token contract を `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` (native) に手動指定
3. ETH 残高 (gas) が 0.0005 以上あるか確認

### HL に deposit しても balance 反映しない

1. Arbiscan で bridge contract への tx success 確認
2. tx の USDC amount が 5 以上であることを確認
3. tx の USDC token が native (`0xaf88d...e5831`) であることを確認 (bridged USDC.e は受け取れない)
4. HL UI で wallet 接続 address が deposit 送信元と一致しているか確認
5. 5 分以上待っても反映しない場合、[HL Discord](https://discord.gg/hyperliquid) の #support で tx hash 提供

---

## 完了後のアクション

Step 1 完了時点で以下を記録し、Step 2 入金判断の根拠にする:

- [ ] 各区間の実測手数料を記録 → 本ファイルか別 evidence ファイル (`handoff/step1-evidence-2026-05-30/`) に追記
- [ ] 各区間の実測所要時間を記録
- [ ] HL 最終着金額が $7+ であることを確認 (試算 Path A2 = $8-13)
- [ ] spec v7 §Step 1 ★ 2026-05-22 update の経路試算 ($1.5-6) と実測の差分を分析
- [ ] **観測値の裏取り** (retro v0.5 #8 改善反映): 各 tx hash + 取引所 API + UI 残高の double check、推論からくる multiplicative 推定を flagged 化
- [ ] Step 2 で入金する具体金額を確定 — **spec v7 配分 B baseline = HL $350 + BP $150**、ただし spec v7 finalize (HL 公式第 2 弾アナウンス検出後) で配分判断を最終化
- [ ] mentor へ完了報告 (実測手数料 / 所要時間 / エラー有無 / HL 最終着金額)
- [ ] retro v0.5 候補 #3-5 (Step 1 実測由来) を `scripts/data_cache/retro_v0.5_candidates_20260519.md` に埋める

---

## ★ 2026-05-30 (土) 実行手順 (mentor 3軸役割再定義準拠 + 5/22 B1-B2 確定)

### 事前 (5/30 前夜まで、特に 5/29 (金) 夜最終チェック)

1. **ユーザー手動**: 必須準備チェックリスト (本書冒頭) を全項目 ✅ にする
   - 特に **bitbank の ETH/USDC Arbitrum One 出金対応** を 5/30 前夜までに目視確認、Path A1/A2/A3 確定
2. **ユーザー手動**: bitbank JPY 残高確認 (¥2,500 以上)
3. **ユーザー手動**: MetaMask Arbitrum 上に ETH 0.001 ETH 以上の gas (Path A1 のみ後で確保でも可)
4. **ユーザー手動**: HL bridge contract address (`0x2df1...f163df7`) を Arbiscan で 1 回再確認
5. **ユーザー手動**: HL UI ([app.hyperliquid.xyz](https://app.hyperliquid.xyz)) に wallet connect が機能することを 5/29 夜に確認
6. **conoha (Claude)**: 本 checklist を再度開き、5/29 夜に user と最終確認 + 着手 path (A1/A2/A3) を確定
7. **★ conoha (Claude) + ユーザー手動 (5/24 mentor 推奨)**: XRP 50 (5/22 GMO 内残留分、B3 = JPY 戻し採用) の売却完了確認
   - 5/29 夜に conoha が user に直接「XRP 売却完了しましたか? GMO JPY 残高は?」と確認
   - **未売却なら 5/30 当日朝に GMO で XRP→JPY 売却 → Step 1 開始 (GMO 内売却は即時、Step 1 開始を 10 分遅らせるのみ、5/24 mentor 補足準拠)**
   - GMO JPY 残高が Step 1 投入額 ¥1,800-2,200 と整合することを目視確認

### 5/30 (土) 当日

1. **conoha (Claude)**: 本 checklist を再度開き、ユーザーに「実行開始しますか?」と確認 (mentor 役割境界遵守)
2. **ユーザー手動**: 確定 path (A1/A2/A3) に従って各区間 (①-④) をブラウザ + MetaMask で実行、conoha は各区間完了時点で次に進む承認を求める
3. **conoha (Claude)**: 各区間で記録すべき値 (tx hash、手数料、所要時間) を都度確認、エラー時はトラブルシュート段で停止
4. **ユーザー手動**: スクリーンショットを `handoff/step1-evidence-2026-05-30/` 配下に保存 (各区間 1-2 枚、後で mentor 報告に使用)
5. **conoha (Claude)**: 全区間完了時点で結果を集計、mentor 用報告書ドラフトを作成
6. **観測値裏取り** (retro v0.5 #8 改善反映): 各区間の手数料 / 所要時間 = tx hash + 取引所 API + MetaMask UI 残高 + Arbiscan/Etherscan の最低 3 source double check

### 5/30 完了後 (~24h 内)

1. **conoha (Claude)**: 実測値を本 checklist の表に追記 (区間別手数料 + 所要時間)
2. **conoha (Claude)**: mentor へ報告書送付 (経路全体所要 / 各区間手数料 / エラー有無 / HL 最終着金額 / Step 2 入金判断材料)
3. **conoha (Claude)**: retro v0.5 candidate #3-5 (Step 1 実測由来) を埋める (`scripts/data_cache/retro_v0.5_candidates_20260519.md`)
4. **ユーザー判断**: Step 2 入金タイミング判断 (HL 公式第 2 弾アナウンス検出待ち、現状 未公開)

### 中断条件 (5/30 当日に発生した場合)

- 区間① bitbank で本人確認エラー → 中断、bitbank サポート連絡後再開
- 区間② bitbank 出金審査が予想より長い (4h 超) → 中断、待機、夜まで待っても来なければ翌週土曜 (6/6) 再実行
- 区間② ネットワーク誤選択 → 中断、Arbiscan / Etherscan で tx 確認、同じアドレスの別ネットワーク残高確認 (救済可能性あり)
- 区間③ Uniswap swap でスリッページ大 (1% 超) → 中断、slippage 設定変更後再試行
- 区間③' Across bridge 手数料急騰 ($10+) → 中断、Stargate / Synapse / Arbitrum 公式 bridge と比較、最安経路へ切替
- 区間④ HL bridge deposit 失敗 → 中断、HL Discord #support に tx hash 提供
- **進めない場合の判断**: 中断地点を記録 + 翌週土曜 (6/6) に再実行 or mentor に報告して判断仰ぐ

### evidence 保存場所

- ファイル: `handoff/step1-evidence-2026-05-30/` (実行日に新規ディレクトリ作成)
- 内訳: 各区間スクリーンショット (1-2 枚)、tx hash 一覧 (txt)、実測手数料 + 所要時間表 (md)、観測値裏取り結果 (md)

---

## 関連

- [spec v7](superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md) §Step 1 ★ 2026-05-22 update — 親 spec、経路再設計根拠
- [docs/hl-step1-route-checklist.md](hl-step1-route-checklist.md) — 旧 v0.2.2 MEXC 経路 (archive 状態、retro v0.5 #7 エビデンス)
- [docs/mentor-mid-review-20260522.md](mentor-mid-review-20260522.md) — mentor 中間レビュー報告書 (v0.2 finalize、B1-B5 確定反映)
- [scripts/data_cache/retro_v0.5_candidates_20260519.md](../scripts/data_cache/retro_v0.5_candidates_20260519.md) — retro v0.5 候補 #7 (経路再設計) + #8 (観測値プロセス改善)
- [scripts/data_cache/route-redesign-research-20260521.md](../scripts/data_cache/route-redesign-research-20260521.md) — Explore subagent web 調査全文 + 1 次ソース URL リスト
- [docs/hl-airdrop-s1-retro.md](hl-airdrop-s1-retro.md) — 第 1 弾 retro 分析 (v0.4)
- [CLAUDE.md](../CLAUDE.md) — プロジェクト 3軸役割定義 (軸2 HL airdrop 専用 + 軸1 VPS 基盤 + 軸0 廃止)
