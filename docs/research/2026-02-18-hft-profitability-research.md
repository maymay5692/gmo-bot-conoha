# HFT Bot 収益性調査レポート (2026-02-18)

4つのエージェントによる並列リサーチの統合結果。
現在のgmo-bot-conohaと収益プレイヤーの差分分析。

---

## 1. 核心的な結論

### 収益プレイヤーとの最大の差分は「速度」と「逆選択防御」

| 要素 | 収益プレイヤー | 現在のbot (v0.9.5) | 差分 |
|------|-------------|----------|------|
| 注文サイクル | 100〜500ms | 5,000ms | 10〜50倍遅い |
| キャンセル速度 | 100〜500ms | 2,000〜10,000ms | 4〜100倍遅い |
| 約定認識 | Private WS（即時） | REST 5秒ポーリング | 最大5秒遅れ |
| 逆選択対策 | TFI/OFI/VPIN | なし | 完全無防備 |
| 保有時間制御 | 数秒〜数十秒で強制決済 | 制限なし | 赤字ポジション放置 |
| Circuit breaker | 高ボラ時に注文停止 | なし | ワースト20%で全損失108% |

### 「ロスなく注文が通る環境」は作れるか？

**環境だけでは解決しない。ただし改善の余地はある。**
- GMO Coinはコロケーション不可、FIX API不可。全参加者が同条件
- ConoHaはGMOグループ傘下 → GMO Coinとのネットワーク距離は既に最短クラスの可能性
- レイテンシの真のボトルネックは物理距離(5ms)ではなく **5秒サイクルの設計遅延(5,000ms)**

---

## 2. GMO Coin HFT環境の実態

### API / WebSocket
- REST API / WSのレイテンシ: 公式SLAなし。東京VPSからは推定5〜30ms
- Public WS: ticker/orderbooks/trades。配信頻度非公開
- Private WS: executionEvents/orderEvents/positionEvents（リアルタイム約定通知）
- **現在のbotはPublic WSのみ → Private WSを使えば約定検知を大幅高速化**

### レート制限（重要な更新）
- **旧情報: 6回/秒 → 最新: Tier 1で20回/秒、Tier 2で30回/秒**
- 現在の消費: 0.8回/秒（Tier 1の4%）
- order_interval 1秒にしても余裕あり

### 手数料
| 種別 | 現物 | レバレッジ |
|------|------|-----------|
| Maker | **-0.01%（リベート）** | 無料 |
| Taker | 0.05% | 無料 |
| 建玉保有 | - | 0.04%/日 |

### 注文タイプ
- **Post-Only**: 対応あり（国内初導入）。強制Maker化でリベート確保可能
- **FOK**: 対応あり
- IOC: 確認中

### コロケーション / FIX API
- **どちらも不提供**。REST + WebSocketが唯一のアクセス手段
- GMOグループのDCは東京・品川区

---

## 3. 日本の暗号資産HFT収益プレイヤーの実態

### 収益ランク
| ランク | 月次収益 | 代表例 |
|--------|---------|--------|
| SS級 | 1,000万円以上 | richmanbtc（月次一時1億円超） |
| A級 | 100万円以上 | 機械学習botで到達 |
| B級 | 10万円以上 | 元手5万円から半年で達成例あり |
| C級以下 | 赤字〜数万円 | 大多数 |

### 使用取引所の傾向
- **GMO Coin**: Maker rebate -0.01%、API安定。ただし板中央1円差に注文密集で過当競争
- **bitFlyer**: 取引量No.1、流動性最高。FIX API提供あり（Axon Trade）
- **bitbank**: Maker rebate -0.02%（最大）
- **中規模海外取引所**: Gate.io, KuCoin等でリベート3.5〜5.5bps、個人に余地あり

### 現在の主流戦略（2024-2025年）
1. **DEXアービトラージ/MEV（Onchain）**: 主戦場が移行中
2. **中規模取引所でのMM**: Gate.io等で個人に参入余地
3. **機械学習方向性予測Bot**: richmanbtcモデル。ただし2023年以降に劣化傾向
4. **CEX Pure MM**: 大手取引所では機関と競合し個人には厳しい

### 成功プレイヤーの逆選択対策
- **TFI / OFI（Trade/Order Flow Imbalance）**: 毒性フロー検出
- **VPIN（Volume Synchronized Probability of Informed Trading）**: インフォームド取引確率
- **動的スプレッド**: 市場方向性に応じてスプレッドを広げる/狭める
- **保有時間上限**: 全員が数秒〜数十秒以内の強制決済を設定
- **Circuit breaker**: ボラ急騰時にクオートを引く

### 成功 vs 失敗の差分要因
**成功**: 予測+執行の両方を最適化、逆選択を定量計測、エッジの賞味期限把握
**失敗**: バックテスト頼み（摩擦コスト未考慮）、逆選択無視のPure MM継続、固定スプレッド

---

## 4. インフラ / 低レイテンシ環境

### コロケーション提供取引所
| 取引所 | コロケーション | FIX API |
|--------|--------------|---------|
| Kraken | あり（Beeks Exchange Cloud, ロンドン, 2025年〜） | あり |
| Binance | なし（AWSの東京リージョンにマッチングエンジン） | なし |
| bitFlyer | なし | あり（Axon Trade FIX 4.4） |
| GMO Coin | なし | なし |
| Bybit | なし（2026年1月に日本サービス終了） | - |

