import unittest
from datetime import datetime
from decimal import Decimal

from acme_orders import pricing
from acme_orders.importer import Line, Order


def order(*lines, code=None):
    return Order("A-1", "ana@example.com", datetime(2026, 10, 1, 9, 0), code, list(lines))


class OrderTotalTest(unittest.TestCase):
    def test_total_adds_vat(self):
        o = order(Line("TEA-01", 2, Decimal("4.50")))
        self.assertEqual(pricing.order_total(o), Decimal("10.80"))

    def test_welcome_discount_before_vat(self):
        o = order(Line("TEA-01", 2, Decimal("5.00")), code="WELCOME10")
        self.assertEqual(pricing.order_total(o), Decimal("10.80"))

    def test_unknown_code_gives_no_discount(self):
        o = order(Line("TEA-01", 1, Decimal("10.00")), code="NOPE")
        self.assertEqual(pricing.order_total(o), Decimal("12.00"))

    def test_rounds_once_per_order(self):
        o = order(Line("MUG-02", 3, Decimal("3.33")))
        self.assertEqual(pricing.order_total(o), Decimal("11.99"))
