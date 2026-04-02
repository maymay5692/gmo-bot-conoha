# 検証結果と根拠付きアクションプラン (2026-02-18)

前回のリサーチレポートの主張を、公式ドキュメント・ソースコード精読・実データシミュレーション・学術論文で検証した結果。

---

## 1. ファクトチェック結果サマリー

### 公式ドキュメントで確認済み（api-verifier）

| 主張 | 判定 | 根拠 |
|------|------|------|
| レート制限 20req/s | **正しい** | 公式docs: Tier1=20/s, Tier2=30/s。旧6/sは誤り |
| Post-Only注文 | **正しい** | `timeInForce: "SOK"` で指定。BTC_JPYでの動作は要実機確認 |
| Private WS約定通知 | **正しい** | `executionEvents`チャンネル。トークン認証、リアルタイム配信 |
| Maker手数料 -0.01% | **正しい** | 公式手数料ページで確認。往復で+0.02%リベート |

### コード精読で確認済み（code-analyzer）

| 改善案 | 実現可能性 | 重要な発見 |
|--------|-----------|-----------|
| order_interval 1s化 | **条件付き可能** | gmo_bot.rs:593のexecution保持期間がorder_intervalに結合。先に分離が必要 |
| t_optimal_min 500ms化 | **可能** | trade-config.yaml追記のみ。cancelループが500msポーリングなので実効下限 |
| 15秒強制決済 | **条件付き可能** | Position構造体にopened_at追加が必要。5sポーリングで±5秒誤差 |

### シミュレーション実データ（sim-runner）

| 閾値 | Avg P&L | Win率 | Total P&L | N |
|------|---------|-------|-----------|---|
| T+10s | **-1.410** | 30.7% | -2,117 | 1,502 |
| T+15s | -1.533 | 34.4% | -2,247 | 1,466 |
| T+20s | -1.710 | 36.0% | -2,478 | 1,449 |
| T+30s | -1.901 | 35.5% | -2,839 | 1,493 |

**15秒強制決済はNO-GO**: 全閾値でP&Lがマイナス。mid movement -1.9 JPY/tripが支配的。

### 学術的根拠の検証（evidence-checker）

| 主張 | 判定 | 理由 |
|------|------|------|
| Fill Rate 5-15%が典型 | **根拠不十分** | 学術的出典なし。定義の混同（quote execution rate vs order fill rate） |
| 逆選択70.7%は戦略主因 | **根拠不十分** | ランダムウォークでも50%は不利方向。真の超過分は~20.7% |
| 1s化で逆選択1/5に | **誤り** | 学術論文で非線形と実証済み。過大評価 |
| TFIが逆選択防御に有効 | **根拠あり** | VPIN論文(Easley et al.)、OFI予測(arXiv:2408.03594) |
| 15秒保有で赤字→強制決済有効 | **bot特有の問題** | Avellaneda-Stoikovモデルと一致するが、シミュ結果はNO-GO |
| 89ms→42msでarb命中率改善 | **根拠あり、ただしarb** | MM戦略には直接適用不可。MMではquote精度が支配的 |

---

## 2. 検証を踏まえた根本問題の再定義

### 前回の診断（修正前）
> 「5秒サイクルが遅すぎる → 1秒にすれば逆選択が1/5になる」

### 検証後の正確な診断
**約定した瞬間から中値が不利方向に動く（mid movement -1.9 JPY/trip）のが最大の問題。**
これは以下の複合原因：

1. **stale quote問題**: 5秒間板に放置された注文が「狙い撃ち」される
   - 1s化で改善可能だが、効果は1/5ではなく非線形（推定20-40%改善）
2. **informed trader detection不在**: 毒性フロー検出なしで無差別にquote提示
   - TFI/OFIフィルタで改善可能（学術的根拠あり）
3. **ベイズ学習の誤り**: 価格到達率をfill probabilityと誤学習
   - informed traderが動かした価格を「約定しやすい価格」と学習
