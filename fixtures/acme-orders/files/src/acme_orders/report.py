"""Daily totals report for finance, as HTML."""

import csv
from decimal import Decimal

from acme_orders import pricing

TEMPLATE = """<h1>Orders {{ day }}</h1>
<table>
{% for row in rows %}<tr><td>{{ row.order_id }}</td><td>{{ row.discount }}</td><td>{{ row.vat }}</td><td>{{ row.total }}</td></tr>
{% endfor %}</table>
<p>Adjustments: {{ adjustments }}</p>
<p>{{ note|urlize }}</p>
"""

KINDS = ("discount", "vat", "order")


def read_adjustments(path):
    total = Decimal("0")
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            total += Decimal(row["amount"].strip())
    return total


def daily_report(orders, day, adjustments_path=None, note=""):
    from jinja2 import Template

    rows = []
    for order in orders:
        row = {"order_id": order.order_id}
        for kind in KINDS:
            row["total" if kind == "order" else kind] = getattr(pricing, f"{kind}_total")(order)
        rows.append(row)
    adjustments = read_adjustments(adjustments_path) if adjustments_path else Decimal("0")
    return Template(TEMPLATE).render(day=day, rows=rows, adjustments=adjustments, note=note)
