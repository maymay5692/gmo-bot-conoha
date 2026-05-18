---
title: HL Step 1 経路検証 — 実作業チェックリスト
purpose: spec v7 Step 1 ($10 経路検証) の実作業手順 + 事前見積もり + 落とし穴
status: v0.2.1 (2026-05-19 session 15、事前準備チェック 2 件追記: トラベルルール事前登録 + MEXC native USDC 確認)
parent: docs/superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md v7
scheduled_execution: 2026-05-23 (土) JST 朝〜午後、mentor 確定スケジュール (2026-05-18 確定)
---

# HL Step 1 経路検証 — 実作業チェックリスト

本書は [spec v7](superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md) Step 1 の実作業手順書。ユーザーがブラウザ UI を見ながら各区間を進める際の checkpoint + 落とし穴 + 事前見積もり。

**実行予定**: 2026-05-23 (土)、所要 40-75 min、$10 = ¥1,500 投入。**mentor 役割境界遵守: 実弾移動はユーザー承認必須、conoha は経路 checklist 整備までで実行はユーザー手動 + 都度承認**。

## 経路

```
国内取引所 (JPY)
   ↓ ①JPY → XRP 購入
国内取引所 XRP wallet
   ↓ ②XRP 送金 (手数料ゼロ)
MEXC XRP wallet
   ↓ ③XRP → USDC swap
MEXC USDC wallet
   ↓ ④USDC 出金 (Arbitrum ネットワーク、$1-2)
Arbitrum One USDC wallet (MetaMask)
   ↓ ⑤HL bridge contract に deposit (gas $0.10)
Hyperliquid L1 (HyperCore) USDC ← 最終到達点
```

---

## 事前準備チェックリスト

### 必須アカウント

- [ ] 国内取引所 (SBI VC Trade / GMO コイン / bitflyer のいずれか) 本人確認完了済
- [ ] MEXC アカウント (本プロジェクトで FR monitor に使用中、開設済)
- [ ] MetaMask wallet インストール + seed phrase 安全保管

### 必須残高

- [ ] 国内取引所に **JPY 1,800 円以上** (≈ $12、マージン含む)
- [ ] MetaMask Arbitrum 上に **ETH 約 0.001** 以上 (gas 用、$3-4 相当)
  - Arbitrum ETH の入手: MEXC から ETH を Arbitrum network で出金 ($1 手数料) or Bybit 経由 (使えないので NG) or 既存 Arbitrum wallet から
  - **新規 MetaMask の場合は ETH ガス代が別途必要**。既存 wallet に 0.001 ETH があれば不要

### 必須情報確認

