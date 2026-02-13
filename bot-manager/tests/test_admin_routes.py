"""Tests for admin API routes."""
import base64
from unittest.mock import patch, MagicMock

import pytest

from config import TestConfig


def _auth_header(username="admin", password="testpass123"):
    """Create Basic Auth header."""
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def auth_app():
    """Create application with auth enabled for testing."""
    from app import create_app
    test_config = TestConfig()
    test_config.WTF_CSRF_ENABLED = False
    test_config.BASIC_AUTH_USERNAME = "admin"
    test_config.BASIC_AUTH_PASSWORD = "testpass123"
    flask_app = create_app(test_config)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def auth_client(auth_app):
    """Create authenticated test client."""
    return auth_app.test_client()


class TestResetPassword:
    """Tests for /api/admin/reset-password endpoint."""

    def test_requires_auth(self, auth_client):
        """Should return 401 without credentials."""
        response = auth_client.post(
            "/api/admin/reset-password",
            json={"new_password": "NewPass123"},
        )
        assert response.status_code == 401

    def test_missing_password_returns_400(self, auth_client):
        """Should reject request without new_password."""
        response = auth_client.post(
            "/api/admin/reset-password",
            json={},
            headers=_auth_header(),
        )
        assert response.status_code == 400
        assert "new_password is required" in response.get_json()["error"]

    def test_short_password_returns_400(self, auth_client):
        """Should reject passwords shorter than 8 characters."""
        response = auth_client.post(
            "/api/admin/reset-password",
            json={"new_password": "short"},
            headers=_auth_header(),
        )
        assert response.status_code == 400
        assert "at least 8" in response.get_json()["error"]

    def test_invalid_chars_returns_400(self, auth_client):
        """Should reject passwords with control characters."""
        response = auth_client.post(
            "/api/admin/reset-password",
            json={"new_password": "pass\x00word1"},
            headers=_auth_header(),
        )
        assert response.status_code == 400
        assert "invalid characters" in response.get_json()["error"]

    def test_first_call_returns_confirm_token(self, auth_client):
        """First call should return a confirmation token."""
        response = auth_client.post(
            "/api/admin/reset-password",
            json={"new_password": "NewPassword123"},
            headers=_auth_header(),
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["confirm_required"] is True
        assert "confirm_token" in data

    @patch("routes.admin.reset_os_password")
    def test_second_call_with_token_executes(self, mock_reset, auth_client):
        """Second call with valid token should execute reset."""
        mock_reset.return_value = MagicMock(
            success=True, output="Command completed", error=None
        )
        # Step 1: get token
        resp1 = auth_client.post(
            "/api/admin/reset-password",
            json={"new_password": "NewPassword123"},
            headers=_auth_header(),
        )
        token = resp1.get_json()["confirm_token"]

        # Step 2: confirm
        resp2 = auth_client.post(
            "/api/admin/reset-password",
            json={"new_password": "NewPassword123", "confirm_token": token},
            headers=_auth_header(),
        )
        assert resp2.status_code == 200
        assert resp2.get_json()["success"] is True
        mock_reset.assert_called_once_with("NewPassword123")

    def test_invalid_token_returns_403(self, auth_client):
        """Should reject invalid confirmation tokens."""
        response = auth_client.post(
            "/api/admin/reset-password",
            json={
                "new_password": "NewPassword123",
                "confirm_token": "bogus",
            },
            headers=_auth_header(),
        )
        assert response.status_code == 403

    @patch("routes.admin.reset_os_password")
    def test_token_consumed_after_use(self, mock_reset, auth_client):
        """Token should be consumed and not reusable."""
        mock_reset.return_value = MagicMock(
            success=True, output="OK", error=None
        )
        # Get and use token
        resp1 = auth_client.post(
            "/api/admin/reset-password",
            json={"new_password": "NewPassword123"},
            headers=_auth_header(),
        )
        token = resp1.get_json()["confirm_token"]
        auth_client.post(
            "/api/admin/reset-password",
            json={"new_password": "NewPassword123", "confirm_token": token},
            headers=_auth_header(),
        )

        # Reuse same token
        resp2 = auth_client.post(
            "/api/admin/reset-password",
            json={"new_password": "NewPassword123", "confirm_token": token},
            headers=_auth_header(),
        )
        assert resp2.status_code == 403


class TestSelfUpdate:
    """Tests for /api/admin/self-update endpoint."""

    def test_requires_auth(self, auth_client):
        """Should return 401 without credentials."""
        response = auth_client.post("/api/admin/self-update")
        assert response.status_code == 401

    @patch("routes.admin.self_update")
    def test_success(self, mock_update, auth_client):
        """Should return success on successful update."""
        mock_update.return_value = MagicMock(
            success=True,
            output="git pull: Already up to date.\npip install: OK",
            error=None,
        )
        response = auth_client.post(
            "/api/admin/self-update",
            json={},
            headers=_auth_header(),
        )
        assert response.status_code == 200
        assert response.get_json()["success"] is True

    @patch("routes.admin.restart_bot_manager")
    @patch("routes.admin.self_update")
    def test_restart_scheduled(self, mock_update, mock_restart, auth_client):
        """Should schedule restart when requested."""
        mock_update.return_value = MagicMock(
            success=True, output="OK", error=None
        )
        response = auth_client.post(
            "/api/admin/self-update",
            json={"restart": True},
            headers=_auth_header(),
        )
        data = response.get_json()
        assert data["restart_scheduled"] is True

    @patch("routes.admin.self_update")
    def test_failure(self, mock_update, auth_client):
        """Should return 500 on failure."""
        mock_update.return_value = MagicMock(
            success=False, output="", error="git pull failed"
        )
        response = auth_client.post(
            "/api/admin/self-update",
            json={},
            headers=_auth_header(),
        )
        assert response.status_code == 500


class TestDeploy:
    """Tests for /api/admin/deploy endpoint."""

    def test_requires_auth(self, auth_client):
        """Should return 401 without credentials."""
        response = auth_client.post("/api/admin/deploy")
        assert response.status_code == 401

    @patch("routes.admin.run_deploy")
    def test_success(self, mock_deploy, auth_client):
        """Should return success on successful deploy."""
        mock_deploy.return_value = MagicMock(
            success=True, output="Deployed v1.0.0", error=None
        )
        response = auth_client.post(
            "/api/admin/deploy",
            json={},
            headers=_auth_header(),
        )
        assert response.status_code == 200
        assert response.get_json()["success"] is True

    @patch("routes.admin.run_deploy")
    def test_failure(self, mock_deploy, auth_client):
        """Should return 500 on failure."""
        mock_deploy.return_value = MagicMock(
            success=False, output="", error="Script not found"
        )
        response = auth_client.post(
            "/api/admin/deploy",
            json={},
            headers=_auth_header(),
        )
        assert response.status_code == 500
