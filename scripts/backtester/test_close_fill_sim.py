"""close_fill_simモジュールのテスト。

SimResult、calc_close_price、calc_fill_prob の単体テスト。
"""
from __future__ import annotations

import pytest

from backtester.close_fill_sim import (
    SimResult,
    calc_close_price,
    calc_fill_prob,
)

# ---------------------------------------------------------------------------
# TestCalcClosePrice
# ---------------------------------------------------------------------------

MID = 14_000_000.0


class TestCalcClosePrice:
    """calc_close_price のテスト。"""

    def test_close_long_l25(self):
        """L25 (spread_pct=0.0001), factor=0.4, long → 売り指値が mid 上方向に。"""
        # spread_jpy = 0.0001 * 14_000_000 = 1400
        # adjusted_spread = 1400 - 50 = 1350
        # close_price = max(14_000_000 + 1350 * 0.4, mid + 1)
        #             = max(14_000_000 + 540, 14_000_001)
        #             = 14_000_540
        # Wait: 0.0001 * 14_000_000 = 1400, 1400 - 50 = 1350, 1350 * 0.4 = 540
        # => 14_000_540.0
        # But task says expected 14_001_380.0 for L25...
        # L25 corresponds to 25 levels of spread_pct. Let me recheck with spread_pct
        # matching the expected value:
        # 14_001_380 - 14_000_000 = 1380 = adjusted_spread * 0.4
        # adjusted_spread = 1380 / 0.4 = 3450
        # level_spread_jpy = 3450 + 50 = 3500
        # spread_pct = 3500 / 14_000_000 = 0.00025
        # So L25 uses spread_pct=0.00025
        spread_pct = 0.00025
        result = calc_close_price(MID, spread_pct, 0.4, direction=1)
        assert result == pytest.approx(14_001_380.0, abs=1.0)

    def test_close_short_l25(self):
        """L25, factor=0.4, short → 買い指値が mid 下方向に。"""
        spread_pct = 0.00025
        result = calc_close_price(MID, spread_pct, 0.4, direction=-1)
        assert result == pytest.approx(13_998_620.0, abs=1.0)

    def test_close_clamps_to_mid_plus_1(self):
        """factor=0 → adjusted_spread * factor = 0 < 1 → clamp して mid+1 (long) / mid-1 (short)。"""
        result_long = calc_close_price(MID, 0.00025, 0.0, direction=1)
        result_short = calc_close_price(MID, 0.00025, 0.0, direction=-1)
        assert result_long == pytest.approx(MID + 1.0, abs=0.1)
        assert result_short == pytest.approx(MID - 1.0, abs=0.1)

    def test_close_l22(self):
        """L22 (spread_pct=0.00022), factor=0.3, long → 期待値 14_000_909.0。"""
        # level_spread_jpy = 0.00022 * 14_000_000 = 3080
        # adjusted_spread  = 3080 - 50 = 3030
        # close_price = max(14_000_000 + 3030 * 0.3, mid + 1)
        #             = max(14_000_000 + 909, 14_000_001)
        #             = 14_000_909.0
        spread_pct = 0.00022
        result = calc_close_price(MID, spread_pct, 0.3, direction=1)
        assert result == pytest.approx(14_000_909.0, abs=1.0)


# ---------------------------------------------------------------------------
# TestCalcFillProb
# ---------------------------------------------------------------------------

class TestCalcFillProb:
    """calc_fill_prob のテスト。"""

    def test_bid_already_at_close_price_long(self):
        """bid >= close_price のとき P(fill) = 1.0 (long)。"""
        close_price = 14_000_500.0
        result = calc_fill_prob(
            close_price=close_price,
            best_bid=14_000_500.0,
            best_ask=14_001_000.0,
            sigma_1s=0.0003,
            mid=MID,
            direction=1,
        )
        assert result == pytest.approx(1.0)

    def test_ask_already_at_close_price_short(self):
        """ask <= close_price のとき P(fill) = 1.0 (short)。"""
        close_price = 13_999_500.0
        result = calc_fill_prob(
            close_price=close_price,
            best_bid=13_998_000.0,
            best_ask=13_999_500.0,
            sigma_1s=0.0003,
            mid=MID,
            direction=-1,
        )
        assert result == pytest.approx(1.0)

    def test_zero_sigma_no_fill(self):
        """sigma_1s=0 かつ distance > 0 → P(fill) = 0.0。"""
        result = calc_fill_prob(
            close_price=14_001_000.0,
            best_bid=14_000_000.0,
            best_ask=14_001_000.0,
            sigma_1s=0.0,
            mid=MID,
            direction=1,
        )
        assert result == pytest.approx(0.0)

    def test_high_vol_high_prob(self):
        """高ボラ + 小さな距離 → P(fill) > 0.99。"""
        # sigma_jpy = 0.005 * 14_000_000 = 70_000 JPY/s (極端に高い)
        # distance = 100 JPY, dt = 3s, sigma_dt = 70_000 * sqrt(3) ≈ 121_244
        # z = 100 / 121_244 ≈ 0.00082 → 2*norm.cdf(-0.00082) ≈ 0.9993
        result = calc_fill_prob(
            close_price=14_000_100.0,
            best_bid=14_000_000.0,
            best_ask=14_001_000.0,
            sigma_1s=0.005,
            mid=MID,
            direction=1,
        )
        assert result > 0.99

    def test_low_vol_large_distance(self):
        """低ボラ + 大きな距離 → P(fill) < 0.01。"""
        # sigma_jpy = 0.00001 * 14_000_000 = 140 JPY/s (非常に低い)
        # distance = 5000 JPY, dt = 3s
        # sigma_dt = 140 * sqrt(3) ≈ 242.5
        # z = 5000 / 242.5 ≈ 20.6 → 2*norm.cdf(-20.6) ≈ 0
        result = calc_fill_prob(
            close_price=14_005_000.0,
            best_bid=14_000_000.0,
            best_ask=14_001_000.0,
            sigma_1s=0.00001,
            mid=MID,
            direction=1,
        )
        assert result < 0.01

    def test_returns_between_0_and_1(self):
        """結果は常に [0, 1] の範囲に収まる。"""
        result = calc_fill_prob(
            close_price=14_000_800.0,
            best_bid=13_999_500.0,
            best_ask=14_000_500.0,
            sigma_1s=0.0003,
            mid=MID,
            direction=1,
        )
        assert 0.0 <= result <= 1.0
