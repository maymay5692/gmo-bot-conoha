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
