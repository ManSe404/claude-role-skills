"""Load one ERP file of a delivery into its bronze table.

Usage: python3 -m pipeline.loaders.erp orders [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from pipeline.loaders.common import load_bronze

FILES = {
    "orders": ("erp_orders", "orders.csv"),
    "invoices": ("erp_invoices", "invoices.csv"),
    "returns": ("erp_returns", "returns.csv"),
    "payments": ("erp_payments", "payments.csv"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load one ERP file into bronze.")
    parser.add_argument("dataset", choices=sorted(FILES))
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args(argv)
    table, name = FILES[args.dataset]
    rows = load_bronze("erp", table, args.date, name)
    print(json.dumps({"rows_read": rows, "rows_written": rows, "rows_changed": rows}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
