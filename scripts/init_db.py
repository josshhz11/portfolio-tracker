#!/usr/bin/env python3
"""Initialise the portfolio tracker database.

Usage
-----
    python scripts/init_db.py
"""

import argparse
import sys
from pathlib import Path

# Allow running from the repository root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db import initialize_database
from src.utils.logging_config import setup_logging


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description="Initialise the portfolio tracker database.")
    parser.parse_args()
    conn = initialize_database()
    conn.close()
    print("Database ready in Supabase/Postgres")


if __name__ == "__main__":
    main()
