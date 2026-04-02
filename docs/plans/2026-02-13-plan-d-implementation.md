# Plan D: Minimal Risk, Maximum Impact Implementation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Admin APIデプロイ + 収益直結のRust修正 + Discord通知で、ボットの安全性と収益性を同時に改善する

**Architecture:** 3つの独立したPhaseで構成。各Phaseが完結してデプロイ可能で、途中で止めても価値がある。Phase 1はPython (bot-manager)、Phase 2はRust (gmo-bot)、Phase 3はPython (bot-manager)。

**Tech Stack:** Rust, Python/Flask, Discord Webhook, nssm (Windows Service), GitHub Actions

---

## Phase 1: Admin APIコミット + VPSデプロイ (v0.3.0)

### Task 1: hmac.compare_digest によるタイミングセーフ比較の修正

**Files:**
- Modify: `bot-manager/auth.py:15`
- Modify: `bot-manager/routes/admin.py:49`

**Step 1: auth.py のBasic Auth比較を修正**

`bot-manager/auth.py:15` を以下に変更:

```python
import hmac

# L15:
return hmac.compare_digest(username, expected_user) and hmac.compare_digest(password, expected_pass)
```

**Step 2: admin.py のトークン比較を修正**

`bot-manager/routes/admin.py:49` を以下に変更:

```python
import hmac

# L49:
if not hmac.compare_digest(saved_token, token):
```

**Step 3: テスト実行で既存テストが通ることを確認**

Run: `cd bot-manager && python -m pytest tests/test_admin_routes.py -v`
Expected: 15 tests PASS

**Step 4: コミット**

```bash
git add bot-manager/auth.py bot-manager/routes/admin.py
git commit -m "fix: use hmac.compare_digest for timing-safe comparison"
```

---

### Task 2: Admin API + 関連ファイルをコミット

**Files:**
- Modified: `bot-manager/app.py`
- New: `bot-manager/routes/admin.py`
- New: `bot-manager/services/admin_service.py`
- New: `bot-manager/tests/test_admin_routes.py`
- New: `deploy/conoha-reset-password.py`

**Step 1: 全テスト実行**

Run: `cd bot-manager && python -m pytest tests/ -v`
Expected: All PASS

**Step 2: コミット**

```bash
git add bot-manager/app.py bot-manager/routes/admin.py bot-manager/services/admin_service.py bot-manager/tests/test_admin_routes.py deploy/conoha-reset-password.py
git commit -m "feat: add admin API for remote OS management (reset-password, self-update, deploy)"
```

**Step 3: v0.3.0タグ + push**

```bash
git tag v0.3.0
git push origin main --tags
```

---

### Task 3: VPSでAdmin APIデプロイ

**前提: ConoHaコンソール(VNC)でVPSにアクセスできること**

VPS上で実行:

**Step 1: bot-manager停止 + git pull**

```powershell
nssm stop bot-manager
cd C:\gmo-bot
git pull origin main
```

**Step 2: pip依存更新**

```powershell
C:\gmo-bot\bot-manager\venv\Scripts\pip install -r bot-manager\requirements.txt
```

**Step 3: bot-manager再起動 + 動作確認**

```powershell
nssm start bot-manager
Start-Sleep 5
nssm status bot-manager
```

Expected: `SERVICE_RUNNING`

**Step 4: Admin API動作確認**

ローカルMacから:

```bash
curl -u admin:REDACTED_OLD_CREDENTIAL http://160.251.219.51/api/admin/self-update -X POST -H "Content-Type: application/json" -d '{"restart": false}'
```

Expected: `{"success": true, ...}` or similar JSON response

---

## Phase 2: 収益直結のRust修正 (v0.3.1)

### Task 4: position_penalty を無効化

**Files:**
- Modify: `src/gmo_bot.rs:566`

**Step 1: position_penalty = 0.0 に変更**

`src/gmo_bot.rs:566` を以下に変更:

```rust
// position_penalty direction is inverted (raises buy price when long-heavy),
// contradicting inventory risk management theory. Disabled per analysis.
let position_penalty = 0.0;
```

**Step 2: コミット**

```bash
git add src/gmo_bot.rs
git commit -m "fix: disable position_penalty (inverted direction harms inventory management)"
```

---

### Task 5: INVENTORY_SPREAD_ADJUSTMENT を 0.5 → 0.2 に縮小

**Files:**
- Modify: `src/gmo_bot.rs:361`

**Step 1: 定数を変更**

`src/gmo_bot.rs:361` を以下に変更:

```rust
const INVENTORY_SPREAD_ADJUSTMENT: f64 = 0.2;
```

**Step 2: コミット**

```bash
git add src/gmo_bot.rs
git commit -m "fix: reduce INVENTORY_SPREAD_ADJUSTMENT 0.5->0.2 to preserve fill rate"
```

---

### Task 6: ポジション更新の原子化

**Files:**
- Modify: `src/gmo_bot.rs:747-757`

**Step 1: 2回のwrite()を1回にまとめる**

`src/gmo_bot.rs:747-757` を以下に変更:

```rust
        {
            let mut pos = position.write();
            pos.short_size = if total_position < 0.0 {
                -util::round_size(total_position)
            } else {
                0.0
            };
            pos.long_size = if total_position > 0.0 {
                util::round_size(total_position)
            } else {
                0.0
            };
        }
```

**Step 2: コミット**

```bash
git add src/gmo_bot.rs
git commit -m "fix: atomize position update to prevent read between two writes"
```

---

### Task 7: reqwest::Client にタイムアウト設定追加

**Files:**
- Modify: `src/gmo_bot.rs:927`

