"""Bitget clean-window DSR: filter paper trades to post-PID-lock period.

PID lock fix landed 2026-04-17 01:11 JST = 2026-04-16 16:11 UTC.
Data before that cutoff is contaminated by phantom duplicates from
overlapping watchdog-spawned instances.

Runs cluster dedup + Gate 1 (Sharpe/PSR/DSR) on the clean window.
"""
import csv
import statistics
from datetime import datetime, timezone
from pathlib import Path

from gate0_cvkelly import cluster_dedup_paper, dsr  # reuse existing code

CACHE_DIR = Path(__file__).parent / "data_cache"
PAPER = CACHE_DIR / "fr_paper_trades.csv"
CLEAN_PAPER = CACHE_DIR / "fr_paper_trades_clean.csv"
CUTOFF = datetime(2026, 4, 16, 16, 11, tzinfo=timezone.utc)


def build_clean_subset():
    """Filter paper_trades.csv to rows at/after the PID-lock cutoff."""
    with open(PAPER) as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        kept = [
            r for r in reader
            if datetime.fromisoformat(r["timestamp"]) >= CUTOFF
        ]
    with open(CLEAN_PAPER, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)
    return kept


def gate1_stats(closes: list[dict]) -> None:
    if not closes:
        print("  No closes in clean window")
        return
    pnls = [float(r["pnl"]) for r in closes]
    stats = dsr(pnls)
    print(f"\nRaw clean (no cluster dedup):")
    print(
        f"  n={stats['n']}  Total=${sum(pnls):.2f}  "
        f"mean=${sum(pnls)/len(pnls):.3f}  "
        f"SR={stats['sr']:.3f}  PSR={stats['psr']:.3f}  "
        f"DSR={stats['dsr']:.3f} (SR*={stats['sr_star']:.3f})"
    )
    wins = sum(1 for p in pnls if p > 0)
    print(f"  Win rate: {wins}/{len(pnls)} = {wins/len(pnls)*100:.0f}%")


def main():
    print("=" * 60)
    print(f"Bitget Clean-Window DSR  (cutoff >= {CUTOFF.isoformat()})")
    print("=" * 60)
    kept = build_clean_subset()
    print(f"Rows kept (post-cutoff): {len(kept)}")
    opens = [r for r in kept if r["action"] == "OPEN"]
    closes = [r for r in kept if r["action"] == "CLOSE"]
    print(f"  OPEN:  {len(opens)}")
    print(f"  CLOSE: {len(closes)}")

    gate1_stats(closes)

    # Cluster dedup runs on full PAPER file in gate0_cvkelly, so we
    # temporarily swap the file for a clean analysis.
    import gate0_cvkelly as g
    g.PAPER = CLEAN_PAPER
    g.cluster_dedup_paper()


if __name__ == "__main__":
    main()
