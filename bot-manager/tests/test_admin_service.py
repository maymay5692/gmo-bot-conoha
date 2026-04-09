"""Tests for admin_service functions that don't hit the OS."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from services import admin_service
from services.admin_service import (
    _parse_nssm_env,
    load_env_file,
    sync_gmo_credentials,
)


class TestParseNssmEnv:
    """Tests for the nssm AppEnvironmentExtra parser."""

    def test_parses_multiple_lines(self):
        raw = "FOO=1\nBAR=hello world\nBAZ=a=b=c\n"
        result = _parse_nssm_env(raw)
        assert result == {"FOO": "1", "BAR": "hello world", "BAZ": "a=b=c"}

    def test_skips_blank_and_malformed_lines(self):
        raw = "\nNO_EQUALS\nKEY=val\n   \n"
        assert _parse_nssm_env(raw) == {"KEY": "val"}

    def test_null_byte_separated(self):
        """nssm outputs REG_MULTI_SZ with NULL byte delimiters."""
        raw = "FOO=1\x00BAR=2\x00BAZ=3\x00"
        result = _parse_nssm_env(raw)
        assert result == {"FOO": "1", "BAR": "2", "BAZ": "3"}

    def test_mixed_null_and_newline(self):
        raw = "FOO=1\x00BAR=2\r\nBAZ=3\x00"
        result = _parse_nssm_env(raw)
        assert result == {"FOO": "1", "BAR": "2", "BAZ": "3"}

    def test_empty_input(self):
        assert _parse_nssm_env("") == {}
        assert _parse_nssm_env(None) == {}


def _mock_get_run(stdout: str, returncode: int = 0, stderr: str = "") -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


class TestLoadEnvFile:
    """Tests for the env-file loader used at app startup."""

    def test_missing_file_returns_zero(self, tmp_path):
        path = tmp_path / "missing.env"
        assert load_env_file(str(path)) == 0

    def test_loads_keys_into_environ(self, tmp_path, monkeypatch):
        path = tmp_path / ".env.local"
        path.write_text("FOO=bar\nBAZ=qux\n")
        monkeypatch.delenv("FOO", raising=False)
        monkeypatch.delenv("BAZ", raising=False)
        n = load_env_file(str(path))
        assert n == 2
        assert os.environ["FOO"] == "bar"
        assert os.environ["BAZ"] == "qux"

    def test_overrides_existing(self, tmp_path, monkeypatch):
        """File values must override stale nssm env entries."""
        path = tmp_path / ".env.local"
        path.write_text("FOO=from_file\n")
        monkeypatch.setenv("FOO", "stale_junk")
        n = load_env_file(str(path))
        assert n == 1
        assert os.environ["FOO"] == "from_file"

    def test_skips_comments_and_blanks(self, tmp_path, monkeypatch):
        path = tmp_path / ".env.local"
        path.write_text("# comment\n\nFOO=ok\n# another\n")
        monkeypatch.delenv("FOO", raising=False)
        n = load_env_file(str(path))
        assert n == 1
        assert os.environ["FOO"] == "ok"

    def test_skips_malformed_lines(self, tmp_path, monkeypatch):
        path = tmp_path / ".env.local"
        path.write_text("NOEQUALS\n=novalue\nFOO=ok\n")
        monkeypatch.delenv("FOO", raising=False)
        n = load_env_file(str(path))
        assert n == 1


class TestSyncGmoCredentials:
    """Tests for sync_gmo_credentials (env-file persistence path)."""

    @pytest.fixture(autouse=True)
    def _force_windows(self):
        with patch.object(admin_service, "IS_WINDOWS", True):
            yield

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        for k in ("GMO_API_KEY", "GMO_API_SECRET"):
            monkeypatch.delenv(k, raising=False)
        yield

    @pytest.fixture
    def env_file(self, tmp_path, monkeypatch):
        """Redirect ENV_FILE_PATH to a tmp file."""
        path = tmp_path / ".env.local"
        monkeypatch.setattr(admin_service, "ENV_FILE_PATH", str(path))
        return path

    def test_success_writes_env_file(self, env_file):
        gmo_get = _mock_get_run(
            "GMO_API_KEY=testkey\nGMO_API_SECRET=testsecret\nOTHER=ignored\n"
        )
        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.return_value = gmo_get
            result = sync_gmo_credentials()

        assert result.success is True
        assert os.environ["GMO_API_KEY"] == "testkey"
        assert os.environ["GMO_API_SECRET"] == "testsecret"

        # Only ONE subprocess call now: nssm get gmo-bot
        assert mock_run.call_count == 1
        assert mock_run.call_args[0][0] == [
            "nssm", "get", "gmo-bot", "AppEnvironmentExtra"
        ]

        # Persistent file written with both creds
        assert env_file.exists()
        content = env_file.read_text()
        assert "GMO_API_KEY=testkey" in content
        assert "GMO_API_SECRET=testsecret" in content
        # No unrelated keys leaked into the file
        assert "OTHER" not in content

    def test_env_file_is_atomic(self, env_file):
        """Pre-existing file must remain valid after a failed write attempt."""
        env_file.write_text("OLD_KEY=old\n")
        gmo_get = _mock_get_run("GMO_API_KEY=newkey\nGMO_API_SECRET=newsecret\n")
        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.return_value = gmo_get
            sync_gmo_credentials()

        content = env_file.read_text()
        assert "GMO_API_KEY=newkey" in content
        assert "GMO_API_SECRET=newsecret" in content
        # Old key gone — file is fully replaced (creds-only)
        assert "OLD_KEY" not in content

    def test_missing_credentials_returns_error(self, env_file):
        gmo_get = _mock_get_run("OTHER=x\n")
        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.return_value = gmo_get
            result = sync_gmo_credentials()

        assert result.success is False
        assert "Missing credentials" in (result.error or "")
        assert "GMO_API_KEY" not in os.environ
        assert not env_file.exists()

    def test_nssm_get_failure(self, env_file):
        gmo_get = _mock_get_run("", returncode=1, stderr="service not found")
        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.return_value = gmo_get
            result = sync_gmo_credentials()

        assert result.success is False
        assert "nssm get gmo-bot failed" in (result.error or "")
        assert "GMO_API_KEY" not in os.environ
        assert not env_file.exists()

    def test_write_failure_surfaces_error(self, tmp_path, monkeypatch):
        # Point env file at a path inside a non-existent dir AND make
        # makedirs raise to force OSError on write
        bad_path = "/nonexistent/path/with/no/perms/.env.local"
        monkeypatch.setattr(admin_service, "ENV_FILE_PATH", bad_path)
        gmo_get = _mock_get_run("GMO_API_KEY=k\nGMO_API_SECRET=s\n")
        with patch("services.admin_service.subprocess.run") as mock_run, \
             patch(
                 "services.admin_service.os.makedirs",
                 side_effect=OSError("permission denied"),
             ):
            mock_run.return_value = gmo_get
            result = sync_gmo_credentials()

        assert result.success is False
        assert "failed to write persistent file" in (result.output or "")
        # Runtime env IS still updated
        assert os.environ["GMO_API_KEY"] == "k"

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
