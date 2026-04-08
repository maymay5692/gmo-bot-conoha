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

    nssm prints each variable as a KEY=VALUE line. Blank lines and
    lines without '=' are ignored.
    """
    result: dict = {}
    for line in (raw or "").splitlines():
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


def sync_gmo_credentials() -> CommandResult:
    """Copy GMO_API_KEY/SECRET from the gmo-bot nssm service into
    the bot-manager service and the current Python process.

    Persistence strategy (fixed 2026-04-09):
        The previous version used ``nssm set ... +KEY=VAL`` which did NOT
        survive a VPS reboot in practice. We now read bot-manager's existing
        AppEnvironmentExtra, merge in the credentials, and write the FULL
        list back (no '+' prefix). This is what the nssm GUI does and is
        the only documented way to reliably persist values.
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

    # 2. Read bot-manager's existing env so we don't clobber other vars
    ok, manager_env, err = _nssm_get_env(BOT_MANAGER_SERVICE)
    if not ok:
        return CommandResult(success=False, output="", error=err)

    # 3. Runtime update (takes effect immediately, no restart needed)
    for key in GMO_CRED_KEYS:
        os.environ[key] = gmo_env[key]

    # 4. Build merged env (gmo creds override any existing values for those keys)
    merged = {**manager_env}
    for key in GMO_CRED_KEYS:
        merged[key] = gmo_env[key]

    # 5. Persist by writing the FULL list back. nssm replaces the entire
    # AppEnvironmentExtra value when no '+' / '-' prefix is given.
    set_cmd = ["nssm", "set", BOT_MANAGER_SERVICE, "AppEnvironmentExtra"]
    for k in sorted(merged.keys()):
        set_cmd.append(f"{k}={merged[k]}")

    try:
        set_result = subprocess.run(
            set_cmd, capture_output=True, text=True, check=False, timeout=30
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            success=False,
            output="Runtime env updated but nssm set timed out",
            error="nssm set bot-manager timed out",
        )
    except OSError as e:
        return CommandResult(
            success=False,
            output="Runtime env updated but nssm set failed",
            error=str(e),
        )

    if set_result.returncode != 0:
        return CommandResult(
            success=False,
            output="Runtime env updated but nssm set failed",
            error=(
                f"nssm set bot-manager failed: "
                f"{set_result.stderr.strip() if set_result.stderr else ''}"
            ),
        )

    other_keys = sorted(k for k in merged if k not in GMO_CRED_KEYS)
    return CommandResult(
        success=True,
        output=(
            f"GMO credentials synced: runtime os.environ updated and "
            f"bot-manager AppEnvironmentExtra persisted with {len(merged)} "
            f"vars (preserved: {other_keys}, set: {list(GMO_CRED_KEYS)})"
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
