# ゴーストポジション誤判定修正 設計

## 概要

close注文のERR-422（ポジション既解消）をゴーストポジション扱いせず、60秒cooldownを回避する。
SLのMARKET closeのERR-422のみ従来通りゴースト扱いを維持。

## 背景と問題

v0.14.0の4/3データ（15.1h）でERR-422が339件発生。分析の結果:

- 339件中338件が「close ORDER_SENT → ERR-422」パターン
- 正常な取引サイクルでポジションが解消された後のclose注文失敗
- これをゴーストと誤判定 → 60秒cooldown → 取引停止
- 84回は両サイド同時ERR-422（BUY/SELL同時close失敗）
- 全時間帯で均等に発生（特定環境の問題ではない）

## 根本原因

botが「ポジションが正常に解消された」ケースと「ゴーストポジション」を区別していない。
close_bulk_order API のERR-422は「決済対象のポジションがない」を意味するが、これは:
1. 別のclose注文やopen注文で既にポジションが解消された（正常）
2. get_positionが古いデータを返してposition情報が実態と乖離している（ゴースト）

のどちらかであり、大多数は1（正常）。

## 変更内容

### `src/gmo_bot.rs`

#### close注文のERR-422処理（L1186-1194付近）

現行:
```rust
if ghost_hit {
    warn!("[GHOST_POSITION] Close order ERR-422 detected, ...");
    let ghost_until = activate_ghost_protection(...);
    stop_loss_cooldown_until = Some(ghost_until);
    margin_cooldown_until = Some(ghost_until);
    ghost_cooldown_until = Some(ghost_until);
}
```

変更後:
```rust
if ghost_hit {
    info!("[CLOSE_NO_POSITION] Close order ERR-422: position already settled");
    reset_position(position);
    // cooldownは入れない — get_positionポーリング(5s)で自動修正
}
```

- `reset_position` でローカルのposition情報をクリア
- `activate_ghost_protection` は呼ばない（ghost_suppressionを設定しない）— get_positionの次のポーリングで正しいpositionが入る
- cooldown（ghost_cooldown_until, stop_loss_cooldown_until, margin_cooldown_until）は設定しない
- ログレベルをwarn→infoに変更（正常動作なので）

#### SLのERR-422処理（L924-929付近）は変更なし

SL（send_market_close）のERR-422は従来通りゴースト扱い（60秒cooldown）。
MARKET closeでERR-422が出るのは真のゴーストポジションの可能性が高い。

### テスト

1. close ERR-422でcooldownが入らないことを確認
2. SL ERR-422では従来通りcooldownが入ることを確認

## 期待効果

- 60秒cooldownの大幅削減（339件/日 → ほぼゼロ）
- 取引可能時間の増加 → trip数増加 → 収益改善
- margin_cooldownの誤設定も解消（ERR-422でmargin不足と誤判定しない）

## スコープ外

- get_positionポーリング間隔の変更（現行5秒で十分）
- ghost_suppression機構の変更（SL用として維持）
- ERR-422カウンターやモニタリング追加
