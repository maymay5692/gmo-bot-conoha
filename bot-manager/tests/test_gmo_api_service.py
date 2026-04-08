"""Tests for GMO API service."""
import pytest
from unittest.mock import patch, MagicMock

from services.gmo_api_service import (
    _create_sign,
    _handle_response,
    fetch_executions_for_date,
    get_account_margin,
    get_latest_executions,
    GmoApiError,
    summarize_executions,
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


def _make_execution(
    ts: str, settle: str = "CLOSE", loss_gain: str = "0", fee: str = "0"
) -> dict:
    return {
        "executionId": 1,
        "orderId": 1,
        "symbol": "BTC_JPY",
        "side": "BUY",
        "settleType": settle,
        "size": "0.001",
        "price": "11000000",
        "lossGain": loss_gain,
        "fee": fee,
        "timestamp": ts,
    }


def _api_response(rows: list) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "status": 0,
        "data": {"pagination": {"currentPage": 1, "count": 100}, "list": rows},
        "responsetime": "2026-01-01T00:00:00.000Z",
    }
    return resp


class TestGetLatestExecutions:
    """Tests for get_latest_executions wrapper."""

    @patch("services.gmo_api_service.requests.get")
    @patch("services.gmo_api_service._get_credentials")
    def test_returns_data_dict(self, mock_creds, mock_get):
        mock_creds.return_value = ("k", "s")
        mock_get.return_value = _api_response(
            [_make_execution("2026-04-08T10:00:00.000Z")]
        )
        result = get_latest_executions(symbol="BTC_JPY", page=1, count=100)
        assert "list" in result
        assert len(result["list"]) == 1

    def test_invalid_count_raises(self):
        with pytest.raises(ValueError):
            get_latest_executions(count=0)
        with pytest.raises(ValueError):
            get_latest_executions(count=101)

    def test_invalid_page_raises(self):
        with pytest.raises(ValueError):
            get_latest_executions(page=0)


class TestFetchExecutionsForDate:
    """Tests for date-based pagination helper."""

    @patch("services.gmo_api_service.get_latest_executions")
    def test_collects_only_target_date_jst(self, mock_get):
        # JST 2026-04-08 == UTC 2026-04-07 15:00 .. 2026-04-08 15:00
        page1 = {
            "list": [
                _make_execution("2026-04-08T20:00:00.000Z"),  # JST 4/9 — skip
                _make_execution(
                    "2026-04-08T10:00:00.000Z", loss_gain="50"
                ),  # JST 4/8 19:00 — keep
                _make_execution(
                    "2026-04-07T18:00:00.000Z", loss_gain="30"
                ),  # JST 4/8 03:00 — keep
                _make_execution(
                    "2026-04-07T10:00:00.000Z", loss_gain="999"
                ),  # JST 4/7 — stop
            ]
        }
        mock_get.return_value = page1

        result = fetch_executions_for_date("2026-04-08", max_pages=5)

        assert result["total"] == 2
        assert result["complete"] is True
        assert result["pages_fetched"] == 1
        # Chronological order (oldest first)
        assert result["executions"][0]["lossGain"] == "30"
        assert result["executions"][1]["lossGain"] == "50"

    @patch("services.gmo_api_service.get_latest_executions")
    def test_paginates_until_older_found(self, mock_get):
        page1 = {"list": [_make_execution("2026-04-08T23:00:00.000Z")]}
        page2 = {
            "list": [
                _make_execution("2026-04-08T20:00:00.000Z"),  # JST 4/9 — skip (new)
                _make_execution(
                    "2026-04-08T05:00:00.000Z", loss_gain="100"
                ),  # JST 4/8 14:00 — keep
                _make_execution(
                    "2026-04-07T00:00:00.000Z"
                ),  # JST 4/7 — stop
            ]
        }
        mock_get.side_effect = [page1, page2]

        result = fetch_executions_for_date("2026-04-08", max_pages=5)

        assert result["pages_fetched"] == 2
        assert result["complete"] is True
        # page1 execution: 2026-04-08T23 UTC = JST 2026-04-09 08 → skip
        # page2 keeper: one execution kept
        assert result["total"] == 1
        assert result["executions"][0]["lossGain"] == "100"

    @patch("services.gmo_api_service.get_latest_executions")
    def test_empty_list_marks_complete(self, mock_get):
        mock_get.return_value = {"list": []}
        result = fetch_executions_for_date("2026-04-08", max_pages=5)
        assert result["complete"] is True
        assert result["total"] == 0
        assert result["pages_fetched"] == 1

    @patch("services.gmo_api_service.get_latest_executions")
    def test_max_pages_cap_marks_incomplete(self, mock_get):
        # All executions on the target day, never hit an older one
        mock_get.return_value = {
            "list": [_make_execution("2026-04-08T10:00:00.000Z")]
        }
        result = fetch_executions_for_date("2026-04-08", max_pages=3)
        assert result["complete"] is False
        assert result["pages_fetched"] == 3


class TestSummarizeExecutions:
    """Tests for summarize_executions aggregation."""

    def test_empty_list(self):
        result = summarize_executions([])
        assert result == {
            "total_fills": 0,
            "open_fills": 0,
            "close_fills": 0,
            "realized_pnl": 0.0,
            "total_fee": 0.0,
            "net_pnl": 0.0,
        }

    def test_mixed_fills(self):
        execs = [
            _make_execution("ts", settle="OPEN", loss_gain="0", fee="1"),
            _make_execution("ts", settle="CLOSE", loss_gain="50", fee="2"),
            _make_execution("ts", settle="CLOSE", loss_gain="-20", fee="1"),
        ]
        result = summarize_executions(execs)
        assert result["total_fills"] == 3
        assert result["open_fills"] == 1
        assert result["close_fills"] == 2
        assert result["realized_pnl"] == 30.0
        assert result["total_fee"] == 4.0
        assert result["net_pnl"] == 26.0

    def test_handles_missing_fields(self):
        execs = [
            {"settleType": "CLOSE"},  # no lossGain, no fee
            {"settleType": "OPEN", "lossGain": "bogus", "fee": "bogus"},
        ]
        result = summarize_executions(execs)
        assert result["total_fills"] == 2
        assert result["close_fills"] == 1
        assert result["open_fills"] == 1
        assert result["realized_pnl"] == 0.0
        assert result["total_fee"] == 0.0
