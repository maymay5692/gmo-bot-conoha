# min_hold_ms Rust実装 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** bot本体（Rust）にmin_hold_ms（最低保持時間）を追加し、open後一定時間closeを抑制してmean reversionを活用する

**Architecture:** `Position` structに `long_open_time` / `short_open_time` を追加。get_position APIポーリングでposition sizeが0→非0に遷移したときに `Instant::now()` をセット。メインループのclose判定で経過時間をチェック。`BotConfig` に `min_hold_ms` を追加し `trade-config.yaml` で設定。SLはmin_holdの制約を受けない。

**Tech Stack:** Rust, tokio, serde_yaml

---

### Task 1: Position struct に open_time を追加

**Files:**
- Modify: `src/model.rs:5-17`

- [ ] **Step 1: Position struct を変更**

`src/model.rs` の `Position` struct を変更:

```rust
use std::time::Instant;

#[derive(Debug, Clone, Copy)]
pub struct Position {
    pub long_size: f64,
    pub short_size: f64,
    pub long_open_price: f64,
    pub short_open_price: f64,
    pub long_open_time: Option<Instant>,
    pub short_open_time: Option<Instant>,
}

impl Default for Position {
    fn default() -> Self {
        Self {
            long_size: 0.0,
            short_size: 0.0,
            long_open_price: 0.0,
            short_open_price: 0.0,
            long_open_time: None,
            short_open_time: None,
        }
    }
}

impl Position {
    pub fn new() -> Self {
        Self::default()
    }
}
```

注意: `Instant` は `Copy` を実装しているので `#[derive(Clone, Copy)]` は維持可能。ただし `Default` derive は `Option<Instant>` の `Default` が `None` を返すので `#[derive(Default)]` でも動作するが、明示的にimplする方が安全。

- [ ] **Step 2: ビルド確認**

Run: `cargo build 2>&1 | head -30`
Expected: ビルド成功（他の箇所でPosition初期化方法に影響がなければ）。`Default` derive を外したことでエラーが出る可能性があるが、明示的impl Defaultで代替。

- [ ] **Step 3: コミット**

```bash
git add src/model.rs
git commit -m "feat: add open_time fields to Position struct"
```

---

### Task 2: BotConfig に min_hold_ms を追加

**Files:**
- Modify: `src/model.rs:149-174`
- Modify: `src/trade-config.yaml`

- [ ] **Step 1: BotConfig にフィールド追加**

`src/model.rs` の `BotConfig` struct に追加（`stop_loss_jpy` の後）:

```rust
    #[serde(default = "default_min_hold_ms")]
    pub min_hold_ms: u64,
```

デフォルト関数を追加（他のdefault関数の近くに）:

```rust
fn default_min_hold_ms() -> u64 { 180000 }
```

- [ ] **Step 2: trade-config.yaml に設定追加**

`src/trade-config.yaml` の末尾に追加:

```yaml
min_hold_ms: 180000
```

- [ ] **Step 3: ビルド確認**

Run: `cargo build 2>&1 | head -20`
Expected: ビルド成功

- [ ] **Step 4: コミット**

```bash
git add src/model.rs src/trade-config.yaml
git commit -m "feat: add min_hold_ms config parameter (default 180s)"
```

---

### Task 3: get_position ポーリングで open_time をセット

**Files:**
- Modify: `src/gmo_bot.rs:1226-1232`

- [ ] **Step 1: get_position 更新箇所を変更**

`src/gmo_bot.rs` の get_position APIレスポンス処理部分（L1226-1232付近）を変更:

```rust
        {
            let mut pos = position.write();
            let prev_long = pos.long_size;
            let prev_short = pos.short_size;

            pos.long_size = util::round_size(long_total);
            pos.short_size = util::round_size(short_total);
            pos.long_open_price = if long_total > 0.0 { long_price_sum / long_total } else { 0.0 };
            pos.short_open_price = if short_total > 0.0 { short_price_sum / short_total } else { 0.0 };

            // Track open time: set when position transitions from 0 to non-zero
            if prev_long < min_lot && pos.long_size >= min_lot && pos.long_open_time.is_none() {
                pos.long_open_time = Some(Instant::now());
            }
            if pos.long_size < min_lot {
                pos.long_open_time = None;
            }
            if prev_short < min_lot && pos.short_size >= min_lot && pos.short_open_time.is_none() {
                pos.short_open_time = Some(Instant::now());
            }
            if pos.short_size < min_lot {
                pos.short_open_time = None;
            }
        }
```

