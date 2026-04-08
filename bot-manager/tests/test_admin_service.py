"""Tests for admin_service functions that don't hit the OS."""
import os
from unittest.mock import patch, MagicMock

import pytest

from services import admin_service
from services.admin_service import _parse_nssm_env, sync_gmo_credentials


class TestParseNssmEnv:
    """Tests for the nssm AppEnvironmentExtra parser."""

    def test_parses_multiple_lines(self):
        raw = "FOO=1\nBAR=hello world\nBAZ=a=b=c\n"
        result = _parse_nssm_env(raw)
        assert result == {"FOO": "1", "BAR": "hello world", "BAZ": "a=b=c"}

    def test_skips_blank_and_malformed_lines(self):
        raw = "\nNO_EQUALS\nKEY=val\n   \n"
        assert _parse_nssm_env(raw) == {"KEY": "val"}

    def test_empty_input(self):
        assert _parse_nssm_env("") == {}
        assert _parse_nssm_env(None) == {}


def _mock_get_run(stdout: str, returncode: int = 0, stderr: str = "") -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestSyncGmoCredentials:
    """Tests for sync_gmo_credentials.

    The function makes 3 subprocess.run calls in order:
      1. nssm get gmo-bot AppEnvironmentExtra
      2. nssm get bot-manager AppEnvironmentExtra
      3. nssm set bot-manager AppEnvironmentExtra <merged list>
    """

    @pytest.fixture(autouse=True)
    def _force_windows(self):
        with patch.object(admin_service, "IS_WINDOWS", True):
            yield

    @pytest.fixture(autouse=True)
    def _clean_env(self):
        saved = {k: os.environ.get(k) for k in ("GMO_API_KEY", "GMO_API_SECRET")}
        os.environ.pop("GMO_API_KEY", None)
        os.environ.pop("GMO_API_SECRET", None)
        yield
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_success_writes_full_env_back(self):
        gmo_get = _mock_get_run(
            "GMO_API_KEY=testkey\nGMO_API_SECRET=testsecret\nOTHER=ignored\n"
        )
        manager_get = _mock_get_run("ADMIN_PASS=secret\nDISCORD_WEBHOOK_URL=https://x\n")
        set_ok = _mock_get_run("")

        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.side_effect = [gmo_get, manager_get, set_ok]
            result = sync_gmo_credentials()

        assert result.success is True
        assert os.environ["GMO_API_KEY"] == "testkey"
        assert os.environ["GMO_API_SECRET"] == "testsecret"

        calls = mock_run.call_args_list
        assert calls[0][0][0] == ["nssm", "get", "gmo-bot", "AppEnvironmentExtra"]
        assert calls[1][0][0] == ["nssm", "get", "bot-manager", "AppEnvironmentExtra"]

        set_args = calls[2][0][0]
        assert set_args[:4] == ["nssm", "set", "bot-manager", "AppEnvironmentExtra"]
        # Full list write — must include both pre-existing AND new vars,
        # and must NOT use the broken '+' prefix.
        assert "ADMIN_PASS=secret" in set_args
        assert "DISCORD_WEBHOOK_URL=https://x" in set_args
        assert "GMO_API_KEY=testkey" in set_args
        assert "GMO_API_SECRET=testsecret" in set_args
        assert not any(a.startswith("+") for a in set_args)

    def test_overrides_existing_gmo_keys(self):
        """If bot-manager already has stale GMO_API_KEY, it must be replaced."""
        gmo_get = _mock_get_run("GMO_API_KEY=newkey\nGMO_API_SECRET=newsecret\n")
        manager_get = _mock_get_run("GMO_API_KEY=stalekey\nADMIN_PASS=p\n")
        set_ok = _mock_get_run("")

        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.side_effect = [gmo_get, manager_get, set_ok]
            sync_gmo_credentials()

        set_args = mock_run.call_args_list[2][0][0]
        assert "GMO_API_KEY=newkey" in set_args
        assert "GMO_API_KEY=stalekey" not in set_args
        assert "ADMIN_PASS=p" in set_args

    def test_handles_empty_manager_env(self):
        """First-time sync where bot-manager has no extras."""
        gmo_get = _mock_get_run("GMO_API_KEY=k\nGMO_API_SECRET=s\n")
        manager_get = _mock_get_run("")  # nothing pre-existing
        set_ok = _mock_get_run("")

        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.side_effect = [gmo_get, manager_get, set_ok]
            result = sync_gmo_credentials()

        assert result.success is True
        set_args = mock_run.call_args_list[2][0][0]
        assert "GMO_API_KEY=k" in set_args
        assert "GMO_API_SECRET=s" in set_args
        # Only the two GMO keys plus the nssm fixed args
        assert len(set_args) == 6

    def test_missing_credentials_returns_error(self):
        gmo_get = _mock_get_run("OTHER=x\n")
        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.return_value = gmo_get
            result = sync_gmo_credentials()

        assert result.success is False
        assert "Missing credentials" in (result.error or "")
        assert "GMO_API_KEY" not in os.environ
        assert mock_run.call_count == 1  # only the gmo-bot get

    def test_nssm_get_gmo_bot_failure(self):
        gmo_get = _mock_get_run("", returncode=1, stderr="service not found")
        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.return_value = gmo_get
            result = sync_gmo_credentials()

        assert result.success is False
        assert "nssm get gmo-bot failed" in (result.error or "")
        assert mock_run.call_count == 1

    def test_nssm_get_bot_manager_failure(self):
        gmo_get = _mock_get_run("GMO_API_KEY=k\nGMO_API_SECRET=s\n")
        manager_get = _mock_get_run("", returncode=1, stderr="not found")
        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.side_effect = [gmo_get, manager_get]
            result = sync_gmo_credentials()

        assert result.success is False
        assert "nssm get bot-manager failed" in (result.error or "")
        # os.environ NOT updated yet — we abort before runtime change
        assert "GMO_API_KEY" not in os.environ
        assert mock_run.call_count == 2

    def test_nssm_set_failure_surfaces_error(self):
        gmo_get = _mock_get_run("GMO_API_KEY=k\nGMO_API_SECRET=s\n")
        manager_get = _mock_get_run("ADMIN_PASS=p\n")
        set_fail = _mock_get_run("", returncode=1, stderr="access denied")

        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.side_effect = [gmo_get, manager_get, set_fail]
            result = sync_gmo_credentials()

        assert result.success is False
        assert "nssm set bot-manager failed" in (result.error or "")
        # Runtime env IS updated even though persistence failed
        assert os.environ["GMO_API_KEY"] == "k"
        assert os.environ["GMO_API_SECRET"] == "s"

    def test_non_windows_returns_error(self):
        with patch.object(admin_service, "IS_WINDOWS", False):
            result = sync_gmo_credentials()
        assert result.success is False
        assert "Windows-only" in (result.error or "")


