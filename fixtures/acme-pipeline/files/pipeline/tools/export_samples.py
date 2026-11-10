"""Write CSV copies of the served tables into samples/<layer>/<table>.csv, the last N days of each.

Usage: python3 -m pipeline.tools.export_samples [--days 29]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from pipeline import warehouse

TABLES = {
    "gold.sales_daily": (
        "sales_date",
        [
            "sales_date", "store_id", "store_name", "currency", "orders", "order_lines", "gross_revenue",
            "cancelled_amount", "net_revenue", "kg_eq", "customer_id", "customer_email", "built_at",
        ],
    ),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CSV copies of the served tables.")
    parser.add_argument("--days", type=int, default=29)
    args = parser.parse_args(argv)
    for table, (day_column, columns) in TABLES.items():
        layer, name = table.split(".")
        rows = warehouse.query(
            f"select {', '.join(columns)} from {table} where {day_column} >= current_date - {args.days}"
            f" and {day_column} < current_date order by {day_column}, store_id, currency",
            {},
        )
        target = Path("samples") / layer / f"{name}.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(columns)
            writer.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
