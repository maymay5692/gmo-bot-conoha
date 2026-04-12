# FR Episode Analyzer 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bitget FR スナップショット CSV からエピソードを抽出し、持続性分類・修正 P&L・what-if シミュレーションを提供する分析 CLI を構築する

**Architecture:** 単一スクリプト `scripts/fr_analyzer.py` に全ロジックを集約。`fr_monitor.py` への依存なし。CSV 読み込み → エピソード抽出 → P&L 計算 → レポート出力の単方向パイプライン。

**Tech Stack:** Python 3, csv, dataclasses, argparse（外部依存なし）

**Spec:** `docs/superpowers/specs/2026-04-13-fr-analyzer-design.md`

---

### Task 1: Episode dataclass + CSV ローディング

**Files:**
- Create: `scripts/fr_analyzer.py`
- Create: `scripts/test_fr_analyzer.py`

- [ ] **Step 1: failing test を書く**

```python
# scripts/test_fr_analyzer.py
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
    assert rows[0]["symbol"] == "AAAUSDT"  # sorted by symbol
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
```

- [ ] **Step 2: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest test_fr_analyzer.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'fr_analyzer'"

- [ ] **Step 3: 実装**

```python
# scripts/fr_analyzer.py
"""Bitget FR Episode Analyzer.

Reads fr_snapshots_*.csv files, extracts FR episodes,
calculates corrected P&L, and reports persistence analysis.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data_cache"
FR_PAYMENT_HOURS = (0, 8, 16)
_DATE_RE = re.compile(r"fr_snapshots_(\d{4}-\d{2}-\d{2})\.csv")


@dataclass
class Episode:
    symbol: str
    direction: str
    start_time: datetime
    end_time: datetime
    duration_minutes: float
    peak_fr: float
    mean_fr: float
    fr_windows_crossed: int
    hedge_status: str
    volume_mean: float
    persistence_class: str


def load_snapshots(
    data_dir: Path = DATA_DIR,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Load and merge all fr_snapshots_*.csv files.

    Returns rows sorted by (symbol, timestamp).
    Each row gets '_parsed_time' and '_parsed_fr' fields.
    """
    files = sorted(data_dir.glob("fr_snapshots_*.csv"))

    if start_date or end_date:
        filtered = []
        for f in files:
            m = _DATE_RE.match(f.name)
            if not m:
                continue
            date_str = m.group(1)
            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue
            filtered.append(f)
        files = filtered

    rows: list[dict] = []
    for path in files:
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["_parsed_time"] = datetime.fromisoformat(row["timestamp"])
                row["_parsed_fr"] = float(row["funding_rate"])
                rows.append(row)

    rows.sort(key=lambda r: (r["symbol"], r["_parsed_time"]))
    return rows
```

- [ ] **Step 4: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest test_fr_analyzer.py -v`
Expected: 3 passed

- [ ] **Step 5: コミット**

```bash
git add scripts/fr_analyzer.py scripts/test_fr_analyzer.py
git commit -m "feat: FR analyzer — Episode dataclass and CSV loading"
```

---

### Task 2: エピソード抽出 + FR payment window + 持続性分類

**Files:**
- Modify: `scripts/fr_analyzer.py`
- Modify: `scripts/test_fr_analyzer.py`

- [ ] **Step 1: failing test を書く**

`test_fr_analyzer.py` の末尾に追加:

```python
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
```

- [ ] **Step 2: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest test_fr_analyzer.py -v`
Expected: FAIL with "cannot import name 'count_fr_windows'"

- [ ] **Step 3: 実装**

`fr_analyzer.py` の末尾（`load_snapshots` の後）に追加:

```python
from collections import Counter
from datetime import timedelta
from itertools import groupby


def count_fr_windows(start: datetime, end: datetime) -> int:
    """Count FR payment windows (00:00/08:00/16:00 UTC) in (start, end]."""
    if start >= end:
        return 0
    count = 0
    current_day = start.date()
    end_day = end.date()
    while current_day <= end_day:
        for hour in FR_PAYMENT_HOURS:
            payment = datetime(
                current_day.year, current_day.month, current_day.day,
                hour, 0, 0, tzinfo=timezone.utc,
            )
            if start < payment <= end:
                count += 1
        current_day += timedelta(days=1)
    return count


def _classify_persistence(fr_windows: int) -> str:
    if fr_windows == 0:
        return "spike"
    if fr_windows == 1:
        return "single"
    return "persistent"


def _build_episode(rows: list[dict]) -> Episode:
    frs = [abs(r["_parsed_fr"]) for r in rows]
    times = [r["_parsed_time"] for r in rows]
    volumes = [float(r["volume_24h"]) for r in rows]
    hedge_counts = Counter(r["hedge_status"] for r in rows)

    start = min(times)
    end = max(times)
    fr_windows = count_fr_windows(start, end)

    return Episode(
        symbol=rows[0]["symbol"],
        direction="LONG" if rows[0]["_parsed_fr"] < 0 else "SHORT",
        start_time=start,
        end_time=end,
        duration_minutes=(end - start).total_seconds() / 60,
        peak_fr=max(frs),
        mean_fr=sum(frs) / len(frs),
        fr_windows_crossed=fr_windows,
        hedge_status=hedge_counts.most_common(1)[0][0],
        volume_mean=sum(volumes) / len(volumes),
        persistence_class=_classify_persistence(fr_windows),
    )


def extract_episodes(
    snapshots: list[dict],
    gap_minutes: float = 10.0,
) -> list[Episode]:
    """Group snapshots into episodes per symbol.

    Splits on: time gap > gap_minutes, or FR sign flip.
    """
    episodes: list[Episode] = []
    gap_delta = timedelta(minutes=gap_minutes)

    for _symbol, group_iter in groupby(snapshots, key=lambda r: r["symbol"]):
        group = list(group_iter)
        if not group:
            continue

        current: list[dict] = [group[0]]

        for row in group[1:]:
            prev = current[-1]
            time_gap = row["_parsed_time"] - prev["_parsed_time"]
            sign_flip = (row["_parsed_fr"] > 0) != (prev["_parsed_fr"] > 0)

            if time_gap > gap_delta or sign_flip:
                episodes.append(_build_episode(current))
                current = [row]
            else:
                current.append(row)

        episodes.append(_build_episode(current))

    episodes.sort(key=lambda e: e.start_time)
    return episodes
```

- [ ] **Step 4: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest test_fr_analyzer.py -v`
Expected: 11 passed

- [ ] **Step 5: コミット**

```bash
git add scripts/fr_analyzer.py scripts/test_fr_analyzer.py
git commit -m "feat: FR analyzer — episode extraction with persistence classification"
```

---

### Task 3: 修正 P&L モデル

**Files:**
- Modify: `scripts/fr_analyzer.py`
- Modify: `scripts/test_fr_analyzer.py`

- [ ] **Step 1: failing test を書く**

`test_fr_analyzer.py` の末尾に追加:

```python
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
```

- [ ] **Step 2: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest test_fr_analyzer.py::test_calc_episode_pnl_profitable -v`
Expected: FAIL with "cannot import name 'calc_episode_pnl'"

- [ ] **Step 3: 実装**

`fr_analyzer.py` の末尾に追加:

```python
def calc_episode_pnl(
    episode: Episode,
    position_size: float,
    fee_rate: float,
) -> dict:
    """Calculate theoretical hedged P&L for one episode.

    Assumes delta-neutral (perp+spot) → price_pnl=0.
    FR collected only at payment windows (not per poll).
    """
    fr_income = episode.mean_fr * position_size * episode.fr_windows_crossed
    fee = position_size * fee_rate
    net_pnl = fr_income - fee

    break_even_fr = (
        fee_rate / episode.fr_windows_crossed
        if episode.fr_windows_crossed > 0
        else float("inf")
    )

    return {
        "fr_income": fr_income,
        "fee": fee,
        "net_pnl": net_pnl,
        "profitable": net_pnl > 0,
        "break_even_fr": break_even_fr,
    }
```