class TestRestartBotManagerWindows:
    """Tests for restart_bot_manager Windows detached spawn."""

    @pytest.fixture(autouse=True)
    def _force_windows(self):
        with patch.object(admin_service, "IS_WINDOWS", True):
            yield

    def test_spawns_detached_process(self):
        """Must use Popen with the detach flag combo, not subprocess.run."""
        with patch("services.admin_service.subprocess.Popen") as mock_popen:
            result = admin_service.restart_bot_manager()

        assert result.success is True
        assert mock_popen.call_count == 1

        kwargs = mock_popen.call_args.kwargs
        # Detach flags must be set
        flags = kwargs["creationflags"]
        assert flags & admin_service._DETACHED_PROCESS
        assert flags & admin_service._CREATE_NEW_PROCESS_GROUP
        assert flags & admin_service._CREATE_BREAKAWAY_FROM_JOB

        # stdio must be detached so closing parent doesn't break the child
        from subprocess import DEVNULL
        assert kwargs["stdin"] is DEVNULL
        assert kwargs["stdout"] is DEVNULL
        assert kwargs["stderr"] is DEVNULL

    def test_command_includes_delay_and_restart(self):
        with patch("services.admin_service.subprocess.Popen") as mock_popen:
            admin_service.restart_bot_manager(delay_seconds=5)

        cmdline = mock_popen.call_args.args[0]
        assert "timeout /t 5" in cmdline
        assert "nssm restart bot-manager" in cmdline
        assert "cmd.exe /c" in cmdline

    def test_minimum_delay_one_second(self):
        with patch("services.admin_service.subprocess.Popen") as mock_popen:
            admin_service.restart_bot_manager(delay_seconds=0)

        cmdline = mock_popen.call_args.args[0]
        assert "timeout /t 1" in cmdline

    def test_popen_failure_returns_error(self):
        with patch("services.admin_service.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = OSError("file not found")
            result = admin_service.restart_bot_manager()

        assert result.success is False
        assert "Failed to spawn detached restart" in (result.error or "")
        assert "file not found" in (result.error or "")

    def test_returns_immediately_does_not_run_subprocess(self):
        """Must NOT use subprocess.run (which would block the parent)."""
        with patch("services.admin_service.subprocess.Popen") as mock_popen, \
             patch("services.admin_service.subprocess.run") as mock_run:
            admin_service.restart_bot_manager()
        assert mock_popen.call_count == 1
        assert mock_run.call_count == 0


class TestRestartBotManagerLinux:
    """Tests for restart_bot_manager on non-Windows (sync systemctl)."""

    @pytest.fixture(autouse=True)
    def _force_linux(self):
        with patch.object(admin_service, "IS_WINDOWS", False):
            yield

    def test_uses_systemctl(self):
        ok = MagicMock(returncode=0, stdout="ok", stderr="")
        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.return_value = ok
            result = admin_service.restart_bot_manager()
        assert result.success is True
        cmd = mock_run.call_args[0][0]
        assert cmd == ["sudo", "systemctl", "restart", "bot-manager"]
