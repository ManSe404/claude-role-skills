"""Imports the shop's daily order export (CSV, ';' separated) into the database."""

import csv
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from acme_orders import pricing, storage


@dataclass
class Line:
    sku: str
    quantity: int
    unit_price: Decimal


@dataclass
class Order:
    order_id: str
    customer_email: str
    created_at: datetime
    discount_code: str | None
    lines: list[Line] = field(default_factory=list)


def parse_amount(value):
    return Decimal(value.strip())


def parse_line(row):
    return Line(
        sku=row["sku"].strip(),
        quantity=int(row["quantity"]),
        unit_price=parse_amount(row["unit_price"]),
    )


def read_orders(path):
    orders = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            order = orders.get(row["order_id"])
            if order is None:
                order = Order(
                    order_id=row["order_id"],
                    customer_email=row["customer_email"].strip().lower(),
                    created_at=datetime.fromisoformat(row["created_at"]),
                    discount_code=(row.get("discount_code") or "").strip().upper() or None,
                )
                orders[order.order_id] = order
            order.lines.append(parse_line(row))
    return list(orders.values())


def import_file(path, db):
    count = 0
    for order in read_orders(path):
        storage.save_order(db, order, pricing.order_total(order))
        count += 1
    return count