### VPS比較（暗号資産bot観点）
| プロバイダ | 評価 | 備考 |
|-----------|------|------|
| AWS Tokyo (ap-northeast-1) | ★★★★★ | Binance/GMO向けベスト |
| EDIS Global (Equinix TY2) | ★★★★★ | プレミアム、Equinix直結 |
| さくら Tokyo | ★★★★ | 石狩より東京の方が低レイテンシ |
| **ConoHa (GMO傘下)** | ★★★★ | **GMO Coinと同一グループ。ネットワーク距離で有利の可能性** |

### レイテンシ実測値
| 接続形態 | RTT (往復) |
|---------|-----------|
| 自宅PC → 取引所 REST | 20〜200ms |
| 東京VPS → 東京取引所 REST | 5〜30ms |
| 同一DC コロケーション | 1〜5ms |
| Equinix クロスコネクト | 0.3ms〜 |

### 実証データ
- **レイテンシ89ms → 42ms改善でarb命中率 23% → 61%**（取引会社実例）
- Sub-50ms: 勝率80%以上 / 150ms超: 勝率30%以下
- 47ms遅延 = 年間$180,000相当の逆選択コスト

### ネットワーク最適化（無料で即実装可能）
- `TCP_NODELAY`: Nagleアルゴリズム無効化（数ms削減）
- `TCP_QUICKACK`: ACK遅延無効化
- `SO_BUSY_POLL`: ポーリングモードで割り込み待ち削除

---

## 5. 現在のbotの詳細分析

### 逆選択70.7%の原因分解
1. **戦略設計が主因**: 5秒サイクルで古い価格の注文が板に残り、informed traderに食われる
2. **ベイズ確率の学習対象**: fill probabilityではなく「価格到達率」を学習 → informed traderの動きを「fill確率が高い」と誤学習
3. **レイテンシ**: ConoHa→GMO Coinは5〜30ms程度で、これ自体は問題ではない

### Fill Rate 28.4%の評価
- **高すぎる**。収益MMerは5〜15%が典型
- 高fill率 = 逆選択されやすい水準
- 5秒ごとに機械的に発注し、高ボラ時にも板に残り続けるため

### 5秒サイクルの評価
- HFTではなく「低頻度ロボットトレード」レベル
- BTC/JPY 現物HFT: 10ms〜100ms
- GMO APIレート制限20回/秒に対して0.8回/秒しか使っていない

### Private WS未使用の影響
- 約定検知が最大5秒遅れ（REST polling）
- ERR-5122で約定を事後検知する設計
- クローズ注文が最大10秒遅れる

---

## 6. 優先順位付きアクションプラン

### P0: 即効性が高い（数日で実装可能）
| # | 改善 | 期待効果 |
|---|------|---------|
| 1 | **order_interval 5s → 1s** | 逆選択にさらされる時間を1/5に |
| 2 | **t_optimal_min 2s → 500ms** | 不利注文の早期キャンセル |
| 3 | **15秒強制決済** | v0.9.5データで検証後、即実装 |

### P1: 中期（1〜2週間）
| # | 改善 | 期待効果 |
|---|------|---------|
| 4 | **Private WebSocket導入** | 約定検知を5秒→数百msに |
| 5 | **TFI（Trade Flow Imbalance）** | 逆選択の事前防御 |
| 6 | **Circuit breaker** | 高ボラ時の損失カット |

### P2: 長期（戦略転換の検討）
| # | 改善 | 期待効果 |
|---|------|---------|
| 7 | **Post-Only注文** | 確実にMaker rebateを取る |
| 8 | **機械学習方向性予測** | 逆選択の根本対策（richmanbtcモデル） |
| 9 | **取引所変更検討** | bitbank(-0.02%リベート)、中規模海外取引所 |

---

## 7. 参考ソース
- [GMO Coin APIドキュメント](https://api.coin.z.com/docs/)
- [GMO Coin 手数料ページ](https://coin.z.com/jp/corp/guide/fees/)
- [ビットコインbotterにとっての各マーケットの特徴(2024年12月)](https://gitan.dev/?p=365)
- [仮想通貨高頻度取引ロジックが勝てない理由](https://kabukimining.hateblo.jp/entry/why_icant_win_htf)
- [Empirical Notes #3: Market Making in Smaller Crypto Exchanges](https://mlquants.substack.com/p/empirical-notes-3-market-making-in)
- [richmanbtc mlbot_tutorial](https://github.com/richmanbtc/mlbot_tutorial)
- [Kraken Colocation Service (2025)](https://blog.kraken.com/news/colocation)
- [AWS Crypto Market-Making Latency](https://aws.amazon.com/blogs/industries/crypto-market-making-latency-and-amazon-ec2-shared-placement-groups/)
- [Crypto HFT Optimization Guide (HangukQuant)](https://www.research.hangukquant.com/p/crypto-hft-in-depth-guide-to-optimization)
- [BitFlyer FIX API - Axon Trade](https://axon.trade/bitflyer-fix-api)
- [High-Frequency Trading in Crypto: Latency, Infrastructure, and Reality](https://medium.com/@laostjen/high-frequency-trading-in-crypto-latency-infrastructure-and-reality-594e994132fd)