- [ ] HL bridge contract address: `0x2df1c51e09aecf9cacb7bc98cb1742757f163df7` を [Arbiscan](https://arbiscan.io/address/0x2df1c51e09aecf9cacb7bc98cb1742757f163df7) で確認 (**確認なしで送ると永久損失**)
- [ ] HL 最小預入 **5 USDC** (下回ると永久損失)
- [ ] MEXC が Arbitrum ネットワークで **native USDC** 対応していることを 5/23 前夜までに `Withdraw` ページで確認 (bridged USDC.e は HL bridge で受け取れない、native USDC contract `0xaf88d065e77c8cC2239327C5EDb3A432268e5831` であることを Arbiscan で照合)
- [ ] **国内取引所の送金先事業者リストに MEXC が登録済** (トラベルルール対応、bitflyer / GMO 等で利用時に必須、初回送金は事業者選択 + 書類提出で数日遅延の可能性あり → **5/23 前夜まで未完了なら経路②区間で詰む**)

---

## 区間①: 国内取引所で JPY → XRP 購入

### 選択肢別手順

**SBI VC Trade の場合** (送金無料、本人確認済み前提):
1. ログイン → 「暗号資産」→ XRP 選択
2. 「取引所」で板買い (販売所はスプレッド広いので避ける) or 現物取引画面で指値
3. JPY 1,500 円相当を XRP 購入 (\$10 + マージン $2)

**GMO コインの場合** (送金無料):
1. ログイン → 「取引所」で XRP/JPY 選択
2. 指値 or 成行で XRP 購入

**bitflyer の場合** (XRP 送金のみ無料、ETH/BTC は不可):
1. ログイン → 「bitFlyer Lightning」→ XRP/JPY 選択
2. 指値で XRP 購入 (販売所は避ける)

### 落とし穴

- **販売所スプレッド**: 国内の販売所は 3-5% spread。必ず「取引所」板買い
- **XRP レート変動**: 購入後送金前に数%動く可能性あり、マージン見込む

### 完了条件

- [ ] 国内取引所の XRP 残高が 1,200 円相当 (約 5-6 XRP @ $2.5) 以上

---

## 区間②: 国内取引所 → MEXC XRP 送金

### 手順

1. MEXC にログイン → 「Assets」→「Deposit」→ XRP 選択
2. **Destination Tag / Memo が表示される** ← これをメモ
3. Deposit address をコピー

### Destination Tag (**Critical**)

XRP は **Destination Tag (Memo) が必須**。MEXC の tag をコピーし忘れると、**資金が MEXC の hot wallet に入っても自分のアカウントに credit されない**。

4. 国内取引所で「送金」選択
5. アドレス欄に MEXC の XRP address
6. **Memo / Destination Tag 欄に MEXC の tag を必ず入力**
7. 送金額を入力、確認画面で **アドレス + tag 両方** 確認
8. 2FA 入力 → 送金実行

### 所要時間

- XRP 送金自体: 5-15 秒
- MEXC 着金: 5-15 分 (ネットワーク遅延 + MEXC 内部処理)
- bitflyer の場合は「トラベルルール」対応で初回送金時に追加書類要求あり

### 落とし穴

- **Destination Tag 未入力 = 資金凍結** (取り戻すには MEXC サポート問い合わせ、数日〜数週間)
- **少額テスト送金推奨**: 初回は 1 XRP ($2.5) 相当で動作確認 → 成功後に本送金
- **国内取引所の送金先ホワイトリスト**: 2023 トラベルルール導入で事前登録が必要な場合あり
- bitflyer: 2024 年以降「送金先事業者の選択」が必須、MEXC が選択肢に存在するか要確認

### 完了条件

- [ ] MEXC Assets に XRP 着金確認

---

## 区間③: MEXC で XRP → USDC swap

### 手順

1. MEXC → 「Trade」→「Spot」→「XRP/USDT」ペア選択
2. XRP を **USDT に売却** (市場価格成行 or 指値)
3. 次に「USDT/USDC」ペアで USDT → USDC 変換 (spread 最小)
4. または直接「XRP/USDC」ペアがあればそれを使う (XRP/USDC の板を確認)

### 別経路: MEXC の Convert 機能

1. 「Convert」タブで XRP → USDC 直接変換
2. スプレッド込みのレート表示、確認してシンプルに swap
3. **Convert はスプレッド大きい場合あり、Spot 板の方が有利なことが多い**

### 完了条件

- [ ] MEXC Spot wallet に USDC 残高 $6-8 (spot 手数料 0.1% 込みで)

---

## 区間④: MEXC から Arbitrum USDC 出金

### 手順

1. MEXC → 「Assets」→「Withdraw」→ USDC 選択
2. **ネットワーク選択画面で `Arbitrum One` (ARB) を必ず選択** ← 他ネットワークは不可
3. Withdrawal address 欄に自分の **MetaMask Arbitrum アドレス**
4. 金額入力 (MEXC 手数料 $1-2 が引かれる)
5. 2FA + Email 確認

### Critical な注意点

- **ネットワーク間違いで永久損失**: Ethereum / Optimism / Polygon を選ぶと Arbitrum wallet に届かない
- **MetaMask の Arbitrum ネットワーク確認**: Chrome 右上 MetaMask → ネットワーク切替で「Arbitrum One」を選択できることを確認
- **MEXC の Arbitrum USDC 出金ミニマム**: $5-10 程度 (時期により変動)

### 所要時間

- MEXC 処理: 数分
- Arbitrum 確認: 1-5 分 (Arbitrum の block time 短い)

### 完了条件

- [ ] MetaMask Arbitrum 上の USDC 残高確認 (Arbiscan でも可: https://arbiscan.io/address/<your-address>)

---

## 区間⑤: Hyperliquid bridge に USDC deposit

### 手順 (Hyperliquid 公式 UI 経由、推奨)

1. [app.hyperliquid.xyz](https://app.hyperliquid.xyz) にアクセス
2. MetaMask を connect → ネットワークが **Arbitrum One** であることを確認
3. 「Deposit」ボタン → USDC 選択
4. 金額入力 (Arbitrum 上の USDC 残高の 5 USDC 以上)
5. **EIP-2612 Permit 署名** (approve tx 不要、署名のみで完了)
6. MetaMask ポップアップで **署名** (gas なし) + **deposit tx** (Arbitrum gas $0.1)
7. tx confirm 後、HL の UI balance に反映 (1-3 分)

### 手動経由 (非推奨)

MetaMask から直接 bridge contract `0x2df1...f163df7` に USDC `transfer()` も可能だが、**EIP-2612 Permit を使わないと approve tx 余計に必要**。公式 UI 経由推奨。

### 落とし穴

- **5 USDC 未満で送ると永久損失**
- **bridge contract address を手入力すると typo リスク**: Arbiscan で contract 検証マーク確認 ([リンク](https://arbiscan.io/address/0x2df1c51e09aecf9cacb7bc98cb1742757f163df7))
- **EIP-2612 Permit 署名は tx ではない**: MetaMask で「Sign」と表示される、これは正常
- **Arbitrum gas 用の ETH 残高不足**: tx 失敗、ETH 0.001 以上確保

### 完了条件

- [ ] Hyperliquid UI に USDC 残高が反映 ($6-8 程度)

---

## 事前見積もり表

| 区間 | 固定手数料 | レート変動 | 所要時間 | 致命的リスク |
|---|---|---|---|---|
| ① 国内 JPY→XRP | 0 | spread 0.1-0.5% | 1-5 分 | なし |
| ② 国内→MEXC XRP | **0** | ≈0 | 5-15 分 | **Destination Tag 未入力** → 資金凍結 |
| ③ MEXC XRP→USDC | spot 0.1% | spread 0.05% | 30 秒 | なし |
| ④ MEXC→Arb USDC | $1-2 | ≈0 | 5 分 | **ネットワーク誤選択** → 永久損失 |
| ⑤ Arb→HL bridge | Arb gas ≈$0.10 | ≈0 | 1-3 分 | **5 USDC 未満** → 永久損失 |
| **合計** | **$1.1-2.1 + spread** | | **20-30 分** | |

**$10 投入時の最終到達額**: $6.5-8.0 (手数料 + spread で $2-3.5 減)

---

## 全工程の所要時間 (手動実作業ベース)

- 事前準備 (MetaMask + アカウント確認): 10-30 分
- 実作業 (区間①-⑤): 20-30 分
- 確認作業 (Arbiscan 等で各区間の tx 検証): 10-15 分
- **合計**: 40-75 分 / 1 回

初回は bitflyer トラベルルール等で 1-2 日遅延する可能性あり (事業者選択 + 書類提出)。

---

## トラブルシュート

### XRP が MEXC に着金しない
1. 国内取引所で tx hash を確認 (完了扱い?)
2. [XRP explorer](https://bithomp.com/explorer/) で tx 成功確認
3. Destination Tag が正しいか再確認 (MEXC の最新 deposit page と照合)
4. 48h 以上経過で MEXC サポートに問い合わせ (tx hash + tag + amount 提供)

### USDC が Arbitrum wallet に着金しない
1. MEXC の withdrawal history で tx hash 確認
2. Arbiscan で tx hash 検索 (`https://arbiscan.io/tx/<hash>`)
3. tx status が `Success` なら MetaMask の USDC トークンを手動追加 (`0xaf88d065e77c8cC2239327C5EDb3A432268e5831` = native USDC on Arbitrum)
4. **ネットワーク誤選択だった場合**: 該当ネットワークの same address で残高確認 (MEXC から間違ったネットワークへ送ってもアドレスは同じため救済可能な場合あり)

### HL に deposit しても balance 反映しない
1. Arbiscan で bridge contract への tx success 確認
2. tx の USDC amount が 5 以上であることを確認
3. HL UI で wallet 接続 address が deposit 送信元と一致しているか確認
4. 5 分以上待っても反映しない場合、[HL Discord](https://discord.gg/hyperliquid) の #support で tx hash 提供

---

## 完了後のアクション

Step 1 完了時点で以下を記録し、Step 2 入金判断の根拠にする:

- [ ] 各区間の実測手数料を記録 → 本ファイルか別 evidence ファイル (`handoff/step1-evidence-2026-05-23/`) に追記
- [ ] 各区間の実測所要時間を記録
- [ ] HL 最終着金額が $6+ であることを確認 (試算 $6.5-8.0)
- [ ] spec v7 の経路試算と実測の差分を分析
- [ ] Step 2 で入金する具体金額を確定 — **spec v7 配分 B baseline = HL $350 + BP $150**、ただし spec v7 finalize (HL 公式第 2 弾アナウンス検出後) で配分判断を最終化
- [ ] mentor へ完了報告 (実測手数料 / 所要時間 / エラー有無)

---

## ★ 2026-05-23 (土) 実行手順 (mentor 3軸役割再定義準拠)

### 事前 (5/23 前夜まで)

1. **ユーザー手動**: 必須準備チェックリスト (本書冒頭) を全項目 ✅ にする (特に v0.2.1 追記の 2 件: トラベルルール事前登録 / MEXC native USDC 確認)
2. **ユーザー手動**: JPY 残高確認 (¥1,800 以上、国内取引所選定)
3. **ユーザー手動**: MetaMask Arbitrum ETH gas 残高 (≈0.001 ETH = $3-4 相当) 確認
4. **ユーザー手動**: HL bridge contract address (`0x2df1c51e09aecf9cacb7bc98cb1742757f163df7`) を Arbiscan で 1 回再確認
5. **ユーザー手動**: MEXC `Withdraw → USDC → Arbitrum One` ページを開いて native USDC 対応 (Token contract = `0xaf88d065e77c8cC2239327C5EDb3A432268e5831`) を 1 回確認

### 5/23 当日

1. **conoha (Claude)**: 本 checklist を再度開き、ユーザーに「実行開始しますか?」と確認 (mentor 役割境界遵守)
2. **ユーザー手動**: 各区間 (①-⑤) をブラウザで実行、conoha は各区間完了時点で次に進む承認を求める
3. **conoha (Claude)**: 各区間で記録すべき値 (tx hash、手数料、所要時間) を都度確認、エラー時はトラブルシュート段で停止
4. **ユーザー手動**: スクリーンショットを `handoff/step1-evidence-2026-05-23/` 配下に保存 (各区間 1-2 枚、後で mentor 報告に使用)
5. **conoha (Claude)**: 全区間完了時点で結果を集計、mentor 用報告書ドラフトを作成

### 5/23 完了後 (~24h 内)

1. **conoha (Claude)**: 実測値を本 checklist の表に追記 (区間別手数料 + 所要時間)
2. **conoha (Claude)**: mentor へ報告書送付 (経路全体所要 / 各区間手数料 / エラー有無 / HL 最終着金額 / Step 2 入金判断材料)
3. **ユーザー判断**: Step 2 入金タイミング判断 (HL 公式第 2 弾アナウンス検出待ち、現状 未公開)

### 中断条件 (5/23 当日に発生した場合)

- 区間①の国内取引所で本人確認未完了 → 中断、別日再開
- 区間②の Destination Tag 入力ミス疑い → MEXC サポートへ問い合わせ後再開
- 区間④の Arbitrum 出金で 30 分超着金しない → 中断、Arbiscan で tx 確認後再開
- 区間⑤の HL bridge deposit 失敗 → 中断、HL Discord #support に tx hash 提供
- **進めない場合の判断**: 中断地点を記録 + 翌週土曜 (5/30) に再実行 or mentor に報告して判断仰ぐ

### evidence 保存場所

- ファイル: `handoff/step1-evidence-2026-05-23/` (実行日に新規ディレクトリ作成)
- 内訳: 各区間スクリーンショット (1-2 枚)、tx hash 一覧 (txt)、実測手数料 + 所要時間表 (md)

---

## 関連

- [spec v7](superpowers/specs/2026-04-20-hl-airdrop-pivot-design.md) — 親 spec (v5→v7 で配分 B baseline / FR コスト明示 / UMA listing +3 BD touch 禁止 / HF cluster watch 追加)
- [docs/hl-airdrop-s1-retro.md](hl-airdrop-s1-retro.md) — 第 1 弾 retro 分析 (v0.4)
- [CLAUDE.md](../CLAUDE.md) — プロジェクト 3軸役割定義 (軸2 HL airdrop 専用 + 軸1 VPS 基盤 + 軸0 廃止)
- `~/Desktop/CCナレッジ/wiki/sources/hyperliquid-hft-bot.md` — API 接続ガイド (rinov)
- `~/Desktop/CCナレッジ/wiki/sources/jeffrey-yan-hyperliquid-profile.md` — ブリッジ経路の 1 次ソース (2026-01 時点情報)
