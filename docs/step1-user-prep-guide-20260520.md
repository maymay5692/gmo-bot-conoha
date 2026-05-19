---
title: HL Step 1 ユーザー側準備 guide (#5/#6/#8 平易手順)
purpose: Step 1 checklist v0.2.2 で未着手のユーザー TODO 3 件 (#5 Arbitrum ETH / #6 HL bridge 照合 / #8 MEXC USDC 実測) を平易な手順で完了させるための事前作業 guide
status: v0.1 (2026-05-20 session 19、ユーザー側「よくわからない」回答を受けて新規作成)
parent: docs/hl-step1-route-checklist.md (v0.2.2)
target_date: 5/20-21 (5/22 中間レビュー前完了、5/30 延期判定の判断材料を mentor に提供)
related: docs/mentor-mid-review-20260522.md section (3)
---

# HL Step 1 ユーザー側準備 guide

このファイルは Step 1 checklist v0.2.2 で確定済の **5/23 前夜タスク** のうち、ユーザーが「よくわからない」と表明した 3 件を、ブラウザ UI 操作レベルで具体化した実作業手順書。

**重要前提**:

- 本 guide の手順を **すべて自力で実施できる** 場合のみ 5/23 実行可。1 件でも詰まったら mentor に報告して 5/30 延期判定
- 各手順は **完全自己責任**。Claude は手順案内のみで、実弾移動 (送金 / 出金 / 購入) はすべてユーザー手動操作
- 不明箇所が出たら **その時点で止めて conoha に報告** — 推測実行は永久損失リスク

---

## #5 — MetaMask Arbitrum 上に ETH 0.001 以上を入手 (gas 用)

### なぜ必要か

5/23 経路の最終区間⑤ で Hyperliquid bridge に USDC を deposit するとき、Arbitrum ネットワーク (Arbitrum One) の **ガス代** として **ETH** が必要。USDC はガス代として使えない。約 0.001 ETH = 約 $3-4 相当 (2026-05 時点) を予め MetaMask の Arbitrum ネットワーク上に置いておく必要がある。

**この $3-4 は Step 1 の $10 投入とは別途必要**。本来 Step 1 の真のコストは $10 + $3-4 + 出金手数料 = 約 $14-15。

### 入手手順 (MEXC 経由が最も確実)

**前提**: MEXC アカウント開設済 + JPY を MEXC に送る経路は別途必要 (Step 1 本作業の区間①-③ と同じパターンで MEXC に着金させる)。

ただし 5/23 までの限られた時間で別経路を立ち上げるのは負荷大。以下から選択:

#### Option A: MEXC で既存資産を使い ETH 購入 → Arbitrum 出金

1. MEXC アカウントに **既に何らかの crypto** (USDT 等) を保有している場合
2. 「Trade」→「Spot」→「ETH/USDT」ペアで ETH を $4-5 相当購入
3. 「Assets」→「Withdraw」→ ETH 選択
4. **ネットワーク選択画面で `Arbitrum One` (ARB) を必ず選択**
5. Withdrawal address に MetaMask の **Arbitrum One ネットワーク** address を入力
6. 金額: 0.001 ETH + 手数料分 (MEXC ETH 出金手数料は時期により $1-2)
7. 2FA + Email 確認

#### Option B: 国内取引所で ETH 購入 → MEXC 経由で Arbitrum 出金 (二度手間)

1. GMO コイン or 他国内取引所で ETH/JPY で $5-6 相当購入
2. ETH を MEXC に送金 (ETH ネットワーク手数料 $5-10 ← 高い)
3. MEXC で受け取り → Arbitrum 出金 (上記 Option A の 3-7 と同じ)

**注意**: Option B は ETH ネットワーク手数料が高く非効率。Option A 推奨。

#### Option C: 友人 / 別 wallet から MetaMask Arbitrum address に送金

- すでに Arbitrum 上に ETH を持つ別 wallet があれば、MetaMask Arbitrum address に直接送る
- ガス代節約のうえ最速

### 完了確認

1. MetaMask 起動 → 右上のネットワーク切替で **Arbitrum One** 選択
2. ETH 残高表示が **0.001 以上** であることを目視
3. (任意) Arbiscan (https://arbiscan.io/address/<your-address>) で残高確認

### 5/22 朝までに完了できない場合

→ mentor 5/22 中間レビューで **5/30 延期** を提案 (本 guide 末尾の section (5) 参照)

---

## #6 — HL bridge contract address Arbiscan 照合

### なぜ必要か

5/23 経路の区間⑤ で USDC を送る先 = HL bridge contract `0x2df1c51e09aecf9cacb7bc98cb1742757f163df7`。**この address に誤りがあると永久損失** (typo 1 文字違いでも資金消失)。Arbiscan という Arbitrum のブロックチェーン explorer で「この address が本物の Hyperliquid bridge であること」を視覚的に確認しておく。

ただし区間⑤ では Hyperliquid 公式 UI (app.hyperliquid.xyz) の「Deposit」ボタンから操作するので、**手入力で address を指定する場面はない**。それでも 1 回照合しておく理由は:

1. 公式 UI が乗っ取られた場合 (極めて稀) の最後の砦
2. address を覚えて 5/23 当日に違和感を察知できる状態にする

### 照合手順 (ブラウザ 1 操作で完了)

1. 以下の URL をブラウザで開く:
   ```
   https://arbiscan.io/address/0x2df1c51e09aecf9cacb7bc98cb1742757f163df7
   ```
2. ページ上部に以下が表示されることを確認:
   - 緑色のチェックマーク (✓) + 「Contract」表示 → contract である証明
   - 「Hyperliquid: Bridge2」または類似の Hyperliquid タグ → 公式 bridge 認識
   - **Verified Contract** マーク → ソースコード公開済 (Hyperliquid 公式が deploy した証明)
3. ページの「Code」タブをクリック → 緑のチェックマーク + ソースコード表示 を確認 (詳細読まなくて OK、表示されることだけ確認)

### 完了確認

- 上記 3 点が表示されれば照合完了
- スクリーンショット 1 枚を `handoff/step1-evidence-2026-05-23/` に保存 (5/23 当日に新規作成、既存ディレクトリなし)

### よくある誤解

- **手順は「URL を開いてページを見るだけ」**、何かを操作 / 送金 / 入力する必要はない
- contract address は固定値で、Hyperliquid 公式が変更しない限り永続有効 (2024 年以降変更なし)
- Arbiscan は無料、アカウント登録も不要

---

## #8 — MEXC native USDC 確認 + Minimum withdrawal 実測

### なぜ必要か

5/23 経路の区間④ で MEXC から Arbitrum 上に USDC を送る際、以下 2 点を満たす必要がある:

- (a) **native USDC** (本物の USDC) であること。MEXC が「bridged USDC.e」という別物を送ると HL bridge で受け取れず、資金消失リスク
- (b) **MEXC の Minimum withdrawal** が $10 投入時の最終手取り $6.5-8.0 を **下回る** こと。例えば MEXC が「最低 $10 から出金可」と設定していたら、$10 投入は区間④で詰む

### 確認手順 (MEXC ログイン後 5 分)

1. MEXC にログイン
2. 右上「Assets」→「Withdraw」をクリック
3. 検索ボックスに `USDC` と入力 → USDC 選択
4. ネットワーク選択画面で `Arbitrum One` (ARB) を選択
5. 以下 2 点を画面から目視取得:

   #### (a) Token contract 照合
   - 画面下部 or USDC の詳細欄に **Token contract address** が表示される
   - **期待値**: `0xaf88d065e77c8cC2239327C5EDb3A432268e5831`
   - これと **完全一致** すれば native USDC (正常)
   - これと **異なる** → bridged USDC.e の可能性、即座に conoha に報告

   #### (b) Minimum withdrawal の数値
   - 画面に「Minimum withdrawal: $X.XX」または「最低出金額」と表示される
   - **数値を実測メモ** ($5、$7、$10 等、時期により変動)
   - **判定**:
     - $7 以下 → 5/23 強行可 ($10 投入で最終手取り $6.5-8.0 内でクリア)
     - $7 超 $10 未満 → 5/23 強行リスクあり、mentor に判断仰ぐ
     - $10 以上 → 5/23 強行 **不可**、5/30 延期 or Step 2 まで MEXC 滞留判断

### 完了確認

- (a) Token contract が `0xaf88d...e5831` と一致
- (b) Minimum withdrawal の数値メモ (Claude に報告)

### よくある誤解

- **画面から数値を読み取るだけ**、実際の出金 (Withdraw) ボタンは押さない
- ネットワーク選択 (Arbitrum One) を間違えると別チェーンの USDC 情報が出る、必ず Arbitrum One

---

## 5/22 朝までの完了スケジュール (推奨)

### 5/20 (火) 中
- **#6** HL bridge contract Arbiscan 照合 (5 分): 即実施可、最も軽い
- **#8** MEXC USDC 確認 + Min withdrawal 実測 (5-10 分): MEXC ログインのみで完結

### 5/20-21 (火-水)
- **#5** Arbitrum ETH 入手: MEXC で ETH 購入 + Arbitrum 出金 (時間: 入金待ち含めて 30 分 - 数時間、ネットワーク混雑次第)
  - MEXC に既に USDT 等あれば 30 分で完了
  - JPY → MEXC 入金からだと 1-2 日かかる場合あり

### 5/22 (木) 朝までに完了確認

- 3 件すべて完了 → 5/23 強行確定、GMO トラベルルール審査結果待ち
- 1 件でも未完了 → mentor 中間レビューで **5/30 延期** を提案

---

## 5/30 延期判定の根拠 (mentor 報告書 section (3) に反映)

以下の場合は 5/23 強行ではなく 5/30 (土) 延期を推奨:

- ユーザー TODO #5/#6/#8 のいずれか 1 件でも 5/22 朝までに完了できない
- GMO トラベルルール審査が 5/22 PM までに承認されない
- MEXC USDC Minimum withdrawal が $7 を超え、$10 投入の経路検証で詰むリスクが顕在化
- ユーザーの 5/23 体調 / 時間確保が困難

5/30 延期で得られる時間:

- 5/24 (日)-5/29 (金) の 6 日間で TODO 解説の再確認 + 実施
- 5/29 (金) 夜に最終チェック → 5/30 (土) 朝実行
- リスク低減: 手順理解 + リードタイム確保 + 5/22 中間レビュー結果反映時間

---

## 関連

- 親 checklist: [docs/hl-step1-route-checklist.md](hl-step1-route-checklist.md) v0.2.2
- mentor 報告書: [docs/mentor-mid-review-20260522.md](mentor-mid-review-20260522.md) section (3)
- evidence 保存先 (5/23 or 5/30 当日に新規作成): `handoff/step1-evidence-2026-05-XX/`
