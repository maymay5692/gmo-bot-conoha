"""FR Episode Analyzer tests."""
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _write_snapshot_csv(path: Path, rows: list[dict]):
    fieldnames = [
        "timestamp", "symbol", "funding_rate", "annualized",
        "volume_24h", "has_spot", "can_borrow", "hedge_status",
        "last_price", "spread",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _snap(ts: str, symbol: str, fr: float, hedge: str = "HEDGE_OK", vol: float = 1000000):
    return {
        "timestamp": ts, "symbol": symbol,
        "funding_rate": str(fr), "annualized": str(fr * 3 * 365 * 100),
        "volume_24h": str(vol), "has_spot": "True",
        "can_borrow": "True", "hedge_status": hedge,
        "last_price": "1.0", "spread": "0.001",
    }


def test_episode_dataclass():
    from fr_analyzer import Episode
    ep = Episode(
        symbol="IDUSDT", direction="LONG",
        start_time=datetime(2026, 4, 11, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 4, 11, 18, 0, tzinfo=timezone.utc),
        duration_minutes=480.0, peak_fr=0.003, mean_fr=0.002,
        fr_windows_crossed=1, hedge_status="HEDGE_OK",
        volume_mean=3000000.0, persistence_class="single",
    )
    assert ep.symbol == "IDUSDT"
    assert ep.persistence_class == "single"


def test_load_snapshots_basic(tmp_path):
    from fr_analyzer import load_snapshots
    _write_snapshot_csv(tmp_path / "fr_snapshots_2026-04-11.csv", [
        _snap("2026-04-11T10:00:00+00:00", "IDUSDT", -0.002),
        _snap("2026-04-11T10:05:00+00:00", "AAAUSDT", 0.003),
    ])
    rows = load_snapshots(data_dir=tmp_path)
    assert len(rows) == 2
    assert rows[0]["symbol"] == "AAAUSDT"
    assert rows[0]["_parsed_fr"] == 0.003


def test_load_snapshots_date_filter(tmp_path):
    from fr_analyzer import load_snapshots
    _write_snapshot_csv(tmp_path / "fr_snapshots_2026-04-11.csv", [
        _snap("2026-04-11T10:00:00+00:00", "AAAUSDT", 0.002),
    ])
    _write_snapshot_csv(tmp_path / "fr_snapshots_2026-04-12.csv", [
        _snap("2026-04-12T10:00:00+00:00", "BBBUSDT", 0.003),
    ])
    rows = load_snapshots(data_dir=tmp_path, start_date="2026-04-12")
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BBBUSDT"



def test_count_fr_windows_one_crossing():
    from fr_analyzer import count_fr_windows
    start = datetime(2026, 4, 11, 7, 30, tzinfo=timezone.utc)
    end = datetime(2026, 4, 11, 8, 30, tzinfo=timezone.utc)
    assert count_fr_windows(start, end) == 1


def test_count_fr_windows_two_crossings():
    from fr_analyzer import count_fr_windows
    start = datetime(2026, 4, 11, 7, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 11, 17, 0, tzinfo=timezone.utc)
    assert count_fr_windows(start, end) == 2


def test_count_fr_windows_zero():
    from fr_analyzer import count_fr_windows
    start = datetime(2026, 4, 11, 8, 1, tzinfo=timezone.utc)
    end = datetime(2026, 4, 11, 15, 59, tzinfo=timezone.utc)
    assert count_fr_windows(start, end) == 0


def test_count_fr_windows_midnight_crossing():
    from fr_analyzer import count_fr_windows
    start = datetime(2026, 4, 11, 23, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 12, 1, 0, tzinfo=timezone.utc)
    assert count_fr_windows(start, end) == 1


def test_extract_episodes_single_spike(tmp_path):
    from fr_analyzer import load_snapshots, extract_episodes
    _write_snapshot_csv(tmp_path / "fr_snapshots_2026-04-11.csv", [
        _snap("2026-04-11T10:00:00+00:00", "AAAUSDT", 0.002),
        _snap("2026-04-11T10:05:00+00:00", "AAAUSDT", 0.002),
    ])
    rows = load_snapshots(data_dir=tmp_path)
    episodes = extract_episodes(rows)
    assert len(episodes) == 1
    assert episodes[0].symbol == "AAAUSDT"
    assert episodes[0].direction == "SHORT"
    assert episodes[0].duration_minutes == 5.0
    assert episodes[0].persistence_class == "spike"


def test_extract_episodes_gap_splits(tmp_path):
    """10分以上のギャップで別エピソードに分割。"""
    from fr_analyzer import load_snapshots, extract_episodes
    _write_snapshot_csv(tmp_path / "fr_snapshots_2026-04-11.csv", [
        _snap("2026-04-11T10:00:00+00:00", "AAAUSDT", 0.002),
        _snap("2026-04-11T10:05:00+00:00", "AAAUSDT", 0.002),
        # 15min gap
        _snap("2026-04-11T10:20:00+00:00", "AAAUSDT", 0.003),
    ])
    rows = load_snapshots(data_dir=tmp_path)
    episodes = extract_episodes(rows)
    assert len(episodes) == 2


def test_extract_episodes_direction_flip_splits(tmp_path):
    """FR符号反転で別エピソードに分割。"""
    from fr_analyzer import load_snapshots, extract_episodes
    _write_snapshot_csv(tmp_path / "fr_snapshots_2026-04-11.csv", [
        _snap("2026-04-11T10:00:00+00:00", "AAAUSDT", 0.002),
        _snap("2026-04-11T10:05:00+00:00", "AAAUSDT", -0.003),
    ])
    rows = load_snapshots(data_dir=tmp_path)
    episodes = extract_episodes(rows)
    assert len(episodes) == 2
    assert episodes[0].direction == "SHORT"
    assert episodes[1].direction == "LONG"


def test_extract_episodes_persistent(tmp_path):
    """8h window を2回跨ぐ → persistent。"""
    from fr_analyzer import load_snapshots, extract_episodes
    rows_data = []
    base = datetime(2026, 4, 11, 7, 0, tzinfo=timezone.utc)
    for i in range(130):  # 5min * 130 = 10.8h — crosses 08:00 and 16:00
        ts = (base + timedelta(minutes=i * 5)).isoformat()
        rows_data.append(_snap(ts, "AAAUSDT", 0.002))
    _write_snapshot_csv(tmp_path / "fr_snapshots_2026-04-11.csv", rows_data)
    rows = load_snapshots(data_dir=tmp_path)
    episodes = extract_episodes(rows)
    assert len(episodes) == 1
    assert episodes[0].fr_windows_crossed == 2
    assert episodes[0].persistence_class == "persistent"


def test_calc_episode_pnl_profitable():
    """persistent エピソード（3 window）で利益。"""
    from fr_analyzer import Episode, calc_episode_pnl
    ep = Episode(
        symbol="AAAUSDT", direction="SHORT",
        start_time=datetime(2026, 4, 11, 7, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 4, 12, 7, 0, tzinfo=timezone.utc),
        duration_minutes=1440.0, peak_fr=0.003, mean_fr=0.002,
        fr_windows_crossed=3, hedge_status="HEDGE_OK",
        volume_mean=5000000.0, persistence_class="persistent",
    )
    result = calc_episode_pnl(ep, position_size=333.0, fee_rate=0.0032)
    # FR income: 0.002 * 333 * 3 = 1.998
    # Fee: 333 * 0.0032 = 1.0656
    # Net: 1.998 - 1.0656 = 0.9324
    assert abs(result["fr_income"] - 1.998) < 0.001
    assert abs(result["fee"] - 1.0656) < 0.001
    assert result["net_pnl"] > 0
    assert result["profitable"] is True


def test_calc_episode_pnl_unprofitable_spike():
    """spike エピソード（0 window）は必ず赤字。"""
    from fr_analyzer import Episode, calc_episode_pnl
    ep = Episode(
        symbol="BBBUSDT", direction="LONG",
        start_time=datetime(2026, 4, 11, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 4, 11, 10, 5, tzinfo=timezone.utc),
        duration_minutes=5.0, peak_fr=0.005, mean_fr=0.005,
        fr_windows_crossed=0, hedge_status="HEDGE_OK",
        volume_mean=2000000.0, persistence_class="spike",
    )
    result = calc_episode_pnl(ep, position_size=333.0, fee_rate=0.0032)
    assert result["fr_income"] == 0.0
    assert result["fee"] > 0
    assert result["net_pnl"] < 0
    assert result["profitable"] is False


def test_calc_episode_pnl_break_even():
    """損益分岐 FR の検証。"""
    from fr_analyzer import Episode, calc_episode_pnl
    # fee_rate=0.0032, windows=2 → break_even_fr = 0.0016
    ep = Episode(
        symbol="CCCUSDT", direction="SHORT",
        start_time=datetime(2026, 4, 11, 7, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 4, 11, 17, 0, tzinfo=timezone.utc),
        duration_minutes=600.0, peak_fr=0.0016, mean_fr=0.0016,
        fr_windows_crossed=2, hedge_status="HEDGE_OK",
        volume_mean=3000000.0, persistence_class="persistent",
    )
    result = calc_episode_pnl(ep, position_size=333.0, fee_rate=0.0032)
    # FR: 0.0016 * 333 * 2 = 1.0656, Fee: 1.0656 → net ≈ 0
    assert abs(result["net_pnl"]) < 0.01
    assert result["break_even_fr"] - 0.0016 < 0.0001


def _make_episode(symbol, start_h, end_h, fr, windows, hedge="HEDGE_OK", pclass=None):
    """Helper: 2026-04-11 の hour offset でエピソードを作る。"""
    from fr_analyzer import Episode
    base = datetime(2026, 4, 11, 0, 0, tzinfo=timezone.utc)
    start = base + timedelta(hours=start_h)
    end = base + timedelta(hours=end_h)
    if pclass is None:
        if windows == 0:
            pclass = "spike"
        elif windows == 1:
            pclass = "single"
        else:
            pclass = "persistent"
    return Episode(
        symbol=symbol, direction="SHORT",
        start_time=start, end_time=end,
        duration_minutes=(end_h - start_h) * 60,
        peak_fr=fr, mean_fr=fr,
        fr_windows_crossed=windows, hedge_status=hedge,
        volume_mean=1000000.0, persistence_class=pclass,
    )


def test_simulate_scenario_filters():
    from fr_analyzer import simulate_scenario
    episodes = [
        _make_episode("A", 7, 9, 0.003, 1),         # single, HEDGE_OK
        _make_episode("B", 7, 18, 0.002, 2),         # persistent, HEDGE_OK
        _make_episode("C", 10, 10.1, 0.005, 0),      # spike, HEDGE_OK
        _make_episode("D", 7, 18, 0.002, 2, hedge="NO_BORROW"),  # persistent, NO_BORROW
    ]
    result = simulate_scenario(
        episodes, capital=1000, max_positions=3, fee_rate=0.0032,
        filter_fn=lambda e: e.persistence_class != "spike" and e.hedge_status == "HEDGE_OK",
    )
    assert result["traded"] == 2  # A and B only
    assert result["total_pnl"] != 0


def test_simulate_scenario_respects_max_positions():
    from fr_analyzer import simulate_scenario
    # 4 overlapping episodes, max 2 positions
    episodes = [
        _make_episode("A", 7, 18, 0.003, 2),
        _make_episode("B", 7, 18, 0.003, 2),
        _make_episode("C", 7, 18, 0.003, 2),
        _make_episode("D", 7, 18, 0.003, 2),
    ]
    result = simulate_scenario(
        episodes, capital=1000, max_positions=2, fee_rate=0.0032,
        filter_fn=lambda e: True,
    )
    assert result["traded"] == 2


def test_simulate_scenario_empty():
    from fr_analyzer import simulate_scenario
    result = simulate_scenario(
        [], capital=1000, max_positions=3, fee_rate=0.0032,
        filter_fn=lambda e: True,
    )
    assert result["traded"] == 0
    assert result["total_pnl"] == 0.0
