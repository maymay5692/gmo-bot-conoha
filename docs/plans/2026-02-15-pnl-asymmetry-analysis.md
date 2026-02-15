# P&L非対称性の調査分析

## 現象
- 利益: +1円 (多数)
- 損失: -5〜-15円 (散見)
- 利益:損失 = 1:10〜15 の非対称

## P&L計算の確認 (0.001 BTC, BTC≒14.3M JPY)

| スプレッド | Level | 片側スプレッド | 往復利益 | P&L (0.001 BTC) |
|-----------|-------|-------------|---------|-----------------|
| 0.001% | 1 | 143 JPY | 286 JPY | 0.29 JPY |
| 0.005% | 5 | 715 JPY | 1,430 JPY | **1.43 JPY** |
| 0.010% | 10 | 1,430 JPY | 2,860 JPY | 2.86 JPY |
| 0.025% | 25 | 3,575 JPY | 7,150 JPY | 7.15 JPY |

**+1円 ≈ Level 3-5のスプレッド幅**
**-15円 = 市場が15,000 JPY逆行 (約0.1%)**

---

## 原因1: 注文パイプラインのレイテンシ分析

### タイムライン (1サイクル = 10秒)

```
[trade loop]                    [cancel loop]              [get_position]
    |                               |                          |
    |---sleep 10s------------------>|---sleep 0.5s---->        |---sleep 5s-->
    |                               |                          |
t=0  EV計算 + 注文送信(BUY+SELL同時)                           |
    |  └── API POST /v1/order ──────> GMO Server              |
    |       (reqwest timeout: 10s, connect: 5s)                |
    |  └── 応答待ち ~100-500ms ──>   order_id返却              |
    |  └── order_listに追加                                    |
    |                               |                          |
t=0.5                             注文チェック(age < 10s → skip)
t=1                               注文チェック(skip)
...                               ...
t=5                                                          API GET /v1/openPositions
                                                               └── ~100-500ms応答
                                                               └── position更新
t=10 次サイクル開始                 注文チェック(age >= 10s)
    |  └── 新EV計算                  └── cancel API → ERR-5122?
    |  └── 新注文送信                   └── order_list削除
```

### ボトルネック

| 処理 | 所要時間 | 影響 |
|------|---------|------|
| **trade loop間隔** | **10,000ms** | 最大の遅延原因。価格変動に10秒間反応できない |
| API POST (注文送信) | ~100-500ms | VPS(ConoHa東京) → GMO API間。十分高速 |
| API GET (position) | ~100-500ms | 同上 |
| cancel loop間隔 | 500ms | 十分高速 |
| order_cancel_ms | 10,000ms | 注文が10秒間「生きている」= 10秒間キャンセル不可 |
| reqwest timeout | 10,000ms | API応答のデッドライン。通常は問題なし |
| WebSocket遅延 | ~50-200ms | Public WSなので若干遅い。Private WSなら数十ms |

**結論: APIレイテンシ自体は問題ではない (~100-500ms)。問題は10秒固定のtrade loopとorder cancel間隔。**

---

## 原因2: 注文の「10秒拘束」問題

### cancel_child_order のロジック (line 95-154)
```rust
loop {
    sleep(500ms);
    for order in list {
        if now - order.timestamp < order_cancel_ms { continue; }  // ← 10秒未満はスキップ
        cancel_order(order);  // ← 10秒後にキャンセル試行
    }
}
```

**問題**: 注文は送信後 **必ず10秒間** キャンセルされない。
- 新規注文: 10秒間指値が出ている = 意図通り
- **決済注文: 10秒間指値が出ている = 市場が逆行しても価格更新されない**

### シナリオ: 損失が拡大するメカニズム

```
t=0:   pos=long 0.001 (建値14,300,000)
       close SELL at 14,301,000 (spread付き)
       BTC急落開始

t=3:   BTC = 14,290,000 (10,000下落)
       SELL注文は14,301,000のまま → 当然約定しない
       キャンセルできない(age=3s < 10s)

t=10:  BTC = 14,285,000 (15,000下落)
       cancel loop: age=10s → キャンセル試行 → 成功
       trade loop: 新SELL at 14,285,700 (現在のbest_ask付近)

t=10.5: SELL 14,285,700が約定 → 損失 = 14,285,700 - 14,300,000 = -14,300
         0.001 BTC × -14,300 = **-14.3円**

もしt=3でキャンセル→再発注できていれば:
       SELL at 14,290,700 → 損失 = -9,300 → -9.3円 (33%軽減)
```

