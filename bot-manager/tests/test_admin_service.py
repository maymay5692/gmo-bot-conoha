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


class TestSyncGmoCredentials:
    """Tests for sync_gmo_credentials."""

    @pytest.fixture(autouse=True)
    def _force_windows(self):
        """Force IS_WINDOWS=True so the function doesn't early-return."""
        with patch.object(admin_service, "IS_WINDOWS", True):
            yield

    @pytest.fixture(autouse=True)
    def _clean_env(self):
        """Ensure test doesn't leak creds into the real process env."""
        saved = {k: os.environ.get(k) for k in ("GMO_API_KEY", "GMO_API_SECRET")}
        os.environ.pop("GMO_API_KEY", None)
        os.environ.pop("GMO_API_SECRET", None)
        yield
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_success_updates_env_and_persists(self):
        get_mock = MagicMock(
            returncode=0,
            stdout="GMO_API_KEY=testkey\nGMO_API_SECRET=testsecret\nOTHER=x\n",
            stderr="",
        )
        set_mock = MagicMock(returncode=0, stdout="", stderr="")

        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.side_effect = [get_mock, set_mock]
            result = sync_gmo_credentials()

        assert result.success is True
        assert os.environ["GMO_API_KEY"] == "testkey"
        assert os.environ["GMO_API_SECRET"] == "testsecret"

        # First call: nssm get gmo-bot
        first_args = mock_run.call_args_list[0][0][0]
        assert first_args == ["nssm", "get", "gmo-bot", "AppEnvironmentExtra"]

        # Second call: nssm set bot-manager with + prefix for both keys
        second_args = mock_run.call_args_list[1][0][0]
        assert second_args[:4] == [
            "nssm", "set", "bot-manager", "AppEnvironmentExtra",
        ]
        assert "+GMO_API_KEY=testkey" in second_args
        assert "+GMO_API_SECRET=testsecret" in second_args

    def test_missing_credentials_returns_error(self):
        get_mock = MagicMock(
            returncode=0, stdout="OTHER=x\n", stderr=""
        )
        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.return_value = get_mock
            result = sync_gmo_credentials()

        assert result.success is False
        assert "Missing credentials" in (result.error or "")
        assert "GMO_API_KEY" not in os.environ
        # Only nssm get was called; no set attempt
        assert mock_run.call_count == 1

    def test_nssm_get_failure_returns_error(self):
        get_mock = MagicMock(
            returncode=1, stdout="", stderr="service not found"
        )
        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.return_value = get_mock
            result = sync_gmo_credentials()

        assert result.success is False
        assert "nssm get gmo-bot failed" in (result.error or "")
        assert mock_run.call_count == 1

    def test_nssm_set_failure_surfaces_error(self):
        get_mock = MagicMock(
            returncode=0,
            stdout="GMO_API_KEY=k\nGMO_API_SECRET=s\n",
            stderr="",
        )
        set_mock = MagicMock(returncode=1, stdout="", stderr="access denied")

        with patch("services.admin_service.subprocess.run") as mock_run:
            mock_run.side_effect = [get_mock, set_mock]
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
