"""Tests for verify_version.py - G category, D11, J level analysis, and phase judgment."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from verify_version import (
    calc_stop_loss_detail,
    calc_trips,
    calc_level_analysis,
    compute_all,
    print_phase_judgment,
    _check,
    build_trips,
)


# ============================================================
# Test helpers: trade event factories
# ============================================================

def _sl_event(unrealized_pnl: float, ts: str = "2026-02-22T12:00:00") -> dict:
    return {
        "timestamp": ts,
        "event": "STOP_LOSS_TRIGGERED",
        "side": "BUY",
        "price": "14000000",
        "size": "0.001",
        "is_close": "true",
        "error": f"unrealized_pnl={unrealized_pnl:.3f}",
        "mid_price": "14000000",
    }


def _order_sent(side: str = "BUY", is_close: str = "false",
                ts: str = "2026-02-22T12:00:00",
                order_id: str = "", level: str = "",
                p_fill: str = "") -> dict:
    return {
        "timestamp": ts,
        "event": "ORDER_SENT",
        "order_id": order_id,
        "side": side,
        "price": "14000000",
        "size": "0.001",
        "is_close": is_close,
        "error": "",
        "mid_price": "14000000",
        "level": level,
        "p_fill": p_fill,
    }


def _order_filled(side: str = "BUY", is_close: str = "false",
                  price: str = "14000000", mid_price: str = "14000050",
                  ts: str = "2026-02-22T12:00:00",
                  order_id: str = "", level: str = "",
                  order_age_ms: str = "") -> dict:
    return {
        "timestamp": ts,
        "event": "ORDER_FILLED",
        "order_id": order_id,
        "side": side,
        "price": price,
        "size": "0.001",
        "is_close": is_close,
        "error": "",
        "mid_price": mid_price,
        "level": level,
        "order_age_ms": order_age_ms,
    }


def _order_cancelled(order_id: str = "", level: str = "",
                     order_age_ms: str = "",
                     ts: str = "2026-02-22T12:00:00") -> dict:
    return {
        "timestamp": ts,
        "event": "ORDER_CANCELLED",
        "order_id": order_id,
        "level": level,
        "order_age_ms": order_age_ms,
    }


# ============================================================
# G. calc_stop_loss_detail tests
# ============================================================

class TestCalcStopLossDetail:
    """Test G1-G6 stop-loss metrics."""

    def test_empty_trades_returns_defaults(self):
        result = calc_stop_loss_detail([], uptime_hours=10, completed_trips=100,
                                       pnl_per_trip=-0.5, sl_total_jpy=-100)
        assert result["G1_sl_count_per_hour"] == 0
        assert result["G2_sl_loss_per_event"] == 0
        assert result["G3_sl_impact_per_trip"] == 0
        assert result["G4_pnl_ex_sl_per_trip"] == 0
        assert result["G5_sl_recovery_trips"] == -1
        assert result["G6_max_sl_loss"] == 0

    def test_no_sl_events_in_trades(self):
        trades = [_order_sent(), _order_filled()]
        result = calc_stop_loss_detail(trades, uptime_hours=10, completed_trips=100,
                                       pnl_per_trip=-0.5, sl_total_jpy=0)
        assert result["G1_sl_count_per_hour"] == 0
        assert result["G2_sl_loss_per_event"] == 0
        assert result["G3_sl_impact_per_trip"] == 0
        # G4 = pnl_per_trip - G3 = -0.5 - 0 = -0.5
        assert result["G4_pnl_ex_sl_per_trip"] == -0.5
        assert result["G5_sl_recovery_trips"] == -1  # G4 < 0

    def test_basic_sl_calculations(self):
        """v0.12.1-like scenario: 11 SL events, 11.72h, 196 trips."""
        trades = [_sl_event(-20.0, f"2026-02-22T{i:02d}:00:00") for i in range(11)]
        result = calc_stop_loss_detail(
            trades,
            uptime_hours=11.72,
            completed_trips=196,
            pnl_per_trip=-0.66,
            sl_total_jpy=-220.0,
        )
        # G1: 11 / 11.72 = 0.9386
        assert abs(result["G1_sl_count_per_hour"] - 11 / 11.72) < 0.001
        # G2: -220 / 11 = -20.0
        assert result["G2_sl_loss_per_event"] == -20.0
        # G3: -220 / 196 = -1.1224
        assert abs(result["G3_sl_impact_per_trip"] - (-220.0 / 196)) < 0.001
        # G4: -0.66 - (-1.1224) = +0.4624
        assert result["G4_pnl_ex_sl_per_trip"] > 0.4
        # G5: abs(-20) / G4 > 0 -> recovery trips
        assert result["G5_sl_recovery_trips"] > 0
        # G6: min(-20, -20, ...) = -20
        assert result["G6_max_sl_loss"] == -20.0

    def test_g6_picks_worst_loss(self):
        trades = [
            _sl_event(-5.0),
            _sl_event(-30.0),
            _sl_event(-10.0),
        ]
        result = calc_stop_loss_detail(
            trades, uptime_hours=1, completed_trips=10,
            pnl_per_trip=1.0, sl_total_jpy=-45.0,
        )
        assert result["G6_max_sl_loss"] == -30.0

    def test_g5_negative_when_g4_too_small(self):
        """G5 should be -1 when G4 <= 0.01 (near-zero or negative)."""
        trades = [_sl_event(-10.0)]
        result = calc_stop_loss_detail(
            trades, uptime_hours=1, completed_trips=10,
            pnl_per_trip=-0.99, sl_total_jpy=-10.0,
        )
        # G3 = -10/10 = -1.0, G4 = -0.99 - (-1.0) = 0.01 -> not > 0.01
        assert result["G5_sl_recovery_trips"] == -1

    def test_g5_positive_when_g4_profitable(self):
        trades = [_sl_event(-50.0)]
        result = calc_stop_loss_detail(
            trades, uptime_hours=10, completed_trips=100,
            pnl_per_trip=0.5, sl_total_jpy=-50.0,
        )
        # G3 = -50/100 = -0.5, G4 = 0.5 - (-0.5) = 1.0
        # G5 = abs(-50) / 1.0 = 50.0
        assert result["G5_sl_recovery_trips"] == 50.0

    def test_zero_uptime_hours(self):
        trades = [_sl_event(-10.0)]
        result = calc_stop_loss_detail(
            trades, uptime_hours=0, completed_trips=10,
            pnl_per_trip=-0.5, sl_total_jpy=-10.0,
        )
        assert result["G1_sl_count_per_hour"] == 0

    def test_zero_completed_trips(self):
        trades = [_sl_event(-10.0)]
        result = calc_stop_loss_detail(
            trades, uptime_hours=1, completed_trips=0,
            pnl_per_trip=0, sl_total_jpy=-10.0,
        )
        assert result["G3_sl_impact_per_trip"] == 0

    def test_sl_event_without_unrealized_pnl_in_error(self):
        """SL event with malformed error field should be skipped."""
        trades = [
            {
                "timestamp": "2026-02-22T12:00:00",
                "event": "STOP_LOSS_TRIGGERED",
                "side": "BUY",
                "error": "some_other_error",
                "mid_price": "14000000",
            },
            _sl_event(-10.0),
        ]
        result = calc_stop_loss_detail(
            trades, uptime_hours=1, completed_trips=10,
            pnl_per_trip=-0.5, sl_total_jpy=-10.0,
        )
        # Only 1 matched SL event (the one with proper unrealized_pnl)
        assert result["G1_sl_count_per_hour"] == 1.0
        assert result["G2_sl_loss_per_event"] == -10.0
        assert result["G6_max_sl_loss"] == -10.0


# ============================================================
# D11. trips_per_hour tests
# ============================================================

class TestD11TripsPerHour:
    """Test D11 metric in calc_trips."""

    def _make_round_trip(self, open_ts: str, close_ts: str) -> list[dict]:
        """Create a complete LONG round trip (BUY open -> SELL close)."""
        return [
            _order_filled("BUY", "false", "14000000", "14000050", open_ts),
            _order_filled("SELL", "true", "14000100", "14000050", close_ts),
        ]

    def test_d11_basic(self):
        trades = self._make_round_trip("2026-02-22T00:00:00", "2026-02-22T00:05:00")
        result = calc_trips(trades, uptime_hours=2.0)
        assert result["D1_completed_trips"] == 1
        assert result["D11_trips_per_hour"] == 0.5  # 1 trip / 2h

    def test_d11_zero_uptime(self):
        trades = self._make_round_trip("2026-02-22T00:00:00", "2026-02-22T00:05:00")
        result = calc_trips(trades, uptime_hours=0)
        assert result["D11_trips_per_hour"] == 0

    def test_d11_no_trips(self):
        result = calc_trips([], uptime_hours=10)
        assert result["D11_trips_per_hour"] == 0

    def test_d11_multiple_trips(self):
        trades = []
        for i in range(10):
            trades.extend(self._make_round_trip(
                f"2026-02-22T{i:02d}:00:00",
                f"2026-02-22T{i:02d}:05:00",
            ))
        result = calc_trips(trades, uptime_hours=5.0)
        assert result["D11_trips_per_hour"] == 2.0  # 10 trips / 5h

    def test_d11_default_uptime_backward_compat(self):
        """calc_trips without uptime_hours should still work (default=0)."""
        result = calc_trips([])
        assert result["D11_trips_per_hour"] == 0


# ============================================================
# compute_all integration tests
# ============================================================

class TestComputeAllGCategory:
    """Test G category integration in compute_all."""

    def test_g_category_present_in_output(self):
        result = compute_all([], [])
        assert "G_stop_loss_detail" in result

    def test_g_category_keys(self):
        result = compute_all([], [])
        g = result["G_stop_loss_detail"]
        expected_keys = [
            "G1_sl_count_per_hour",
            "G2_sl_loss_per_event",
            "G3_sl_impact_per_trip",
            "G4_pnl_ex_sl_per_trip",
            "G5_sl_recovery_trips",
            "G6_max_sl_loss",
        ]
        for key in expected_keys:
            assert key in g, f"Missing key: {key}"

    def test_g_with_sl_events(self):
        trades = [
            # Need timestamps spanning time for A1
            _order_sent("BUY", "false", "2026-02-22T00:00:00"),
            _order_filled("BUY", "false", "14000000", "14000050", "2026-02-22T00:01:00"),
            _order_filled("SELL", "true", "14000100", "14000050", "2026-02-22T00:06:00"),
            _sl_event(-15.0, "2026-02-22T01:00:00"),
        ]
        result = compute_all(trades, [])
        g = result["G_stop_loss_detail"]
        assert g["G1_sl_count_per_hour"] > 0
        assert g["G6_max_sl_loss"] == -15.0


# ============================================================
# _check helper tests
# ============================================================

class TestCheckHelper:
    """Test the _check judgment function."""

    def test_less_than_pass(self):
        result = _check("test", 0.5, "<", 1.0)
        assert "[PASS]" in result

    def test_less_than_fail(self):
        result = _check("test", 1.5, "<", 1.0)
        assert "[FAIL]" in result

    def test_greater_than_pass(self):
        result = _check("test", 1.5, ">", 1.0)
        assert "[PASS]" in result

    def test_greater_than_fail(self):
        result = _check("test", 0.5, ">", 1.0)
        assert "[FAIL]" in result

    def test_less_equal_pass(self):
        result = _check("test", 1.0, "<=", 1.0)
        assert "[PASS]" in result

    def test_greater_equal_pass(self):
        result = _check("test", 1.0, ">=", 1.0)
        assert "[PASS]" in result

    def test_unit_suffix(self):
        result = _check("test", 0.5, "<", 1.0, " JPY")
        assert "JPY" in result

    def test_exact_boundary_less_than(self):
        result = _check("test", 1.0, "<", 1.0)
        assert "[FAIL]" in result  # 1.0 is NOT < 1.0


# ============================================================
# print_phase_judgment smoke tests
# ============================================================

class TestPrintPhaseJudgment:
    """Test print_phase_judgment doesn't crash and outputs expected content."""

    def _make_result(self) -> dict:
        return compute_all([], [])

    def test_phase_3_0_no_crash(self, capsys):
        result = self._make_result()
        print_phase_judgment(result, "3-0")
        captured = capsys.readouterr()
        assert "Phase 3-0" in captured.out
        assert "Data sufficiency" in captured.out
        assert "Monitoring targets" in captured.out
        assert "Success criteria" in captured.out
        assert "Rollback triggers" in captured.out

    def test_phase_3_1_no_crash(self, capsys):
        result = self._make_result()
        print_phase_judgment(result, "3-1")
        captured = capsys.readouterr()
        assert "Phase 3-1" in captured.out

    def test_phase_3_2_no_crash(self, capsys):
        result = self._make_result()
        print_phase_judgment(result, "3-2")
        captured = capsys.readouterr()
        assert "Phase 3-2" in captured.out

    def test_unknown_phase(self, capsys):
        result = self._make_result()
        print_phase_judgment(result, "9-9")
        captured = capsys.readouterr()
        assert "Unknown phase" in captured.out

    def test_phase_3_0_with_real_data(self, capsys):
        """Phase 3-0 judgment with SL events should show PASS/FAIL correctly."""
        trades = [
            _order_sent("BUY", "false", "2026-02-22T00:00:00"),
            _order_filled("BUY", "false", "14000000", "14000050", "2026-02-22T00:01:00"),
            _order_filled("SELL", "true", "14000100", "14000050", "2026-02-22T00:06:00"),
            _sl_event(-15.0, "2026-02-22T01:00:00"),
        ]
        result = compute_all(trades, [])
        print_phase_judgment(result, "3-0")
        captured = capsys.readouterr()
        assert "PASS" in captured.out or "FAIL" in captured.out


