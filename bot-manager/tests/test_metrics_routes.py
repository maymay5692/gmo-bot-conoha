"""Tests for metrics API routes."""
import pytest
from unittest.mock import patch

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


class TestMetricsCsvApi:
    """Tests for GET /api/metrics/csv."""

    @patch("routes.metrics.metrics_service")
    def test_returns_metrics_data(self, mock_svc, client):
        """Should return metrics CSV data as JSON."""
        mock_svc.get_metrics_csv.return_value = [
            {"timestamp": "2026-02-14T10:00:00Z", "mid_price": "6500000", "buy_prob_avg": "0.45"},
            {"timestamp": "2026-02-14T10:00:10Z", "mid_price": "6501000", "buy_prob_avg": "0.48"},
        ]

        response = client.get("/api/metrics/csv?date=2026-02-14")

        assert response.status_code == 200
        data = response.get_json()
        assert data["date"] == "2026-02-14"
        assert data["type"] == "metrics"
        assert len(data["rows"]) == 2
        assert data["count"] == 2
        assert data["rows"][0]["mid_price"] == "6500000"

    @patch("routes.metrics.metrics_service")
    def test_returns_404_for_missing_data(self, mock_svc, client):
        """Should return 404 when CSV file doesn't exist."""
        mock_svc.get_metrics_csv.return_value = None

        response = client.get("/api/metrics/csv?date=2026-02-14")

        assert response.status_code == 404

    @patch("routes.metrics.metrics_service")
    def test_returns_400_for_missing_date(self, mock_svc, client):
        """Should return 400 when date param is missing."""
        response = client.get("/api/metrics/csv")

        assert response.status_code == 400

    @patch("routes.metrics.metrics_service")
    def test_returns_400_for_invalid_date(self, mock_svc, client):
        """Should return 400 for invalid date format."""
        response = client.get("/api/metrics/csv?date=bad-date")

        assert response.status_code == 400


class TestTradesCsvApi:
    """Tests for GET /api/trades/csv."""

    @patch("routes.metrics.metrics_service")
    def test_returns_trades_data(self, mock_svc, client):
        """Should return trades CSV data as JSON."""
        mock_svc.get_trades_csv.return_value = [
            {"timestamp": "2026-02-14T10:00:00Z", "event": "ORDER_SENT", "side": "BUY"},
        ]

        response = client.get("/api/trades/csv?date=2026-02-14")

        assert response.status_code == 200
        data = response.get_json()
        assert data["type"] == "trades"
        assert len(data["rows"]) == 1
        assert data["rows"][0]["event"] == "ORDER_SENT"

    @patch("routes.metrics.metrics_service")
    def test_returns_404_for_missing_data(self, mock_svc, client):
        """Should return 404 when trades CSV doesn't exist."""
        mock_svc.get_trades_csv.return_value = None

        response = client.get("/api/trades/csv?date=2026-02-14")

        assert response.status_code == 404


class TestAvailableDatesApi:
    """Tests for GET /api/metrics/dates."""

    @patch("routes.metrics.metrics_service")
    def test_returns_available_dates(self, mock_svc, client):
        """Should return list of available dates."""
        mock_svc.list_available_dates.return_value = ["2026-02-12", "2026-02-13", "2026-02-14"]

        response = client.get("/api/metrics/dates?type=metrics")

        assert response.status_code == 200
        data = response.get_json()
        assert data["dates"] == ["2026-02-12", "2026-02-13", "2026-02-14"]
        assert data["type"] == "metrics"

    @patch("routes.metrics.metrics_service")
    def test_defaults_to_metrics(self, mock_svc, client):
        """Should default to metrics type when not specified."""
        mock_svc.list_available_dates.return_value = []

        client.get("/api/metrics/dates")

        mock_svc.list_available_dates.assert_called_once_with("metrics")

    @patch("routes.metrics.metrics_service")
    def test_accepts_trades_type(self, mock_svc, client):
        """Should accept trades type parameter."""
        mock_svc.list_available_dates.return_value = ["2026-02-14"]

        response = client.get("/api/metrics/dates?type=trades")

        assert response.status_code == 200
        mock_svc.list_available_dates.assert_called_once_with("trades")

    def test_rejects_invalid_type(self, client):
        """Should return 400 for invalid csv type."""
        response = client.get("/api/metrics/dates?type=invalid")

        assert response.status_code == 400