- [ ] **Step 4: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest test_fr_analyzer.py -v`
Expected: 14 passed

- [ ] **Step 5: コミット**

```bash
git add scripts/fr_analyzer.py scripts/test_fr_analyzer.py
git commit -m "feat: FR analyzer — corrected P&L model with hedged arbitrage math"
```

---

### Task 4: what-if シミュレーション

**Files:**
- Modify: `scripts/fr_analyzer.py`
- Modify: `scripts/test_fr_analyzer.py`

- [ ] **Step 1: failing test を書く**

`test_fr_analyzer.py` の末尾に追加:

```python
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
```

- [ ] **Step 2: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest test_fr_analyzer.py::test_simulate_scenario_filters -v`
Expected: FAIL with "cannot import name 'simulate_scenario'"

- [ ] **Step 3: 実装**

`fr_analyzer.py` の末尾に追加:

```python
from typing import Callable


def simulate_scenario(
    episodes: list[Episode],
    capital: float,
    max_positions: int,
    fee_rate: float,
    filter_fn: Callable[[Episode], bool],
) -> dict:
    """Run what-if simulation for a filter scenario.

    Processes episodes in time order, respects max_positions.
    """
    filtered = sorted(
        [e for e in episodes if filter_fn(e)],
        key=lambda e: e.start_time,
    )

    if not filtered:
        return {
            "traded": 0,
            "profitable": 0,
            "total_pnl": 0.0,
            "monthly_pnl": 0.0,
            "annual_return_pct": 0.0,
        }

    position_size = capital / max_positions
    active_ends: list[datetime] = []
    total_pnl = 0.0
    traded = 0
    profitable_count = 0

    for ep in filtered:
        active_ends = [t for t in active_ends if t > ep.start_time]

        if len(active_ends) >= max_positions:
            continue

        active_ends.append(ep.end_time)
        pnl = calc_episode_pnl(ep, position_size, fee_rate)
        total_pnl += pnl["net_pnl"]
        traded += 1
        if pnl["profitable"]:
            profitable_count += 1

    all_times = [e.start_time for e in filtered] + [e.end_time for e in filtered]
    days = max((max(all_times) - min(all_times)).total_seconds() / 86400, 1.0)

    return {
        "traded": traded,
        "profitable": profitable_count,
        "total_pnl": total_pnl,
        "monthly_pnl": total_pnl / days * 30,
        "annual_return_pct": (total_pnl / days * 365) / capital * 100,
    }
```