---

## 原因3: 決済注文の価格設定の問題

### 現在のフロー (line 724-784)
```
1. should_close_long = position.long_size >= min_lot
2. should_buy = should_close_short || can_open_long  → is_close = should_close_short
3. should_sell = should_close_long || can_open_short  → is_close = should_close_long
4. buy/sell_order_price は新規・決済ともに同じ計算式
```

**決済注文の価格 = 新規注文と同一**
- 新規: mid ± spread → スプレッド分の利益を確保するため、midから離す → 正しい
- 決済: mid ± spread → **スプレッドを取ろうとして約定が遅れる** → 損失拡大

### position_penaltyの方向バグ (line 439-440)
```rust
let buy_order_price = bid - penalty * position.long_size / min_lot;
let sell_order_price = ask + penalty * position.short_size / min_lot;
```

| 状態 | 決済方向 | penalty計算 | 結果 |
|------|---------|------------|------|
| long保持, short=0 | SELL決済 | ask + penalty × **0** / 0.001 | **penaltyゼロ!** |
| short保持, long=0 | BUY決済 | bid - penalty × **0** / 0.001 | **penaltyゼロ!** |

**ポジションを片側だけ保持している(最も危険な)場合に、決済を加速する機構が効かない。**

---

## 原因4: 構造的な「逆選択」リスク

### マーケットメイキングの基本的な問題
```
bot: BUY at 14,299,000, SELL at 14,301,000 を指値

ケース A (利益): BTC横ばい → 両方約定 → +2,000 JPY × 0.001 = +2円
ケース B (損失): BTC急落 → BUYだけ約定 → ポジション保持 → 逆行で損失
```

**ケースBが起きやすい理由 (逆選択)**:
- 市場が下落するとき → 売り手が多い → 指値BUYが約定しやすい
- しかしそのBUYは「割高」で買っている（市場はさらに下がるから）
- つまり **約定した注文は、市場の反対側に賭けている** = 平均的に損する側

### 逆選択への対策（未実装）
- **Trade Flow Imbalance (TFI)**: 売買フローの偏りを検出し、逆方向に偏っている時は注文を控える
- **スプレッド拡大**: ボラティリティが高い時はスプレッドを広げる → v0.9.2で一部対応済み

---

## 原因5: 両足同時約定 vs 片足約定の確率

### 現在の動作
- trade loopで **BUYとSELLを同時送信** (tokio::join!)
- 両方LIMIT注文 → 約定は市場次第
- 両方約定: 利益 (スプレッド分)
- 片方のみ: 損失リスク (ポジション保持)

### 約定確率の考察
Level 5 (片側spread = 715 JPY) の場合:
- BTC best_bid/ask spread ≈ 通常 500-2,000 JPY
- bot spread 715 JPY ≈ GMOのbid-askスプレッドと同程度
- **約定しやすいが、片足で捕まるリスクも高い**

---

## まとめ: 根本原因の重要度

| # | 原因 | 影響度 | 修正難度 |
|---|------|--------|---------|
| 1 | **10秒拘束で決済が遅い** | CRITICAL | order_cancel_msを決済だけ短縮 |
| 2 | **決済価格が新規と同じ** | CRITICAL | close用に別価格計算 |
| 3 | **position_penaltyが決済に効かない** | HIGH | penalty計算式の修正 |
| 4 | **逆選択リスク** | HIGH | TFI実装 (中期) |
| 5 | **スプレッドが狭すぎる** | MEDIUM | v0.9.2で一部対応済み |

## 修正プラン

### Phase 1: 決済注文の即時性改善 [最優先]
- 決済注文のキャンセル間隔を3秒に短縮
- 決済注文の価格をmid_price付近に設定（スプレッド50%カット）
- position_penaltyを保持サイドに効かせる

### Phase 2: ストップロス機構 [次点]
- 一定時間（30秒）以上保持したポジションは成行決済
- GMO API: executionType = "MARKET" で close_bulk_order

### Phase 3: 逆選択防御 [中期]
- Trade Flow Imbalance (TFI) の導入
- 売買フローが偏っている時はスプレッド拡大 or 注文控え
