#!/usr/bin/env python3
"""Initialise the portfolio tracker database.

Usage
-----
    python scripts/init_db.py [--db PATH]
"""

import argparse
import sys
from pathlib import Path

# Allow running from the repository root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DB_PATH
from src.db import initialize_database
from src.utils.logging_config import setup_logging


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Initialise the portfolio tracker database.")
    parser.add_argument(
        "--db",
        default=str(DB_PATH),
        metavar="PATH",
        help="Path to the SQLite database file (default: %(default)s).",
    )
    args = parser.parse_args()
    conn = initialize_database(Path(args.db))
    conn.close()
    print(f"Database ready at {args.db}")


if __name__ == "__main__":
    main()
