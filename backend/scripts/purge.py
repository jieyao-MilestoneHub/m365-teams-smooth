"""Retention pass: purge working storage (checkpoints + verdict claims) for finished trials.

Run: ``cd backend && uv run python -m scripts.purge [--retention-days N]``. The audit log is never
touched. Safe to re-run; schedule it (e.g. nightly cron) on any deployment that accumulates trials.
"""

from __future__ import annotations

import argparse

from app.config import Settings
from app.container import build_maintenance_service


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override RETENTION_DAYS for this run (default: settings value).",
    )
    args = parser.parse_args()

    settings = Settings()
    days = args.retention_days if args.retention_days is not None else settings.retention_days
    report = build_maintenance_service(settings).purge_finished_trials(days)
    print(f"cutoff={report.cutoff} threads_purged={report.threads_purged}")


if __name__ == "__main__":
    main()
