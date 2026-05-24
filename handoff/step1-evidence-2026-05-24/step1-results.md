---
title: Step 1 経路検証 実測結果 (2026-05-24 実行)
executed: 2026-05-24 14:00-14:43 JST
path: A2 (bitbank → MetaMask Arbitrum ETH → Uniswap USDC swap → HL bridge deposit)
status: 完了
---

# Step 1 経路検証 — 実測結果

## 実行サマリ

- 実行日: **2026-05-24 (土)** (当初予定 5/30 から 6 日前倒し)
- 経路: **Path A2** (bitbank ETH Arbitrum 出金 → MetaMask → Uniswap ETH→USDC → HL bridge)
- HL 最終着金: **18.35 USDC ($18.35)**
- HL wallet: `0xeee8...df03`
- 所要時間: 約 **45 min** (14:00-14:43 JST)

## 区間別実測

| 区間 | 操作 | 結果 |
|---|---|---|
| ① bitbank JPY→ETH | 取引所で ETH 購入 | 完了 |
| ② bitbank→MetaMask | ETH を Arbitrum ネットワークで送付 | 着金確認済 |
| ③ Uniswap ETH→USDC | Arbitrum 上で swap | 18.55 USDC 取得 |
| ④ HL bridge deposit | app.hyperliquid.xyz から deposit | **18.35 USDC 着金** |

## 事前見積もりとの比較

| 項目 | 事前見積もり (checklist v0.3) | 実測 |
|---|---|---|
| 投入額 | $12-15 | ~$20 相当 |
| HL 着金額 | $7-13 (Path A2) | **$18.35** |
| 総手数料 | $0.6-7.1 | ~$2 (推定) |
| 所要時間 | 20-50 min | **45 min** |
| HL 最小預入 5 USDC | クリア必要 | **$18.35 で余裕** |

## Path 確定経緯

- 2026-05-24 14:00 user bitbank スマホアプリで確認:
  - USDC 出金: 非対応 (画面空) → Path A1 不可
  - ETH 出金: **Arbitrum ネットワーク選択肢あり** → Path A2 確定
  - Path A3 (Ethereum mainnet fallback): 不要

## エラー / 問題

- なし。全区間スムーズに完了

## spec v7 への反映事項

- §Step 1 経路試算: 実測で手数料 ~$2、見積もり $1.5-6 の範囲内
- 経路 A (Path A2) は実用的と確認、Step 2 ($350 HL + $150 BP or $500 HL) でも同経路使用可能
- HYPE 価格 $58.84 時点 (配分 A 例外 $60 まで 1.97%)