注意: この関数はasyncタスク内で実行される。`min_lot` は引数として渡す必要がある。現在の `handle_position_data` の引数を確認し、`min_lot` を追加するか、`0.001` をハードコードする（BotConfigからmin_lotを取得する方法を確認すること）。

実際のhandle_position_data関数シグネチャを読んで、min_lot の渡し方を決定すること。ハードコード `0.001` が最もシンプルだが、`config` のmin_lotと乖離するリスクがある。config をArc等で共有しているなら参照を追加。

最もシンプルな方法: `pos.long_size > 0.0` で判定（min_lot判定は不要、sizeが正の値ならポジションあり）:

```rust
            // Track open time: set when position transitions from 0 to non-zero
            if prev_long <= 0.0 && pos.long_size > 0.0 && pos.long_open_time.is_none() {
                pos.long_open_time = Some(Instant::now());
            }
            if pos.long_size <= 0.0 {
                pos.long_open_time = None;
            }
            if prev_short <= 0.0 && pos.short_size > 0.0 && pos.short_open_time.is_none() {
                pos.short_open_time = Some(Instant::now());
            }
            if pos.short_size <= 0.0 {
                pos.short_open_time = None;
            }
```

- [ ] **Step 2: reset_position で open_time もリセット**

`src/gmo_bot.rs` の `reset_position` 関数（L238-244付近）を変更:

```rust
fn reset_position(position: &Positions) {
    let mut pos = position.write();
    pos.long_size = 0.0;
    pos.short_size = 0.0;
    pos.long_open_price = 0.0;
    pos.short_open_price = 0.0;
    pos.long_open_time = None;
    pos.short_open_time = None;
}
```

- [ ] **Step 3: ビルド確認**

Run: `cargo build 2>&1 | head -30`
Expected: ビルド成功

- [ ] **Step 4: コミット**

```bash
git add src/gmo_bot.rs
git commit -m "feat: track position open time in get_position polling"
```

---

### Task 4: close判定に min_hold チェックを追加

**Files:**
- Modify: `src/gmo_bot.rs:1042-1043`

- [ ] **Step 1: close判定を変更**

`src/gmo_bot.rs` の close判定（L1042-1043付近）を変更:

```rust
        // Min hold: suppress close until min_hold_ms has elapsed since position open
        let min_hold = std::time::Duration::from_millis(config.min_hold_ms);
        let min_hold_elapsed_long = current_position.long_open_time
            .map_or(true, |t| t.elapsed() >= min_hold);
        let min_hold_elapsed_short = current_position.short_open_time
            .map_or(true, |t| t.elapsed() >= min_hold);

        let should_close_short = current_position.short_size >= min_lot && min_hold_elapsed_short;
        let should_close_long = current_position.long_size >= min_lot && min_hold_elapsed_long;

        // Log min_hold suppression
        if current_position.long_size >= min_lot && !min_hold_elapsed_long {
            debug!(
                "[MIN_HOLD] Close long suppressed: {}ms / {}ms",
                current_position.long_open_time.unwrap().elapsed().as_millis(),
                config.min_hold_ms
            );
        }
        if current_position.short_size >= min_lot && !min_hold_elapsed_short {
            debug!(
                "[MIN_HOLD] Close short suppressed: {}ms / {}ms",
                current_position.short_open_time.unwrap().elapsed().as_millis(),
                config.min_hold_ms
            );
        }
```

注意: SL判定（L874-920付近）はこの箇所より前にあり、`send_market_close` を直接呼ぶため min_hold の影響を受けない。変更不要。

- [ ] **Step 2: ORDERログにmin_hold情報を追加**

