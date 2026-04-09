"""Admin service for OS-level management operations."""
import os
import platform
import subprocess
from dataclasses import dataclass
from typing import Optional

IS_WINDOWS = platform.system() == "Windows"
BOT_DIR = r"C:\gmo-bot" if IS_WINDOWS else "/home/ubuntu/gmo-bot"
BOT_MANAGER_SERVICE = "bot-manager"
BOT_SERVICE = "gmo-bot"
GMO_CRED_KEYS = ("GMO_API_KEY", "GMO_API_SECRET")
# Persistent env file loaded at bot-manager startup. Replaces nssm
# AppEnvironmentExtra persistence which was unreliable in practice.
ENV_FILE_PATH = os.path.join(BOT_DIR, "bot-manager", ".env.local")


@dataclass(frozen=True)
class CommandResult:
    """Immutable result of a command execution."""

    success: bool
    output: str
    error: Optional[str] = None


def reset_os_password(new_password: str) -> CommandResult:
    """Reset the OS Administrator/root password.

    Windows: net user Administrator <password>
    Linux: chpasswd
    """
    if not new_password or len(new_password) < 8:
        return CommandResult(
            success=False,
            output="",
            error="Password must be at least 8 characters",
        )

    if IS_WINDOWS:
        cmd = ["net", "user", "Administrator", new_password]
    else:
        cmd = ["sudo", "chpasswd"]

    try:
        if IS_WINDOWS:
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=False, timeout=30
            )
        else:
            result = subprocess.run(
                cmd,
                input=f"root:{new_password}\n",
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        return CommandResult(
            success=result.returncode == 0,
            output=result.stdout.strip() if result.stdout else "",
            error=result.stderr.strip() if result.stderr else "" if result.returncode != 0 else None,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(success=False, output="", error="Command timed out")
    except OSError as e:
        return CommandResult(success=False, output="", error=str(e))


def self_update() -> CommandResult:
    """Pull latest code and install dependencies.

    Returns the git pull result. The caller is responsible for
    triggering a service restart after confirming the result.
    """
    try:
        git_result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=BOT_DIR,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if git_result.returncode != 0:
            return CommandResult(
                success=False,
                output=git_result.stdout.strip() if git_result.stdout else "",
                error=git_result.stderr.strip() if git_result.stderr else "",
            )

        pip_cmd = (
            ["pip", "install", "-r", "bot-manager/requirements.txt"]
            if IS_WINDOWS
            else ["pip3", "install", "-r", "bot-manager/requirements.txt"]
        )
        pip_result = subprocess.run(
            pip_cmd,
            cwd=BOT_DIR,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

        git_output = git_result.stdout.strip() if git_result.stdout else ""
        if pip_result.returncode != 0:
            pip_err = pip_result.stderr.strip() if pip_result.stderr else ""
            return CommandResult(
                success=False,
                output=f"git pull: {git_output}",
                error=f"pip install failed: {pip_err}",
            )

        return CommandResult(
            success=True,
            output=f"git pull: {git_output}\npip install: OK",
        )
    except subprocess.TimeoutExpired:
        return CommandResult(success=False, output="", error="Command timed out")
    except OSError as e:
        return CommandResult(success=False, output="", error=str(e))


# Windows process creation flags for detaching the restarter from the
# bot-manager process tree. Without these, `nssm restart bot-manager` is
# killed when nssm stops the parent service mid-call (observed twice on
# 2026-04-09). With them, the restart command runs in a fully independent
# process and survives the parent kill.
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_BREAKAWAY_FROM_JOB = 0x01000000
_DETACH_FLAGS = (
    _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP | _CREATE_BREAKAWAY_FROM_JOB
)


def restart_bot_manager(delay_seconds: int = 3) -> CommandResult:
    """Schedule a bot-manager service restart that survives parent termination.

    Windows: spawns a fully detached cmd.exe that sleeps `delay_seconds`
    and then runs `nssm restart bot-manager`. The detach flags ensure the
    child is NOT in the bot-manager service's job object, so when nssm
    stops bot-manager mid-restart, the orchestrating cmd.exe keeps running
    and completes the start half. Returns immediately — caller does NOT
    block waiting for the actual restart.

    Linux: keeps the original synchronous `systemctl restart` (no observed
    issue there).
    """
    if not IS_WINDOWS:
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", BOT_MANAGER_SERVICE],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            return CommandResult(
                success=result.returncode == 0,
                output=result.stdout.strip() if result.stdout else "",
                error=result.stderr.strip() if result.stderr else None,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(success=False, output="", error="Command timed out")
        except OSError as e:
            return CommandResult(success=False, output="", error=str(e))

    # Windows: launch a detached cmd.exe that waits then restarts.
    # `timeout /t N /nobreak` is more reliable than `ping -n N localhost`
    # for the delay; `>nul` suppresses output. We don't capture stdout
    # because the child outlives this call.
    delay = max(1, int(delay_seconds))
    cmdline = (
        f'cmd.exe /c "timeout /t {delay} /nobreak >nul '
        f'&& nssm restart {BOT_MANAGER_SERVICE}"'
    )
    try:
        subprocess.Popen(
            cmdline,
            shell=False,
            creationflags=_DETACH_FLAGS,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError as e:
        return CommandResult(
            success=False,
            output="",
            error=f"Failed to spawn detached restart: {e}",
        )

    return CommandResult(
        success=True,
        output=(
            f"Restart scheduled in {delay}s via detached cmd.exe "
            f"(PID will not be tracked)"
        ),
    )


def _parse_nssm_env(raw: str) -> dict:
    """Parse nssm AppEnvironmentExtra output into a dict.

    nssm stores AppEnvironmentExtra as REG_MULTI_SZ in the Windows registry,
    which uses NULL bytes ('\\x00') as delimiters. When nssm cli outputs this,
    the separators may be NULLs, newlines, or a mix of both depending on the
    nssm build and Windows version. We split on all of them to be safe.
    """
    result: dict = {}
    if not raw:
        return result
    # Split on NULL bytes first, then newlines within each segment.
    for chunk in raw.split("\x00"):
        for line in chunk.splitlines():
            stripped = line.strip()
            if not stripped or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            if key:
                result[key] = value
    return result


def _nssm_get_env(service: str) -> tuple[bool, dict, str]:
    """Run `nssm get <service> AppEnvironmentExtra` and return (ok, parsed, err).

    A non-existent AppEnvironmentExtra returns success with an empty dict.
    """
    try:
        result = subprocess.run(
            ["nssm", "get", service, "AppEnvironmentExtra"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, {}, f"nssm get {service} timed out"
    except OSError as e:
        return False, {}, f"nssm not available: {e}"

    if result.returncode != 0:
        return False, {}, (
            f"nssm get {service} failed: "
            f"{result.stderr.strip() if result.stderr else ''}"
        )

    return True, _parse_nssm_env(result.stdout or ""), ""


def load_env_file(path: str = ENV_FILE_PATH) -> int:
    """Load KEY=VALUE lines from an env file into os.environ.

    Returns the count of variables loaded. Missing file is fine — returns 0.
    Values in the file ALWAYS override existing os.environ entries because
    the file contains clean, validated credentials written by
    sync_gmo_credentials, whereas nssm AppEnvironmentExtra may contain
    stale or malformed values from earlier failed persistence attempts.
    """
    if not os.path.isfile(path):
        return 0
    loaded = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if not key:
                    continue
                os.environ[key] = value.strip()
                loaded += 1
    except OSError:
        return loaded
    return loaded


def _write_env_file(path: str, env: dict) -> None:
    """Atomically write a KEY=VALUE env file."""
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("# Auto-generated by sync_gmo_credentials. Do not edit by hand.\n")
        for k in sorted(env.keys()):
            f.write(f"{k}={env[k]}\n")
    os.replace(tmp, path)
    # Best-effort permission tighten on POSIX (no-op on Windows)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def sync_gmo_credentials() -> CommandResult:
    """Copy GMO_API_KEY/SECRET from the gmo-bot nssm service into
    bot-manager's runtime env AND a persistent .env.local file.

    Persistence strategy (fixed 2026-04-09 round 2):
        Earlier attempts via `nssm set AppEnvironmentExtra +KEY=VAL` and
        full multi-arg replacement BOTH failed to persist across reboots
        on this VPS. We now write a `.env.local` file in the bot-manager
        directory which is loaded at app startup via `load_env_file`.
        This bypasses nssm AppEnvironmentExtra entirely.
    """
    if not IS_WINDOWS:
        return CommandResult(
            success=False, output="", error="sync_gmo_credentials is Windows-only"
        )

    # 1. Read GMO creds from gmo-bot service
    ok, gmo_env, err = _nssm_get_env(BOT_SERVICE)
    if not ok:
        return CommandResult(success=False, output="", error=err)

    missing = [k for k in GMO_CRED_KEYS if not gmo_env.get(k)]
    if missing:
        return CommandResult(
            success=False,
            output=f"Keys seen in gmo-bot env: {sorted(gmo_env.keys())}",
            error=f"Missing credentials in gmo-bot service: {missing}",
        )

    creds = {k: gmo_env[k] for k in GMO_CRED_KEYS}

    # 2. Runtime update (immediate effect)
    for k, v in creds.items():
        os.environ[k] = v

    # 3. Persist to .env.local for next startup
    try:
        _write_env_file(ENV_FILE_PATH, creds)
    except OSError as e:
        return CommandResult(
            success=False,
            output=(
                "Runtime env updated but failed to write persistent file"
            ),
            error=f"write {ENV_FILE_PATH} failed: {e}",
        )

    return CommandResult(
        success=True,
        output=(
            f"GMO credentials synced: runtime os.environ updated and "
            f"persisted to {ENV_FILE_PATH} ({len(creds)} keys). "
            f"Loaded automatically by bot-manager at next startup."
        ),
    )


def run_deploy() -> CommandResult:
    """Execute the deploy script (download-release.ps1 or equivalent)."""
    if IS_WINDOWS:
        script = os.path.join(BOT_DIR, "deploy", "download-release.ps1")
        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", script]
    else:
        script = os.path.join(BOT_DIR, "deploy", "download-release.sh")
        cmd = ["bash", script]

    if not os.path.exists(script):
        return CommandResult(
            success=False,
            output="",
            error=f"Deploy script not found: {script}",
        )

    try:
        result = subprocess.run(
            cmd,
            cwd=BOT_DIR,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        return CommandResult(
            success=result.returncode == 0,
            output=result.stdout.strip() if result.stdout else "",
            error=result.stderr.strip() if result.stderr else "" if result.returncode != 0 else None,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            success=False, output="", error="Deploy script timed out (5 min)"
        )
    except OSError as e:
        return CommandResult(success=False, output="", error=str(e))
