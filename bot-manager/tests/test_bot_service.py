"""Tests for bot_service module."""
import pytest
from unittest.mock import patch, MagicMock

from services.bot_service import (
    get_status,
    start_bot,
    stop_bot,
    restart_bot,
    BotStatus,
)


class TestGetStatus:
    """Tests for get_status function."""

    @patch("services.bot_service.subprocess.run")
    def test_returns_running_status_when_active(self, mock_run):
        """Should return running status when systemd service is active."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="● gmo-bot.service - GMO Trading Bot\n"
                   "   Loaded: loaded\n"
                   "   Active: active (running) since Mon 2024-01-01 00:00:00 UTC\n"
                   "   Main PID: 1234 (gmo)\n"
                   "   Memory: 50.0M\n"
        )

        status = get_status()

        assert status.is_running is True
        assert status.pid == 1234
        assert "50.0M" in status.memory

    @patch("services.bot_service.subprocess.run")
    def test_returns_stopped_status_when_inactive(self, mock_run):
        """Should return stopped status when systemd service is inactive."""
        mock_run.return_value = MagicMock(
            returncode=3,
            stdout="● gmo-bot.service - GMO Trading Bot\n"
                   "   Loaded: loaded\n"
                   "   Active: inactive (dead)\n"
        )

        status = get_status()

        assert status.is_running is False
        assert status.pid is None

    @patch("services.bot_service.subprocess.run")
    def test_handles_service_not_found(self, mock_run):
        """Should handle case when service doesn't exist."""
        mock_run.return_value = MagicMock(
            returncode=4,
            stdout="",
            stderr="Unit gmo-bot.service could not be found."
        )

        status = get_status()

        assert status.is_running is False
        assert status.error == "Service not found"


class TestStartBot:
    """Tests for start_bot function."""

    @patch("services.bot_service.subprocess.run")
    def test_returns_true_on_success(self, mock_run):
        """Should return True when service starts successfully."""
        mock_run.return_value = MagicMock(returncode=0)

        result = start_bot()

        assert result is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "start" in args
        assert "gmo-bot" in args

    @patch("services.bot_service.subprocess.run")
    def test_returns_false_on_failure(self, mock_run):
        """Should return False when service fails to start."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="Failed to start"
        )

        result = start_bot()

        assert result is False


class TestStopBot:
    """Tests for stop_bot function."""

    @patch("services.bot_service.subprocess.run")
    def test_returns_true_on_success(self, mock_run):
        """Should return True when service stops successfully."""
        mock_run.return_value = MagicMock(returncode=0)

        result = stop_bot()

        assert result is True
        args = mock_run.call_args[0][0]
        assert "stop" in args

    @patch("services.bot_service.subprocess.run")
    def test_returns_false_on_failure(self, mock_run):
        """Should return False when service fails to stop."""
        mock_run.return_value = MagicMock(returncode=1)

        result = stop_bot()

        assert result is False


class TestRestartBot:
    """Tests for restart_bot function."""

    @patch("services.bot_service.subprocess.run")
    def test_returns_true_on_success(self, mock_run):
        """Should return True when service restarts successfully."""
        mock_run.return_value = MagicMock(returncode=0)

        result = restart_bot()

        assert result is True
        args = mock_run.call_args[0][0]
        assert "restart" in args

    @patch("services.bot_service.subprocess.run")
    def test_returns_false_on_failure(self, mock_run):
        """Should return False when service fails to restart."""
        mock_run.return_value = MagicMock(returncode=1)

        result = restart_bot()

        assert result is False
