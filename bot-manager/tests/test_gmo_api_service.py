"""Tests for GMO API service."""
import pytest
from unittest.mock import patch, MagicMock

from services.gmo_api_service import (
    _create_sign,
    _handle_response,
    get_account_margin,
    GmoApiError,
)


class TestCreateSign:
    """Tests for HMAC signature creation."""

    def test_creates_hex_string(self):
        """Should return a hex-encoded HMAC-SHA256 signature."""
        sign = _create_sign("GET", "/v1/account/margin", "", "1234567890", "secret")
        assert isinstance(sign, str)
        assert len(sign) == 64  # SHA256 hex = 64 chars

    def test_different_inputs_different_signs(self):
        """Different inputs should produce different signatures."""
        sign1 = _create_sign("GET", "/v1/path1", "", "1000", "secret")
        sign2 = _create_sign("GET", "/v1/path2", "", "1000", "secret")
        assert sign1 != sign2


class TestHandleResponse:
    """Tests for API response handling."""

    def test_success_response(self):
        """Should return parsed data on success."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": 0,
            "data": {"availableAmount": "50000"},
            "responsetime": "2026-01-01T00:00:00.000Z",
        }

        result = _handle_response(mock_resp)

        assert result["data"]["availableAmount"] == "50000"

    def test_error_response_raises(self):
        """Should raise GmoApiError on non-zero status."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": 1,
            "messages": [
                {"message_code": "ERR-201", "message_string": "Insufficient margin"}
            ],
        }

        with pytest.raises(GmoApiError) as exc_info:
            _handle_response(mock_resp)

        assert "ERR-201" in str(exc_info.value)

    def test_http_error_raises(self):
        """Should propagate HTTP errors."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("500 Server Error")

        with pytest.raises(Exception, match="500 Server Error"):
            _handle_response(mock_resp)


class TestGetAccountMargin:
    """Tests for get_account_margin."""

    @patch("services.gmo_api_service.requests.get")
    @patch("services.gmo_api_service._get_credentials")
    def test_returns_data(self, mock_creds, mock_get):
        """Should return margin data dict."""
        mock_creds.return_value = ("test-key", "test-secret")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": 0,
            "data": {
                "actualProfitLoss": "50000",
                "availableAmount": "40000",
                "margin": "10000",
                "profitLoss": "500",
            },
            "responsetime": "2026-01-01T00:00:00.000Z",
        }
        mock_get.return_value = mock_resp

        result = get_account_margin()

        assert result["actualProfitLoss"] == "50000"
        assert result["availableAmount"] == "40000"

    @patch("services.gmo_api_service._get_credentials")
    def test_missing_credentials_raises(self, mock_creds):
        """Should raise when credentials are missing."""
        mock_creds.return_value = ("", "")

        with pytest.raises(GmoApiError):
            get_account_margin()