# ============================================================
# J. Level Analysis tests
# ============================================================

class TestCalcLevelAnalysis:
    """Test J1-J4 level-based metrics."""

    def test_empty_trades(self):
        result = calc_level_analysis([])
        assert result["J1_levels_analyzed"] == 0
        assert result["J2_level_details"] == {}

    def test_no_level_data(self):
        """Old CSV format without level column should return empty."""
        trades = [
            _order_sent("BUY", "false"),
            _order_filled("BUY", "false"),
        ]
        result = calc_level_analysis(trades)
        assert result["J1_levels_analyzed"] == 0

    def test_single_level_all_filled(self):
        """All orders at level 5 filled."""
        trades = [
            _order_sent("BUY", "false", order_id="o1", level="5", p_fill="0.20"),
            _order_filled("BUY", "false", order_id="o1", level="5",
                          price="14000000", mid_price="14000050"),
            _order_sent("BUY", "false", order_id="o2", level="5", p_fill="0.25"),
            _order_filled("BUY", "false", order_id="o2", level="5",
                          price="14000000", mid_price="14000050"),
        ]
        result = calc_level_analysis(trades)
        assert result["J1_levels_analyzed"] == 1
        details = result["J2_level_details"]
        assert "5" in details
        lv5 = details["5"]
        assert lv5["sent"] == 2
        assert lv5["filled"] == 2
        assert lv5["fill_rate_pct"] == 100.0
        assert lv5["cancelled"] == 0

    def test_multi_level_mixed(self):
        """Multiple levels with mixed fill/cancel outcomes."""
        trades = [
            # Level 4: 3 sent, 1 filled, 2 cancelled
            _order_sent("BUY", "false", order_id="a1", level="4", p_fill="0.10"),
            _order_sent("BUY", "false", order_id="a2", level="4", p_fill="0.12"),
            _order_sent("BUY", "false", order_id="a3", level="4", p_fill="0.08"),
            _order_filled("BUY", "false", order_id="a1", level="4",
                          price="14000000", mid_price="14000050"),
            _order_cancelled(order_id="a2", level="4", order_age_ms="3000"),
            _order_cancelled(order_id="a3", level="4", order_age_ms="4500"),
            # Level 10: 2 sent, 0 filled, 2 cancelled
            _order_sent("SELL", "false", order_id="b1", level="10", p_fill="0.05"),
            _order_sent("SELL", "false", order_id="b2", level="10", p_fill="0.04"),
            _order_cancelled(order_id="b1", level="10", order_age_ms="8000"),
            _order_cancelled(order_id="b2", level="10", order_age_ms="9000"),
        ]
        result = calc_level_analysis(trades)
        assert result["J1_levels_analyzed"] == 2

        details = result["J2_level_details"]
        lv4 = details["4"]
        assert lv4["sent"] == 3
        assert lv4["filled"] == 1
        assert abs(lv4["fill_rate_pct"] - 33.33) < 0.1
        assert lv4["cancelled"] == 2
        assert abs(lv4["avg_predicted_pfill"] - 0.10) < 0.01

        lv10 = details["10"]
        assert lv10["sent"] == 2
        assert lv10["filled"] == 0
        assert lv10["fill_rate_pct"] == 0.0
        assert lv10["cancelled"] == 2

    def test_cancel_age_stats(self):
        """Cancel order_age_ms statistics per level."""
        trades = [
            _order_sent("BUY", "false", order_id="c1", level="6", p_fill="0.15"),
            _order_sent("BUY", "false", order_id="c2", level="6", p_fill="0.15"),
            _order_cancelled(order_id="c1", level="6", order_age_ms="2000"),
            _order_cancelled(order_id="c2", level="6", order_age_ms="4000"),
        ]
        result = calc_level_analysis(trades)
        lv6 = result["J2_level_details"]["6"]
        assert lv6["cancelled"] == 2
        assert lv6["avg_cancel_age_ms"] == 3000.0

    def test_compute_all_includes_j_category(self):
        """J category should be present in compute_all output."""
        result = compute_all([], [])
        assert "J_level_analysis" in result

    def test_close_orders_excluded(self):
        """Close orders should not be counted in level analysis."""
        trades = [
            _order_sent("BUY", "false", order_id="o1", level="5", p_fill="0.20"),
            _order_filled("BUY", "false", order_id="o1", level="5",
                          price="14000000", mid_price="14000050"),
            _order_sent("SELL", "true", order_id="c1", level="0", p_fill="0.80"),
            _order_filled("SELL", "true", order_id="c1", level="0",
                          price="14000100", mid_price="14000050"),
        ]
        result = calc_level_analysis(trades)
        # Only level 5 (open order) should be analyzed
        assert result["J1_levels_analyzed"] == 1
        assert "5" in result["J2_level_details"]
        assert "0" not in result["J2_level_details"]