4. **Makerリベート未活用**: Post-Only未使用。往復+3 JPY/tripのリベートが取れていない可能性

### P&Lの数式
```
P&L/trip = スプレッド捕捉(+2.38) + Makerリベート(+3.0?) - 逆選択コスト(-4.33) - その他
         = 現状: -1.95 JPY/trip (推定)
```

**逆選択コスト(-4.33)を3.0以下に抑えるか、リベート(+3.0)を確実に取ればブレークイーブン到達の可能性がある。**

---

## 3. 根拠付きアクションプラン（優先順位修正版）

### Action 1: execution保持期間の分離（前提条件）
- **根拠**: code-analyzerが発見。gmo_bot.rs:593でexecution retainがorder_intervalに結合
- **変更**: retainの期間を`order_interval_ms`から`5000`固定に分離
- **リスク**: 低。既存動作を変えずにretain期間だけ固定化
- **コスト**: 1行変更

### Action 2: order_interval 5s → 2s（段階的に）
- **根拠**: stale quote問題はサイクル短縮で緩和される（非線形だが改善方向は正しい）
- **1sではなく2sの理由**:
  - APIコール最大4.3回/秒で制限20回/秒の21%。安全圏
  - 段階的に効果測定してから1sへ
  - evidence-checkerの「1/5は過大評価」を考慮し慎重に
- **リスク**: 中。execution保持期間分離が前提

### Action 3: Post-Only注文 (`timeInForce: "SOK"`)
- **根拠**: 公式APIで確認済み。Maker往復リベート+3 JPY/tripは逆選択コスト-4.33の69%を相殺
- **変更**: send_orderのexecutionTypeパラメータにtimeInForce: "SOK"を追加
- **リスク**: fill rateが下がる可能性（Takerとして約定するケースがキャンセルされる）
- **検証方法**: 24h稼働後にfill rateとP&Lを比較

### Action 4: TFI（Trade Flow Imbalance）フィルタ
- **根拠**: Easley et al. VPIN論文、OFI予測論文(arXiv:2408.03594)で有効性実証
- **実装**: 直近N秒のbuy volume / sell volume比率を計算し、3:1以上の不均衡時に該当方向の注文をスキップ
- **計算式**: `TFI = Σ(V_buy) / Σ(V_sell) over last 5s`
- **リスク**: パラメータ調整が必要。ノイズが大きい短期ウィンドウでは偽シグナル多

### Action 5: Private WebSocket導入
- **根拠**: 公式API確認済み。executionEventsで約定リアルタイム検知
- **効果**: get_positionの5sポーリング廃止 → 保有時間管理の精度向上
- **実装コスト**: 中〜高（トークン認証、WS接続管理、既存コードとの統合）
- **依存**: Action 2-4の効果測定後に着手が合理的

### 15秒強制決済: 保留
- **根拠**: シミュレーション結果で全閾値マイナスP&L。NO-GO
- **再評価条件**: Action 2-4実装後にP&Lがプラス転換した場合、「利益確定タイマー」として再検討

---

## 4. 実装順序と期待効果

```
Week 1: Action 1 (retention分離) + Action 2 (2sサイクル) + Action 3 (Post-Only)
        → 24h稼働してデータ収集
        → 期待: 逆選択20-40%削減 + リベート+3 JPY/trip

Week 2: データ分析 → P&Lがプラス方向なら Action 4 (TFI)
        → 48h稼働してデータ収集

Week 3: Action 5 (Private WS) の設計・実装
        → 保有時間管理の精密化
```

---

## 5. 参考文献
- GMO Coin API公式: https://api.coin.z.com/docs/
- The Market Maker's Dilemma (Albers et al., 2024): arXiv:2502.18625
- Flow Toxicity and Liquidity (Easley et al.): VPIN理論
- Forecasting HF Order Flow Imbalance: arXiv:2408.03594
- Limit Order Strategic Placement: arXiv:1610.00261
- High Frequency Market Making: The Role of Speed (ScienceDirect, 2023)
