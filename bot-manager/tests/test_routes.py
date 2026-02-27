"""Tests for route handlers."""
import pytest
from unittest.mock import patch, MagicMock

from config import TestConfig


@pytest.fixture
def app():
    """Create application for testing."""
    from app import create_app
    test_config = TestConfig()
    test_config.WTF_CSRF_ENABLED = False  # Disable CSRF for testing
    test_config.BASIC_AUTH_PASSWORD = ""  # Disable auth for testing
    flask_app = create_app(test_config)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestDashboardRoutes:
    """Tests for dashboard routes."""

    @patch("routes.dashboard.pnl_service")
    @patch("routes.dashboard.get_status")
    @patch("routes.dashboard.get_recent_logs")
    def test_index_returns_200(self, mock_logs, mock_status, mock_pnl, client):
        """Dashboard index should return 200."""
        mock_status.return_value = MagicMock(
            is_running=True, pid=123, memory="50M", uptime="1h", error=None
        )
        mock_logs.return_value = ["Log line 1", "Log line 2"]
        mock_pnl.take_snapshot.return_value = None
        mock_pnl.get_current_pnl.return_value = None

        response = client.get("/")

        assert response.status_code == 200
        assert b"Dashboard" in response.data


class TestBotControlRoutes:
    """Tests for bot control API routes."""

    @patch("routes.bot_control.get_status")
    def test_api_status_returns_json(self, mock_status, client):
        """API status should return JSON."""
        mock_status.return_value = MagicMock(
            is_running=True, pid=123, memory="50M", uptime="1h", error=None
        )

        response = client.get("/api/status")

        assert response.status_code == 200
        assert response.content_type == "application/json"
        data = response.get_json()
        assert data["is_running"] is True
        assert data["pid"] == 123

    @patch("routes.bot_control.start_bot")
    def test_api_start_success(self, mock_start, client):
        """API start should return success."""
        mock_start.return_value = True

        response = client.post("/api/bot/start")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    @patch("routes.bot_control.start_bot")
    def test_api_start_failure(self, mock_start, client):
        """API start should return 500 on failure."""
        mock_start.return_value = False

        response = client.post("/api/bot/start")

        assert response.status_code == 500
        data = response.get_json()
        assert data["success"] is False

    @patch("routes.bot_control.stop_bot")
    def test_api_stop_success(self, mock_stop, client):
        """API stop should return success."""
        mock_stop.return_value = True

        response = client.post("/api/bot/stop")

        assert response.status_code == 200

    @patch("routes.bot_control.restart_bot")
    def test_api_restart_success(self, mock_restart, client):
        """API restart should return success."""
        mock_restart.return_value = True

        response = client.post("/api/bot/restart")

        assert response.status_code == 200


class TestTunnelUrlRoute:
    """Tests for /api/tunnel-url endpoint."""

    def test_tunnel_url_no_log_file(self, client):
        """Should return null when log file doesn't exist."""
        response = client.get("/api/tunnel-url")
        assert response.status_code == 200
        data = response.get_json()
        assert data["tunnel_url"] is None

    def test_tunnel_url_with_log_file(self, client, tmp_path):
        """Should extract URL from cloudflared log."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        log_file = log_dir / "cloudflared-stderr.log"
        log_file.write_text(
            "2026-02-27T10:00:00Z INF Starting tunnel\n"
            "2026-02-27T10:00:01Z INF +----------------------------+\n"
            "2026-02-27T10:00:01Z INF |  https://abc-def-123.trycloudflare.com  |\n"
            "2026-02-27T10:00:01Z INF +----------------------------+\n"
            "2026-02-27T10:00:02Z INF Connection registered\n"
        )
        # Override BOT_LOG_DIR for this test
        client.application.config["APP_CONFIG"].BOT_LOG_DIR = str(log_dir)

        response = client.get("/api/tunnel-url")
        assert response.status_code == 200
        data = response.get_json()
        assert data["tunnel_url"] == "https://abc-def-123.trycloudflare.com"

    def test_tunnel_url_no_match_in_log(self, client, tmp_path):
        """Should return null when URL not found in log."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        log_file = log_dir / "cloudflared-stderr.log"
        log_file.write_text("2026-02-27T10:00:00Z INF Some other message\n")
        client.application.config["APP_CONFIG"].BOT_LOG_DIR = str(log_dir)

        response = client.get("/api/tunnel-url")
        data = response.get_json()
        assert data["tunnel_url"] is None
        assert "not found" in data["error"]


class TestLogsRoutes:
    """Tests for logs routes."""

    @patch("routes.logs.get_recent_logs")
    def test_logs_page_returns_200(self, mock_logs, client):
        """Logs page should return 200."""
        mock_logs.return_value = ["Log line"]

        response = client.get("/logs")

        assert response.status_code == 200

    @patch("routes.logs.get_recent_logs")
    def test_logs_page_caps_lines(self, mock_logs, client):
        """Logs page should cap lines at 1000."""
        mock_logs.return_value = []

        client.get("/logs?lines=5000")

        mock_logs.assert_called_once_with(lines=1000)

    @patch("routes.logs.get_recent_logs")
    def test_logs_page_min_lines(self, mock_logs, client):
        """Logs page should enforce minimum of 1 line."""
        mock_logs.return_value = []

        client.get("/logs?lines=-10")

        mock_logs.assert_called_once_with(lines=1)

    @patch("routes.logs.get_recent_logs")
    def test_api_logs_returns_json(self, mock_logs, client):
        """API logs should return JSON."""
        mock_logs.return_value = ["Line 1", "Line 2"]

        response = client.get("/api/logs")

        assert response.status_code == 200
        data = response.get_json()
        assert data["count"] == 2
        assert len(data["logs"]) == 2