**Step 1: Client::new() をビルダーパターンに変更**

`src/gmo_bot.rs:927` を以下に変更:

```rust
    let shared_client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .connect_timeout(std::time::Duration::from_secs(5))
        .build()
        .expect("Failed to create HTTP client");
```

**Step 2: コミット**

```bash
git add src/gmo_bot.rs
git commit -m "fix: add reqwest timeout (10s) and connect_timeout (5s) to prevent hang"
```

---

### Task 8: ビルド確認 + v0.3.1タグ + デプロイ

**Step 1: ローカルビルド確認 (Mac)**

Run: `cargo build --release --bin gmo 2>&1 | tail -5`
Expected: `Finished` (Macでのクロスコンパイルは不要、構文チェック目的)

**Step 2: タグ + push (GitHub Actionsでwindowsビルド)**

```bash
git tag v0.3.1
git push origin main --tags
```

**Step 3: GitHub Actions完了後、VPSでデプロイ**

ローカルMacから (Admin API経由):

```bash
curl -u admin:REDACTED_OLD_CREDENTIAL http://160.251.219.51/api/admin/deploy -X POST -H "Content-Type: application/json"
```

または VPSで直接:

```powershell
cd C:\gmo-bot\deploy
.\download-release.ps1
```

---

## Phase 3: Discord Webhook アラート通知 (v0.3.2)

### Task 9: Discord通知ユーティリティ作成

**Files:**
- Create: `bot-manager/services/discord_notify.py`

**Step 1: 最小実装を作成**

```python
"""Discord Webhook notification service."""
import json
import logging
import urllib.request

logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL = None


def init_discord(webhook_url: str | None) -> None:
    """Initialize Discord webhook URL."""
    global DISCORD_WEBHOOK_URL
    DISCORD_WEBHOOK_URL = webhook_url


def send_alert(title: str, message: str, color: int = 0xFF0000) -> bool:
    """Send an alert to Discord via webhook.

    Args:
        title: Alert title
        message: Alert body
        color: Embed color (default: red)

    Returns:
        True if sent successfully, False otherwise
    """
    if not DISCORD_WEBHOOK_URL:
        logger.debug("Discord webhook URL not configured, skipping alert")
        return False

    payload = {
        "embeds": [{
            "title": title,
            "description": message,
            "color": color,
        }]
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            DISCORD_WEBHOOK_URL,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception as e:
        logger.warning("Discord notification failed: %s", e)
        return False
```

**Step 2: コミット**

```bash
git add bot-manager/services/discord_notify.py
git commit -m "feat: add Discord webhook notification utility"
```

---

### Task 10: bot-managerにDiscord通知を統合

**Files:**
- Modify: `bot-manager/app.py` (init_discord呼び出し追加)
- Modify: `bot-manager/routes/admin.py` (操作完了時に通知)

**Step 1: app.pyでDiscord初期化**

`bot-manager/app.py` の `create_app()` 内に追加:

```python
from services.discord_notify import init_discord
init_discord(os.environ.get("DISCORD_WEBHOOK_URL"))
```

**Step 2: admin.pyの各エンドポイントに通知追加**

各admin操作(reset-password, self-update, deploy)の成功/失敗時に:

```python
from services.discord_notify import send_alert
send_alert("Admin: Self-Update", f"Result: {result.success}", color=0x00FF00 if result.success else 0xFF0000)
```

**Step 3: テスト実行**

Run: `cd bot-manager && python -m pytest tests/ -v`
Expected: All PASS

**Step 4: コミット**

```bash
git add bot-manager/app.py bot-manager/routes/admin.py bot-manager/services/discord_notify.py
git commit -m "feat: integrate Discord webhook alerts for admin operations"
```

---

### Task 11: v0.3.2タグ + VPSデプロイ

**Step 1: タグ + push**

```bash
git tag v0.3.2
git push origin main --tags
```

**Step 2: VPSでbot-manager更新**

Admin API経由:

```bash
curl -u admin:REDACTED_OLD_CREDENTIAL http://160.251.219.51/api/admin/self-update -X POST -H "Content-Type: application/json" -d '{"restart": true}'
```

**Step 3: VPS上でDiscord Webhook URL環境変数を設定**

VPS上で (ConoHaコンソール or RDP):

```powershell
nssm stop bot-manager
$v = (nssm get bot-manager AppEnvironmentExtra)
$v += "DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
nssm set bot-manager AppEnvironmentExtra $v
nssm start bot-manager
```

**Step 4: 動作確認**

Admin APIのself-updateを実行してDiscordに通知が来ることを確認。

---

## リスクと注意事項

| リスク | 対策 |
|--------|------|
| VPSにアクセスできない | ConoHaコンソール(VNC)で接続。Phase 1のTask 3が前提 |
| GitHub Actionsのビルド失敗 | cargo buildをMacでまず確認(Task 8 Step 1) |
| nssm環境変数に不正文字混入 | 1行ずつ慎重に入力。`nssm get bot-manager AppEnvironmentExtra` で確認 |
| position_penalty無効化後の挙動変化 | best_bid/askクランプが安全弁。即座に損失にはならない |
| Discord Webhook URLの秘匿 | 環境変数で管理、コードにハードコードしない |

## 各Phase完了後の状態

| Phase | 完了後にできること |
|-------|-------------------|
| Phase 1 | リモートからAdmin API経由でVPS管理可能 (ロックアウト防止) |
| Phase 2 | 在庫管理が理論通りに動作、APIハング防止、ポジション整合性改善 |
| Phase 3 | admin操作時にDiscord通知。将来的にボット異常検知にも拡張可能 |
