"""Sync DB-backed reference data from external providers.

Currently supported:
- Country State City API -> `countries`, `cities`
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on the Python path when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infrastructure.persistence.memory_store import sync_country_state_city_reference_options


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default="csc",
        choices=["csc"],
        help="Reference data source to sync.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.source == "csc":
        sync_country_state_city_reference_options()
        print("Synced `countries` and `cities` from Country State City API into Postgres.")


if __name__ == "__main__":
    main()
