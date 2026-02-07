"""Tests for P&L service."""
import json
import os
import tempfile

import pytest
from unittest.mock import patch

from services import pnl_service


@pytest.fixture(autouse=True)
def setup_pnl_service():
    """Set up P&L service with temp directory for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        pnl_service.init(tmpdir)
        pnl_service._last_snapshot_time = 0.0
        yield tmpdir


class TestSnapshotPersistence:
    """Tests for snapshot save/load."""

    def test_load_empty(self, setup_pnl_service):
        """Should return empty list when no data file."""
        snapshots = pnl_service._load_snapshots()
        assert snapshots == []

    def test_save_and_load(self, setup_pnl_service):
        """Should persist snapshots to JSON."""
        data = [
            {"timestamp": "2026-01-01 00:00:00", "actual_profit_loss": "50000"},
        ]
        pnl_service._save_snapshots(data)

        loaded = pnl_service._load_snapshots()
        assert len(loaded) == 1
        assert loaded[0]["actual_profit_loss"] == "50000"

    def test_save_trims_to_max(self, setup_pnl_service):
        """Should trim snapshots to MAX_SNAPSHOTS."""
        data = [{"timestamp": f"2026-01-01 00:{i:02d}:00"} for i in range(3000)]
        pnl_service._save_snapshots(data)

        loaded = pnl_service._load_snapshots()
        assert len(loaded) == pnl_service.MAX_SNAPSHOTS

    def test_load_corrupted_file(self, setup_pnl_service):
        """Should return empty list on corrupted JSON."""
        path = pnl_service._get_data_path()
        with open(path, "w") as f:
            f.write("not valid json")

        snapshots = pnl_service._load_snapshots()
        assert snapshots == []


class TestTakeSnapshot:
    """Tests for take_snapshot."""

    @patch("services.pnl_service.get_account_margin")
    def test_takes_snapshot(self, mock_margin, setup_pnl_service):
        """Should save a snapshot when interval has passed."""
        mock_margin.return_value = {
            "actualProfitLoss": "50000",
            "availableAmount": "40000",
            "profitLoss": "500",
            "margin": "10000",
        }

        result = pnl_service.take_snapshot()

        assert result is not None
        assert result["actual_profit_loss"] == "50000"

        snapshots = pnl_service._load_snapshots()
        assert len(snapshots) == 1

    @patch("services.pnl_service.get_account_margin")
    def test_skips_within_interval(self, mock_margin, setup_pnl_service):
        """Should skip if called within 5-minute interval."""
        mock_margin.return_value = {
            "actualProfitLoss": "50000",
            "availableAmount": "40000",
            "profitLoss": "500",
            "margin": "10000",
        }

        pnl_service.take_snapshot()
        result = pnl_service.take_snapshot()

        assert result is None
        assert len(pnl_service._load_snapshots()) == 1

    @patch("services.pnl_service.get_account_margin")
    def test_handles_api_error(self, mock_margin, setup_pnl_service):
        """Should return None on API error."""
        from services.gmo_api_service import GmoApiError
        mock_margin.side_effect = GmoApiError(1, [{"message_code": "ERR", "message_string": "API error"}])

        result = pnl_service.take_snapshot()

        assert result is None
        assert len(pnl_service._load_snapshots()) == 0


class TestGetChartData:
    """Tests for get_chart_data."""

    def test_empty_data(self, setup_pnl_service):
        """Should return empty arrays when no snapshots."""
        data = pnl_service.get_chart_data(hours=24)
        assert data["labels"] == []
        assert data["actual_profit_loss"] == []
        assert data["unrealized_profit_loss"] == []

    def test_returns_chart_format(self, setup_pnl_service):
        """Should format data for Chart.js."""
        snapshots = [
            {
                "timestamp": "2099-01-01 00:00:00",
                "actual_profit_loss": "50000",
                "profit_loss": "500",
            },
            {
                "timestamp": "2099-01-01 00:05:00",
                "actual_profit_loss": "50100",
                "profit_loss": "600",
            },
        ]
        pnl_service._save_snapshots(snapshots)

        data = pnl_service.get_chart_data(hours=24)

        assert len(data["labels"]) == 2
        assert data["actual_profit_loss"] == [50000.0, 50100.0]
        assert data["unrealized_profit_loss"] == [500.0, 600.0]


class TestGetCurrentPnl:
    """Tests for get_current_pnl."""

    @patch("services.pnl_service.get_account_margin")
    def test_returns_current(self, mock_margin):
        """Should return current P&L data."""
        mock_margin.return_value = {
            "actualProfitLoss": "50000",
            "availableAmount": "40000",
            "profitLoss": "500",
            "margin": "10000",
        }

        result = pnl_service.get_current_pnl()

        assert result["actual_profit_loss"] == "50000"
        assert result["profit_loss"] == "500"

    @patch("services.pnl_service.get_account_margin")
    def test_returns_none_on_error(self, mock_margin):
        """Should return None on API error."""
        from services.gmo_api_service import GmoApiError
        mock_margin.side_effect = GmoApiError(1, [{"message_code": "ERR", "message_string": "API error"}])

        result = pnl_service.get_current_pnl()

        assert result is None
