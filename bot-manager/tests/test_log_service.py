"""Tests for log_service module."""
import pytest
from unittest.mock import patch, MagicMock

from services.log_service import get_recent_logs, get_logs_since, TIMESTAMP_PATTERN


class TestGetRecentLogs:
    """Tests for get_recent_logs function."""

    @patch("services.log_service.subprocess.run")
    def test_returns_log_lines(self, mock_run):
        """Should return list of log lines."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Jan 01 00:00:00 server gmo[123]: Starting bot\n"
                   "Jan 01 00:00:01 server gmo[123]: Connected to API\n"
                   "Jan 01 00:00:02 server gmo[123]: Placing order\n"
        )

        logs = get_recent_logs(lines=100)

        assert len(logs) == 3
        assert "Starting bot" in logs[0]
        assert "Connected to API" in logs[1]

    @patch("services.log_service.subprocess.run")
    def test_respects_lines_parameter(self, mock_run):
        """Should pass lines parameter to journalctl."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        get_recent_logs(lines=50)

        args = mock_run.call_args[0][0]
        assert "-n" in args
        idx = args.index("-n")
        assert args[idx + 1] == "50"

    @patch("services.log_service.subprocess.run")
    def test_returns_empty_list_on_error(self, mock_run):
        """Should return empty list when journalctl fails."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Failed to get journal"
        )

        logs = get_recent_logs()

        assert logs == []

    @patch("services.log_service.subprocess.run")
    def test_filters_empty_lines(self, mock_run):
        """Should filter out empty lines from output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Line 1\n\nLine 2\n\n\nLine 3\n"
        )

        logs = get_recent_logs()

        assert len(logs) == 3
        assert all(line.strip() for line in logs)

    @patch("services.log_service.subprocess.run")
    def test_negative_lines_becomes_positive(self, mock_run):
        """Should convert negative lines to positive."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        get_recent_logs(lines=-10)

        args = mock_run.call_args[0][0]
        idx = args.index("-n")
        assert args[idx + 1] == "1"


class TestGetLogsSince:
    """Tests for get_logs_since function."""

    def test_valid_date_format(self):
        """Should accept valid date format."""
        assert TIMESTAMP_PATTERN.match("2024-01-01")
        assert TIMESTAMP_PATTERN.match("2024-12-31 23:59:59")

    def test_invalid_date_format(self):
        """Should reject invalid date formats."""
        assert not TIMESTAMP_PATTERN.match("invalid")
        assert not TIMESTAMP_PATTERN.match("01-01-2024")
        assert not TIMESTAMP_PATTERN.match("2024/01/01")
        assert not TIMESTAMP_PATTERN.match("2024-01-01; rm -rf /")

    @patch("services.log_service.subprocess.run")
    def test_rejects_invalid_timestamp(self, mock_run):
        """Should return empty list for invalid timestamp."""
        logs = get_logs_since("invalid; rm -rf /")

        assert logs == []
        mock_run.assert_not_called()

    @patch("services.log_service.subprocess.run")
    def test_accepts_valid_timestamp(self, mock_run):
        """Should accept valid timestamp."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Log line\n")

        logs = get_logs_since("2024-01-01")

        assert logs == ["Log line"]
        mock_run.assert_called_once()
