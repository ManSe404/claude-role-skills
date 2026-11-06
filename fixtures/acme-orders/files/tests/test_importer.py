import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from acme_orders import importer

HEADER = "order_id;customer_email;created_at;sku;quantity;unit_price;discount_code\n"


class ParseAmountTest(unittest.TestCase):
    def test_plain_amount(self):
        self.assertEqual(importer.parse_amount("12.50"), Decimal("12.50"))

    def test_strips_spaces(self):
        self.assertEqual(importer.parse_amount(" 3.00 "), Decimal("3.00"))


class ReadOrdersTest(unittest.TestCase):
    def test_groups_lines_by_order(self):
        rows = (
            HEADER
            + "A-1;Ana@Example.com;2026-10-01T09:00:00+02:00;TEA-01;2;4.50;welcome10\n"
            + "A-1;ana@example.com;2026-10-01T09:00:00+02:00;MUG-02;1;8.00;\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orders.csv"
            path.write_text(rows, encoding="utf-8")
            orders = importer.read_orders(path)
        self.assertEqual(len(orders), 1)
        self.assertEqual(len(orders[0].lines), 2)
        self.assertEqual(orders[0].customer_email, "ana@example.com")
        self.assertEqual(orders[0].discount_code, "WELCOME10")
