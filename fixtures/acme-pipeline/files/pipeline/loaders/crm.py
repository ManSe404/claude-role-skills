"""Load one CRM file of a delivery into its bronze table.

Usage: python3 -m pipeline.loaders.crm customers [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from pipeline.loaders.common import load_bronze

FILES = {
    "customers": ("crm_customers", "customers.csv"),
    "contacts": ("crm_contacts", "contacts.csv"),
    "activities": ("crm_activities", "activities.csv"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load one CRM file into bronze.")
    parser.add_argument("dataset", choices=sorted(FILES))
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args(argv)
    table, name = FILES[args.dataset]
    rows = load_bronze("crm", table, args.date, name)
    print(json.dumps({"rows_read": rows, "rows_written": rows, "rows_changed": rows}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
