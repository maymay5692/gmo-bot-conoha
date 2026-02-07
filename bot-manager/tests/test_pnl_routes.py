"""Tests for P&L routes."""
import pytest
from unittest.mock import patch, MagicMock

from config import TestConfig


@pytest.fixture
def app():
    """Create application for testing."""
    from app import create_app
    test_config = TestConfig()
    test_config.WTF_CSRF_ENABLED = False
    test_config.BASIC_AUTH_PASSWORD = ""
    flask_app = create_app(test_config)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


class TestPnlPage:
    """Tests for P&L page."""

    @patch("routes.pnl.pnl_service")
    def test_pnl_page_returns_200(self, mock_pnl, client):
        """P&L page should return 200."""
        mock_pnl.take_snapshot.return_value = None
        mock_pnl.get_current_pnl.return_value = {
            "actual_profit_loss": "50000",
            "available_amount": "40000",
            "profit_loss": "500",
            "margin": "10000",
        }

        response = client.get("/pnl")

        assert response.status_code == 200
        assert b"P&amp;L" in response.data or b"P&L" in response.data

    @patch("routes.pnl.pnl_service")
    def test_pnl_page_handles_no_data(self, mock_pnl, client):
        """P&L page should handle missing data gracefully."""
        mock_pnl.take_snapshot.return_value = None
        mock_pnl.get_current_pnl.return_value = None

        response = client.get("/pnl")

        assert response.status_code == 200


class TestPnlDataApi:
    """Tests for P&L data API."""

    @patch("routes.pnl.pnl_service")
    def test_returns_chart_data(self, mock_pnl, client):
        """Should return chart data as JSON."""
        mock_pnl.take_snapshot.return_value = None
        mock_pnl.get_chart_data.return_value = {
            "labels": ["2026-01-01 00:00:00"],
            "actual_profit_loss": [50000.0],
            "unrealized_profit_loss": [500.0],
        }

        response = client.get("/api/pnl/data")

        assert response.status_code == 200
        data = response.get_json()
        assert "labels" in data
        assert "actual_profit_loss" in data

    @patch("routes.pnl.pnl_service")
    def test_accepts_hours_param(self, mock_pnl, client):
        """Should pass hours parameter to service."""
        mock_pnl.take_snapshot.return_value = None
        mock_pnl.get_chart_data.return_value = {
            "labels": [],
            "actual_profit_loss": [],
            "unrealized_profit_loss": [],
        }

        client.get("/api/pnl/data?hours=6")

        mock_pnl.get_chart_data.assert_called_once_with(hours=6)

    @patch("routes.pnl.pnl_service")
    def test_clamps_hours_param(self, mock_pnl, client):
        """Should clamp hours to valid range."""
        mock_pnl.take_snapshot.return_value = None
        mock_pnl.get_chart_data.return_value = {
            "labels": [],
            "actual_profit_loss": [],
            "unrealized_profit_loss": [],
        }

        client.get("/api/pnl/data?hours=999")

        mock_pnl.get_chart_data.assert_called_once_with(hours=240)


class TestPnlCurrentApi:
    """Tests for current P&L API."""

    @patch("routes.pnl.pnl_service")
    def test_returns_current_pnl(self, mock_pnl, client):
        """Should return current P&L as JSON."""
        mock_pnl.get_current_pnl.return_value = {
            "actual_profit_loss": "50000",
            "profit_loss": "500",
        }

        response = client.get("/api/pnl/current")

        assert response.status_code == 200
        data = response.get_json()
        assert data["actual_profit_loss"] == "50000"

    @patch("routes.pnl.pnl_service")
    def test_returns_503_on_error(self, mock_pnl, client):
        """Should return 503 when data is unavailable."""
        mock_pnl.get_current_pnl.return_value = None

        response = client.get("/api/pnl/current")

        assert response.status_code == 503