L1085-1094付近のORDERログに min_hold 状態を追加:

```rust
        info!(
            "[ORDER] buy={} (close_short={}, open_long={}), sell={} (close_long={}, open_short={}), pos=({}/{}), min_hold_ok=({}/{})",
            should_buy, should_close_short, can_open_long,
            should_sell, should_close_long, can_open_short,
            current_position.long_size, current_position.short_size,
            min_hold_elapsed_long, min_hold_elapsed_short,
        );
```

注意: 既存のログフォーマットが長い場合は、min_hold部分だけ追加する形で。既存のログ行を読んで適切にマージすること。

- [ ] **Step 3: ビルド確認**

Run: `cargo build 2>&1 | head -30`
Expected: ビルド成功

- [ ] **Step 4: テスト実行**

Run: `cargo test 2>&1 | tail -20`
Expected: 既存テスト全パス

- [ ] **Step 5: コミット**

```bash
git add src/gmo_bot.rs
git commit -m "feat: add min_hold check to close order decision"
```

---

### Task 5: 単体テスト追加

**Files:**
- Modify: `src/gmo_bot.rs` (tests module)

- [ ] **Step 1: min_hold テストを追加**

`src/gmo_bot.rs` の `#[cfg(test)] mod tests` ブロック内に追加:

```rust
    #[test]
    fn test_min_hold_suppresses_close() {
        // Position opened just now → min_hold not elapsed
        let mut pos = Position::new();
        pos.long_size = 0.001;
        pos.long_open_time = Some(Instant::now());

        let min_hold = Duration::from_millis(180000);
        let elapsed = pos.long_open_time
            .map_or(true, |t| t.elapsed() >= min_hold);

        assert!(!elapsed, "min_hold should suppress close immediately after open");
    }

    #[test]
    fn test_min_hold_allows_close_when_none() {
        // open_time is None → should allow close (safe default)
        let mut pos = Position::new();
        pos.long_size = 0.001;
        // long_open_time is None (default)

        let min_hold = Duration::from_millis(180000);
        let elapsed = pos.long_open_time
            .map_or(true, |t| t.elapsed() >= min_hold);

        assert!(elapsed, "min_hold should allow close when open_time is unknown");
    }

    #[test]
    fn test_min_hold_zero_disables() {
        // min_hold_ms = 0 → always allow close
        let mut pos = Position::new();
        pos.long_size = 0.001;
        pos.long_open_time = Some(Instant::now());

        let min_hold = Duration::from_millis(0);
        let elapsed = pos.long_open_time
            .map_or(true, |t| t.elapsed() >= min_hold);

        assert!(elapsed, "min_hold=0 should always allow close");
    }
```

注意: `use std::time::{Duration, Instant};` がテストモジュール内にない場合は追加。

- [ ] **Step 2: テスト実行**

Run: `cargo test 2>&1 | tail -20`
Expected: 全テストパス（新規3テスト含む）

- [ ] **Step 3: コミット**

```bash
git add src/gmo_bot.rs
git commit -m "test: add min_hold unit tests"
```

---

### Task 6: バージョンタグ準備

**Files:**
- No file changes

- [ ] **Step 1: 全テスト実行**

Run: `cargo test 2>&1`
Expected: 全テストパス

- [ ] **Step 2: cargo build --release 確認**

Run: `cargo build --release 2>&1 | tail -5`

注意: VPSはWindows Server、ローカルはmacOS。ローカルでのrelease buildは動作確認用（クロスコンパイルではない）。実際のWindows binaryはGitHub Actionsで生成される。

- [ ] **Step 3: コミットログ確認**

Run: `git log --oneline -10`

全変更が意図通りか確認。

- [ ] **Step 4: 注意事項**

デプロイは以下の手順で実施（この計画のスコープ外）:
1. `git tag v0.14.0 && git push origin v0.14.0`
2. GitHub Actions がWindows binary を build → Release作成
3. VPS で `.\deploy\download-release.ps1`
4. `verify_version.py` でログ確認

min_hold_ms=180000 がデフォルト。従来動作に戻すには `min_hold_ms: 0` に変更。
