"""FR Episode Analyzer tests."""
import csv
from datetime import datetime, timezone
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


from datetime import timedelta


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
