"""Tests for /api/gmo/executions route."""
import base64
from unittest.mock import patch

import pytest

from config import TestConfig


def _auth_header(username="admin", password="testpass123"):
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def auth_client():
    from app import create_app
    cfg = TestConfig()
    cfg.WTF_CSRF_ENABLED = False
    cfg.BASIC_AUTH_USERNAME = "admin"
    cfg.BASIC_AUTH_PASSWORD = "testpass123"
    app = create_app(cfg)
    app.config["TESTING"] = True
    return app.test_client()


class TestGmoExecutionsRoute:
    def test_requires_auth(self, auth_client):
        resp = auth_client.get("/api/gmo/executions?date=2026-04-08")
        assert resp.status_code == 401

    def test_missing_date_returns_400(self, auth_client):
        resp = auth_client.get(
            "/api/gmo/executions", headers=_auth_header()
        )
        assert resp.status_code == 400

    def test_invalid_date_format_returns_400(self, auth_client):
        resp = auth_client.get(
            "/api/gmo/executions?date=2026/04/08",
            headers=_auth_header(),
        )
        assert resp.status_code == 400

    def test_invalid_symbol_returns_400(self, auth_client):
        resp = auth_client.get(
            "/api/gmo/executions?date=2026-04-08&symbol=bad-symbol!",
            headers=_auth_header(),
        )
        assert resp.status_code == 400

    def test_invalid_max_pages_returns_400(self, auth_client):
        resp = auth_client.get(
            "/api/gmo/executions?date=2026-04-08&max_pages=0",
            headers=_auth_header(),
        )
        assert resp.status_code == 400

    @patch("routes.gmo_history.fetch_executions_for_date")
    def test_success_returns_summary(self, mock_fetch, auth_client):
        mock_fetch.return_value = {
            "date": "2026-04-08",
            "executions": [
                {
                    "settleType": "CLOSE",
                    "lossGain": "100",
                    "fee": "5",
                    "timestamp": "2026-04-08T01:00:00.000Z",
                },
                {
                    "settleType": "OPEN",
                    "lossGain": "0",
                    "fee": "2",
                    "timestamp": "2026-04-08T02:00:00.000Z",
                },
            ],
            "total": 2,
            "pages_fetched": 1,
            "complete": True,
        }
        resp = auth_client.get(
            "/api/gmo/executions?date=2026-04-08",
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["total"] == 2
        assert body["symbol"] == "BTC_JPY"
        assert body["summary"]["realized_pnl"] == 100.0
        assert body["summary"]["total_fee"] == 7.0
        assert body["summary"]["net_pnl"] == 93.0
        assert body["summary"]["close_fills"] == 1
        assert body["summary"]["open_fills"] == 1

    @patch("routes.gmo_history.fetch_executions_for_date")
    def test_gmo_api_error_returns_502(self, mock_fetch, auth_client):
        from services.gmo_api_service import GmoApiError
        mock_fetch.side_effect = GmoApiError(1, [
            {"message_code": "ERR-XXX", "message_string": "boom"}
        ])
        resp = auth_client.get(
            "/api/gmo/executions?date=2026-04-08",
            headers=_auth_header(),
        )
        assert resp.status_code == 502