- [ ] **Step 4: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest test_fr_analyzer.py -v`
Expected: 17 passed

- [ ] **Step 5: コミット**

```bash
git add scripts/fr_analyzer.py scripts/test_fr_analyzer.py
git commit -m "feat: FR analyzer — what-if scenario simulation"
```

---

### Task 5: レポート出力 + CLI + CSV エクスポート

**Files:**
- Modify: `scripts/fr_analyzer.py`
- Modify: `scripts/test_fr_analyzer.py`

- [ ] **Step 1: failing test を書く**

`test_fr_analyzer.py` の末尾に追加:

```python
def test_write_episodes_csv(tmp_path):
    from fr_analyzer import write_episodes_csv
    episodes = [
        _make_episode("AAAUSDT", 7, 18, 0.003, 2),
        _make_episode("BBBUSDT", 10, 10.1, 0.005, 0),
    ]
    out_path = tmp_path / "fr_episodes.csv"
    write_episodes_csv(episodes, out_path)
    assert out_path.exists()
    with open(out_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 2
    assert rows[0]["symbol"] == "AAAUSDT"
    assert rows[0]["persistence_class"] == "persistent"
    assert float(rows[0]["mean_fr"]) == 0.003


def test_format_class_table():
    from fr_analyzer import format_class_table
    episodes = [
        _make_episode("A", 7, 18, 0.003, 2),
        _make_episode("B", 10, 10.1, 0.005, 0),
        _make_episode("C", 7, 9, 0.002, 1),
    ]
    table = format_class_table(episodes, position_size=333.0, fee_rate=0.0032)
    assert len(table) == 3  # spike, single, persistent
    assert table[0]["class"] == "spike"
    assert table[2]["class"] == "persistent"
```

- [ ] **Step 2: テスト実行して失敗を確認**

Run: `cd scripts && python -m pytest test_fr_analyzer.py::test_write_episodes_csv -v`
Expected: FAIL with "cannot import name 'write_episodes_csv'"

- [ ] **Step 3: 実装**

`fr_analyzer.py` の末尾に追加:

```python
import argparse


def write_episodes_csv(episodes: list[Episode], path: Path) -> None:
    """Write all episodes to CSV (overwrites)."""
    fieldnames = [
        "symbol", "direction", "start_time", "end_time",
        "duration_minutes", "peak_fr", "mean_fr",
        "fr_windows_crossed", "hedge_status", "volume_mean",
        "persistence_class",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for ep in episodes:
            writer.writerow({
                "symbol": ep.symbol,
                "direction": ep.direction,
                "start_time": ep.start_time.isoformat(),
                "end_time": ep.end_time.isoformat(),
                "duration_minutes": f"{ep.duration_minutes:.1f}",
                "peak_fr": f"{ep.peak_fr:.6f}",
                "mean_fr": f"{ep.mean_fr:.6f}",
                "fr_windows_crossed": ep.fr_windows_crossed,
                "hedge_status": ep.hedge_status,
                "volume_mean": f"{ep.volume_mean:.0f}",
                "persistence_class": ep.persistence_class,
            })


def format_class_table(
    episodes: list[Episode],
    position_size: float,
    fee_rate: float,
) -> list[dict]:
    """Build persistence class summary table (HEDGE_OK only)."""
    hedgeable = [e for e in episodes if e.hedge_status == "HEDGE_OK"]
    classes = ["spike", "single", "persistent"]
    table = []

    for cls in classes:
        group = [e for e in hedgeable if e.persistence_class == cls]
        if not group:
            table.append({
                "class": cls, "count": 0, "mean_fr": 0.0,
                "mean_dur": 0.0, "theory_pnl": 0.0, "profitable_pct": 0.0,
            })
            continue

        pnls = [calc_episode_pnl(e, position_size, fee_rate) for e in group]
        table.append({
            "class": cls,
            "count": len(group),
            "mean_fr": sum(e.mean_fr for e in group) / len(group),
            "mean_dur": sum(e.duration_minutes for e in group) / len(group),
            "theory_pnl": sum(p["net_pnl"] for p in pnls) / len(pnls),
            "profitable_pct": sum(1 for p in pnls if p["profitable"]) / len(pnls) * 100,
        })

    return table


def _print_report(episodes: list[Episode], capital: float, max_positions: int, fee_rate: float):
    """Print full analysis report to stdout."""
    if not episodes:
        print("No episodes found.")
        return

    position_size = capital / max_positions
    hedgeable = [e for e in episodes if e.hedge_status == "HEDGE_OK"]
    start = min(e.start_time for e in episodes)
    end = max(e.end_time for e in episodes)
    days = max((end - start).total_seconds() / 86400, 1.0)

    # Summary
    print("=" * 60)
    print("FR Episode Analysis")
    print("=" * 60)
    print(f"  Period: {start.strftime('%Y-%m-%d')} — {end.strftime('%Y-%m-%d')} ({days:.1f} days)")
    print(f"  Total episodes: {len(episodes)}")
    print(f"  HEDGE_OK: {len(hedgeable)} ({len(hedgeable)/len(episodes)*100:.1f}%)")

    by_class = {}
    for e in episodes:
        by_class.setdefault(e.persistence_class, []).append(e)
    parts = [f"{cls}={len(eps)}" for cls, eps in sorted(by_class.items())]
    print(f"  Persistence: {', '.join(parts)}")

    fee_pct = fee_rate * 100
    print(f"\n  Capital: ${capital:.0f}, Max positions: {max_positions}")
    print(f"  Position size: ${position_size:.0f}, Fee (round-trip): {fee_pct:.2f}%")

    # Class table
    print(f"\n{'='*60}")
    print("Persistence Class Summary (HEDGE_OK only)")
    print(f"{'='*60}")
    table = format_class_table(episodes, position_size, fee_rate)
    print(f"  {'Class':<12} {'Count':>5} {'Mean FR':>9} {'Mean Dur':>10} {'PnL/ep':>10} {'Profit%':>8}")
    print(f"  {'-'*12} {'-'*5} {'-'*9} {'-'*10} {'-'*10} {'-'*8}")
    for row in table:
        if row["count"] == 0:
            print(f"  {row['class']:<12} {'—':>5}")
            continue
        dur_str = (
            f"{row['mean_dur']:.0f}min" if row["mean_dur"] < 120
            else f"{row['mean_dur']/60:.1f}h"
        )
        print(
            f"  {row['class']:<12} {row['count']:>5} "
            f"{row['mean_fr']*100:>8.3f}% {dur_str:>10} "
            f"${row['theory_pnl']:>+8.2f} {row['profitable_pct']:>7.0f}%"
        )

    # What-if
    print(f"\n{'='*60}")
    print("What-if Simulation")
    print(f"{'='*60}")

    scenarios = [
        ("All HEDGE_OK", lambda e: e.hedge_status == "HEDGE_OK"),
        ("single+ HEDGE_OK", lambda e: e.hedge_status == "HEDGE_OK" and e.persistence_class != "spike"),
        ("persistent HEDGE_OK", lambda e: e.hedge_status == "HEDGE_OK" and e.persistence_class == "persistent"),
    ]
    print(f"  {'Scenario':<25} {'Traded':>6} {'Monthly':>10} {'Annual':>10}")
    print(f"  {'-'*25} {'-'*6} {'-'*10} {'-'*10}")
    for name, fn in scenarios:
        r = simulate_scenario(episodes, capital, max_positions, fee_rate, fn)
        print(
            f"  {name:<25} {r['traded']:>6} "
            f"${r['monthly_pnl']:>+8.2f} {r['annual_return_pct']:>+9.1f}%"
        )

    # Break-even info
    print(f"\n  Break-even FR per windows crossed:")
    for w in [1, 2, 3]:
        be = fee_rate / w
        print(f"    {w} window: {be*100:.3f}%/8h")


def main():
    parser = argparse.ArgumentParser(description="Bitget FR Episode Analyzer")
    parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=1000.0, help="Capital in USD")
    parser.add_argument("--max-positions", type=int, default=3, help="Max concurrent positions")
    parser.add_argument("--fee-rate", type=float, default=0.0032, help="Round-trip fee rate")
    parser.add_argument("--csv-only", action="store_true", help="Output CSV only, no report")
    args = parser.parse_args()

    snapshots = load_snapshots(
        data_dir=DATA_DIR,
        start_date=args.start,
        end_date=args.end,
    )
    if not snapshots:
        print("No snapshot data found.")
        return

    episodes = extract_episodes(snapshots)

    csv_path = DATA_DIR / "fr_episodes.csv"
    write_episodes_csv(episodes, csv_path)

    if args.csv_only:
        print(f"Wrote {len(episodes)} episodes to {csv_path}")
        return

    _print_report(episodes, args.capital, args.max_positions, args.fee_rate)
    print(f"\n  Episodes CSV: {csv_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: テスト実行してパスを確認**

Run: `cd scripts && python -m pytest test_fr_analyzer.py -v`
Expected: 19 passed

- [ ] **Step 5: 実データで動作確認**

Run: `cd scripts && python fr_analyzer.py`
Expected: レポートが表示され、`data_cache/fr_episodes.csv` が生成される

- [ ] **Step 6: コミット**

```bash
git add scripts/fr_analyzer.py scripts/test_fr_analyzer.py
git commit -m "feat: FR analyzer — report output, CLI, and CSV export"
```
