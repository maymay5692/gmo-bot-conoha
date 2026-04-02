# min_hold_ms — bot本体（Rust）への最低保持時間制約 設計

## 概要

bot本体（Rust）にmin_hold_ms（最低保持時間）パラメータを追加する。
open fill後、min_hold_ms経過するまでclose注文を抑制し、mean reversionを待つ。

## 背景と目的

- バックテスト分析で、min_hold=180sでP&L/tripが-1.69→+0.31に黒字転換
- 現行botはclose注文のcancel/再送信を繰り返し、逆行中に追いかけて不利なタイミングで決済
- 300s+保持のtripはmean reversionにより平均P&L/trip=+9.15
- min_holdにより「急いでcloseしない」制約を入れ、mean reversionを活用する

## 変更ファイルと内容

### 1. `src/model.rs`

#### Position struct に open_time を追加

```rust
pub struct Position {
    pub long_size: f64,
    pub short_size: f64,
    pub long_open_price: f64,
    pub short_open_price: f64,
    pub long_open_time: Option<std::time::Instant>,   // 追加
    pub short_open_time: Option<std::time::Instant>,  // 追加
}
```

Default実装で `None` に初期化。

#### BotConfig に min_hold_ms を追加

```rust
#[serde(default = "default_min_hold_ms")]
pub min_hold_ms: u64,
```

デフォルト値: 180000（180秒）。
0でmin_hold無効（従来動作と同じ）。

### 2. `src/gmo_bot.rs`

#### open fill受信時にopen_timeをセット

open注文がfillされたとき（`is_close == false` のORDER_FILLEDイベント）、
対応するsideのopen_timeを `Some(Instant::now())` にセット。

#### close判定にmin_hold経過チェックを追加

```rust
let min_hold = Duration::from_millis(config.min_hold_ms);

let min_hold_elapsed_long = current_position.long_open_time
    .map_or(true, |t| t.elapsed() >= min_hold);
let min_hold_elapsed_short = current_position.short_open_time
    .map_or(true, |t| t.elapsed() >= min_hold);

let should_close_short = current_position.short_size >= min_lot && min_hold_elapsed_short;
let should_close_long = current_position.long_size >= min_lot && min_hold_elapsed_long;
```

`map_or(true, ...)` — open_timeがNone（時刻不明）の場合はclose許可（安全側）。

#### min_holdによるclose抑制ログ

min_holdが有効でclose抑制された場合にログを出力:

```rust
if current_position.long_size >= min_lot && !min_hold_elapsed_long {
    debug!("[MIN_HOLD] Close long suppressed: {:.0}ms / {}ms elapsed",
        current_position.long_open_time.unwrap().elapsed().as_millis(),
        config.min_hold_ms);
}
```

#### reset_position でopen_timeもリセット

ghost検出やSL後のposition resetでopen_timeも `None` にクリア。

#### SLはmin_holdの影響を受けない

SL判定ブロック（`stop_loss_jpy > 0.0`の箇所）はmin_holdチェックより前にあり、
SLは直接 `send_market_close` を呼ぶためmin_holdの制約を受けない。
変更不要。

### 3. `src/trade-config.yaml`

```yaml
min_hold_ms: 180000
```

### 4. ログ出力（trade_logger）

open fill時にmin_hold情報をログに記録。
close抑制時にdebugログを出力。

## テスト

### 単体テスト（`src/gmo_bot.rs` の `#[cfg(test)]`）

1. `test_min_hold_suppresses_close` — min_hold未経過でshould_closeがfalseになる
2. `test_min_hold_allows_close_after_elapsed` — min_hold経過後にshould_closeがtrue
3. `test_min_hold_zero_disables` — min_hold_ms=0で従来動作
4. `test_sl_ignores_min_hold` — SLはmin_hold中でも発動

### 統合テスト

VPSデプロイ後に verify_version.py で検証。

## デプロイ

1. `git tag vX.Y.Z && git push origin vX.Y.Z`
2. GitHub Actions でWindows binary build
3. VPS で `.\deploy\download-release.ps1`
4. verify_version.py でログ確認

## スコープ外

- min_hold値の自動最適化（固定値180000msで開始）
- close_spread_factorの動的変更
- t_optimalとmin_holdの連動
- min_hold中のEV再計算
