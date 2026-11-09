"""Read the nightly stock export of the warehouse system (CSV, one row per SKU and warehouse)."""

import csv
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StockRow:
    sku: str
    name: str
    warehouse: str
    qty: int
    exported_at: datetime


def parse_row(row: dict[str, str]) -> StockRow:
    return StockRow(
        sku=row["sku"].strip().upper(),
        name=row["name"].strip(),
        warehouse=row["warehouse"].strip(),
        qty=int(row["qty"]),
        exported_at=datetime.fromisoformat(row["exported_at"].strip()),
    )


def read_snapshot(path: str) -> list[StockRow]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [parse_row(row) for row in csv.DictReader(fh)]


def describe(row: StockRow) -> str:
    status = f"{row.qty} in stock" if row.qty > 0 else "out of stock"
    return f"{row.name} ({row.sku}), {row.warehouse} warehouse: {status}."
