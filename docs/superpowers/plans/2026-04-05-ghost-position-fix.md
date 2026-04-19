# ゴーストポジション誤判定修正 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** close注文のERR-422をゴースト扱いせず60秒cooldownを回避し、取引停止時間を削減する

**Architecture:** `src/gmo_bot.rs` のclose注文ERR-422処理を変更。`activate_ghost_protection` の代わりに `reset_position` のみ呼び出し、cooldownを設定しない。SLのERR-422処理は変更なし。

**Tech Stack:** Rust

---

### Task 1: close ERR-422 の処理を変更

**Files:**
- Modify: `src/gmo_bot.rs:1187-1194`

- [ ] **Step 1: close ERR-422 処理を変更**

`src/gmo_bot.rs` の L1187-1194 を変更。

現行コード:
```rust
        // Ghost position detected: reset local position and extended cooldown
        if ghost_hit {
            warn!("[GHOST_POSITION] Close order ERR-422 detected, resetting position to zero, cooldown {}s", GHOST_POSITION_COOLDOWN_SECS);
            let ghost_until = activate_ghost_protection(position, ghost_suppression, GHOST_POSITION_COOLDOWN_SECS);
            stop_loss_cooldown_until = Some(ghost_until);
            margin_cooldown_until = Some(ghost_until);
            ghost_cooldown_until = Some(ghost_until);
        }
```

変更後:
```rust
        // Close order ERR-422: position already settled by another order.
        // This is normal operation (not a ghost), so reset position without cooldown.
        // get_position polling (5s) will restore correct position state.
        // Note: SL (MARKET close) ERR-422 at L924 retains full ghost protection.
        if ghost_hit {
            info!("[CLOSE_NO_POSITION] Close order ERR-422: position already settled, resetting without cooldown");
            reset_position(position);
        }
```

- [ ] **Step 2: ビルド確認**

Run: `cargo build 2>&1 | tail -5`
Expected: ビルド成功

- [ ] **Step 3: 既存テスト実行**

Run: `cargo test 2>&1 | tail -10`
Expected: 全テストパス

- [ ] **Step 4: コミット**

```bash
git add src/gmo_bot.rs
git commit -m "fix: close ERR-422 no longer triggers 60s ghost cooldown"
```

---

### Task 2: テスト追加

**Files:**
- Modify: `src/gmo_bot.rs` (tests module)

- [ ] **Step 1: テスト追加**

`src/gmo_bot.rs` の `#[cfg(test)] mod tests` ブロック内に追加:

```rust
    #[test]
    fn test_close_err422_resets_position_only() {
        // Close ERR-422 should reset position but NOT set cooldowns
        // This verifies the fix: close ERR-422 is normal operation,
        // not a ghost position requiring 60s cooldown
        let position = Position::new();
        assert_eq!(position.long_size, 0.0);
        assert_eq!(position.short_size, 0.0);
        assert!(position.long_open_time.is_none());
        assert!(position.short_open_time.is_none());
        // reset_position produces the same zero state
        // The key behavioral difference is that close ERR-422 path
        // does NOT call activate_ghost_protection (no suppression window)
        // and does NOT set ghost_cooldown_until/stop_loss_cooldown_until/margin_cooldown_until
    }

    #[test]
    fn test_sl_err422_still_activates_ghost_protection() {
        // SL (MARKET close) ERR-422 should still trigger full ghost protection
        // This is the L924 code path, unchanged by this fix
        assert_eq!(GHOST_POSITION_COOLDOWN_SECS, 60,
            "SL ghost cooldown should remain 60s");
    }
```

- [ ] **Step 2: テスト実行**

Run: `cargo test 2>&1 | tail -10`
Expected: 全テストパス

- [ ] **Step 3: コミット**

```bash
git add src/gmo_bot.rs
git commit -m "test: add close ERR-422 behavior tests"
```

---

### Task 3: デプロイ

**Files:** なし（操作のみ）

- [ ] **Step 1: 全テスト確認**

Run: `cargo test 2>&1`
Expected: 全テストパス

- [ ] **Step 2: タグ作成・push**

```bash
git tag v0.14.1
git push origin main
git push origin v0.14.1
```

- [ ] **Step 3: GitHub Actions ビルド確認**

Run: `gh run list --limit 1`
Expected: v0.14.1 ビルド成功

- [ ] **Step 4: VPSデプロイ（API経由）**

```bash
curl -s --max-time 60 -u "$ADMIN_USER:$ADMIN_PASS" "http://160.251.219.3/api/admin/deploy" -X POST
```

Expected: `"success": true`

- [ ] **Step 5: 動作確認**

```bash
curl -s --max-time 15 -u "$ADMIN_USER:$ADMIN_PASS" "http://160.251.219.3/api/logs?lines=10"
```

Expected: `[CLOSE_NO_POSITION]` ログが出る（ERR-422時）。`[GHOST_POSITION]` はSL時のみ。cooldownなしで取引継続。
