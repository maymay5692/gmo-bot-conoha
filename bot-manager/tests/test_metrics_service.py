"""Tests for metrics CSV reading service."""
import os
import tempfile

import pytest

from services import metrics_service


METRICS_HEADER = "timestamp,mid_price,best_bid,best_ask,spread,volatility,best_ev,buy_spread_pct,sell_spread_pct,long_size,short_size,collateral,buy_prob_avg,sell_prob_avg\n"
TRADES_HEADER = "timestamp,event,order_id,side,price,size,is_close,error\n"


@pytest.fixture(autouse=True)
def setup_metrics_service():
    """Set up metrics service with temp log directory for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        metrics_service.init(tmpdir)
        yield tmpdir


class TestGetMetricsCsv:
    """Tests for get_metrics_csv."""

    def test_returns_none_for_invalid_date(self, setup_metrics_service):
        """Should return None for invalid date format."""
        assert metrics_service.get_metrics_csv("not-a-date") is None
        assert metrics_service.get_metrics_csv("2026/02/14") is None
        assert metrics_service.get_metrics_csv("") is None

    def test_returns_none_for_missing_file(self, setup_metrics_service):
        """Should return None when CSV file doesn't exist."""
        result = metrics_service.get_metrics_csv("2026-02-14")
        assert result is None

    def test_reads_metrics_csv(self, setup_metrics_service):
        """Should parse metrics CSV and return list of dicts."""
        tmpdir = setup_metrics_service
        metrics_dir = os.path.join(tmpdir, "metrics")
        os.makedirs(metrics_dir)

        csv_path = os.path.join(metrics_dir, "metrics-2026-02-14.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(METRICS_HEADER)
            f.write("2026-02-14T10:00:00Z,6500000,6499000,6501000,2000,1500,0.00123,0.077,0.077,0.001,0.0,100000,0.45,0.52\n")
            f.write("2026-02-14T10:00:10Z,6501000,6500000,6502000,2000,1200,0.00150,0.080,0.075,0.001,0.001,100000,0.48,0.50\n")

        result = metrics_service.get_metrics_csv("2026-02-14")

        assert result is not None
        assert len(result) == 2
        assert result[0]["mid_price"] == "6500000"
        assert result[0]["buy_prob_avg"] == "0.45"
        assert result[1]["sell_prob_avg"] == "0.50"

    def test_returns_empty_list_for_header_only(self, setup_metrics_service):
        """Should return empty list when CSV has only header."""
        tmpdir = setup_metrics_service
        metrics_dir = os.path.join(tmpdir, "metrics")
        os.makedirs(metrics_dir)

        csv_path = os.path.join(metrics_dir, "metrics-2026-02-14.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(METRICS_HEADER)

        result = metrics_service.get_metrics_csv("2026-02-14")

        assert result is not None
        assert result == []

    def test_handles_corrupted_csv(self, setup_metrics_service):
        """Should not crash on corrupted CSV data."""
        tmpdir = setup_metrics_service
        metrics_dir = os.path.join(tmpdir, "metrics")
        os.makedirs(metrics_dir)

        csv_path = os.path.join(metrics_dir, "metrics-2026-02-14.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("\x00\x01\x02binary garbage")

        result = metrics_service.get_metrics_csv("2026-02-14")

        assert isinstance(result, (list, type(None)))

    def test_rejects_path_traversal_attempts(self, setup_metrics_service):
        """Should reject dates containing path traversal sequences."""
        assert metrics_service.get_metrics_csv("../../etc/passwd") is None
        assert metrics_service.get_metrics_csv("2026-02-14/../../etc") is None
        assert metrics_service.get_metrics_csv("..\\..\\windows\\system32") is None
        assert metrics_service.get_metrics_csv("2026-02-14\x00.csv") is None


class TestGetTradesCsv:
    """Tests for get_trades_csv."""

    def test_returns_none_for_invalid_date(self, setup_metrics_service):
        """Should return None for invalid date format."""
        assert metrics_service.get_trades_csv("bad-date") is None

    def test_returns_none_for_missing_file(self, setup_metrics_service):
        """Should return None when CSV file doesn't exist."""
        result = metrics_service.get_trades_csv("2026-02-14")
        assert result is None

    def test_reads_trades_csv(self, setup_metrics_service):
        """Should parse trades CSV and return list of dicts."""
        tmpdir = setup_metrics_service
        trades_dir = os.path.join(tmpdir, "trades")
        os.makedirs(trades_dir)

        csv_path = os.path.join(trades_dir, "trades-2026-02-14.csv")
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(TRADES_HEADER)
            f.write("2026-02-14T10:00:00Z,ORDER_SENT,123456,BUY,6500000,0.001,false,\n")
            f.write("2026-02-14T10:00:05Z,ORDER_FILLED,123456,BUY,6500000,0.001,,\n")
            f.write("2026-02-14T10:00:10Z,ORDER_SENT,123457,SELL,6501000,0.001,false,\n")

        result = metrics_service.get_trades_csv("2026-02-14")

        assert result is not None
        assert len(result) == 3
        assert result[0]["event"] == "ORDER_SENT"
        assert result[0]["side"] == "BUY"
        assert result[1]["event"] == "ORDER_FILLED"
        assert result[2]["price"] == "6501000"


class TestListAvailableDates:
    """Tests for list_available_dates."""

    def test_returns_empty_for_no_files(self, setup_metrics_service):
        """Should return empty list when no CSV files exist."""
        result = metrics_service.list_available_dates("metrics")
        assert result == []

    def test_lists_metrics_dates(self, setup_metrics_service):
        """Should list available dates from metrics directory."""
        tmpdir = setup_metrics_service
        metrics_dir = os.path.join(tmpdir, "metrics")
        os.makedirs(metrics_dir)

        # Create a few CSV files
        for date in ["2026-02-12", "2026-02-14", "2026-02-13"]:
            csv_path = os.path.join(metrics_dir, f"metrics-{date}.csv")
            with open(csv_path, "w") as f:
                f.write(METRICS_HEADER)

        result = metrics_service.list_available_dates("metrics")

        assert result == ["2026-02-12", "2026-02-13", "2026-02-14"]

    def test_lists_trades_dates(self, setup_metrics_service):
        """Should list available dates from trades directory."""
        tmpdir = setup_metrics_service
        trades_dir = os.path.join(tmpdir, "trades")
        os.makedirs(trades_dir)

        csv_path = os.path.join(trades_dir, "trades-2026-02-14.csv")
        with open(csv_path, "w") as f:
            f.write(TRADES_HEADER)

        result = metrics_service.list_available_dates("trades")

        assert result == ["2026-02-14"]

    def test_ignores_non_csv_files(self, setup_metrics_service):
        """Should ignore non-CSV files in directory."""
        tmpdir = setup_metrics_service
        metrics_dir = os.path.join(tmpdir, "metrics")
        os.makedirs(metrics_dir)

        # CSV file
        with open(os.path.join(metrics_dir, "metrics-2026-02-14.csv"), "w") as f:
            f.write(METRICS_HEADER)
        # Non-CSV file
        with open(os.path.join(metrics_dir, "notes.txt"), "w") as f:
            f.write("some notes")

        result = metrics_service.list_available_dates("metrics")

        assert result == ["2026-02-14"]

    def test_invalid_type_returns_empty(self, setup_metrics_service):
        """Should return empty list for invalid csv_type."""
        result = metrics_service.list_available_dates("invalid")
        assert result == []
