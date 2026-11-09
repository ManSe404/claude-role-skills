import unittest
from datetime import datetime, timedelta, timezone

from acme_assist.snapshot import StockRow, describe, parse_row

EXPORTED = datetime(2026, 9, 2, 2, 0, tzinfo=timezone(timedelta(hours=2)))


def raw(**overrides):
    row = {
        "sku": "K200-BLK",
        "name": "Kestrel K-200 black",
        "warehouse": "Novi Sad",
        "qty": "12",
        "exported_at": "2026-09-02T02:00:00+02:00",
    }
    row.update(overrides)
    return row


class ParseRowTest(unittest.TestCase):
    def test_parses_a_row(self):
        row = parse_row(raw())
        self.assertEqual(row, StockRow("K200-BLK", "Kestrel K-200 black", "Novi Sad", 12, EXPORTED))

    def test_normalises_the_sku(self):
        self.assertEqual(parse_row(raw(sku=" k200-wht ")).sku, "K200-WHT")

    def test_bad_quantity_raises(self):
        with self.assertRaises(ValueError):
            parse_row(raw(qty="n/a"))


class DescribeTest(unittest.TestCase):
    def test_in_stock(self):
        self.assertEqual(describe(parse_row(raw())), "Kestrel K-200 black (K200-BLK), Novi Sad warehouse: 12 in stock.")

    def test_out_of_stock(self):
        self.assertIn("out of stock", describe(parse_row(raw(qty="0"))))
