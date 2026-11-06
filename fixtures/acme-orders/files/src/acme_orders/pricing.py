"""Prices an order: lines, discount, VAT, total. Money is Decimal, rounded once per order."""

from decimal import ROUND_HALF_UP, Decimal

VAT_RATE = Decimal("0.20")
CENT = Decimal("0.01")

DISCOUNTS = {
    "WELCOME10": Decimal("0.10"),
    "STAFF25": Decimal("0.25"),
}


def _round(amount):
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def line_total(line):
    return line.unit_price * line.quantity


def subtotal(order):
    return sum((line_total(line) for line in order.lines), Decimal("0"))


def discount_total(order):
    rate = DISCOUNTS.get((order.discount_code or "").upper(), Decimal("0"))
    return subtotal(order) * rate


def vat_total(order):
    return (subtotal(order) - discount_total(order)) * VAT_RATE


def order_total(order):
    return _round(subtotal(order) - discount_total(order) + vat_total(order))
