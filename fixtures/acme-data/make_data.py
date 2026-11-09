#!/usr/bin/env python3
"""Generate the sample CSVs of the acme-data fixture into extras/data/.

Usage: python3 fixtures/acme-data/make_data.py [TARGET_DIR]

Everything is made up. E-mails are at example.com, phones are in the 555 range and the JMBGs use the unassigned region
66, so none can belong to a real person. Only `Random.random()` is used, because it is the one method whose sequence
Python guarantees across versions, so the same seed gives the same bytes on every interpreter.

Planted for data_profile.py: 6 duplicated customer ids, 30 order lines whose product does not exist, decimal commas in
120 unit prices, dd.mm.yyyy in 300 order dates and several promotions on some products.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "extras" / "data"
SEED = 20260609

FIRST_NAMES = [
    "Ana", "Bojan", "Danica", "Dragan", "Goran", "Ivana", "Jasna", "Katarina", "Lazar", "Ljiljana", "Marija", "Milan",
    "Nada", "Nikola", "Olivera", "Petar", "Radmila", "Sava", "Tamara", "Uroš", "Vera", "Vuk", "Zorica", "Željko",
]  # fmt: skip
LAST_NAMES = [
    "Borović", "Bresković", "Cerović", "Dubović", "Grabić", "Hrastić", "Jasenović", "Javorac", "Kestenić", "Klenović",
    "Lipić", "Orahović", "Smrekić", "Šumarac", "Topolić", "Vrbić",
]  # fmt: skip
CITIES = ["Novi Sad", "Subotica", "Zrenjanin", "Pančevo", "Sombor", "Kikinda", "Vršac", "Sremska Mitrovica"]
LOYALTY_TIERS = ["none", "bronze", "silver", "gold"]
STATUSES = ["completed"] * 90 + ["cancelled"] * 6 + ["returned"] * 4

STORES = [
    (1, "Acme Novi Sad Centar", "Novi Sad", "Bačka"),
    (2, "Acme Novi Sad Liman", "Novi Sad", "Bačka"),
    (3, "Acme Novi Sad Detelinara", "Novi Sad", "Bačka"),
    (4, "Acme Novi Sad Klisa", "Novi Sad", "Bačka"),
    (5, "Acme Subotica", "Subotica", "Bačka"),
    (6, "Acme Sombor", "Sombor", "Bačka"),
    (7, "Acme Zrenjanin", "Zrenjanin", "Banat"),
    (8, "Acme Kikinda", "Kikinda", "Banat"),
    (9, "Acme Pančevo", "Pančevo", "Banat"),
    (10, "Acme Vršac", "Vršac", "Banat"),
    (11, "Acme Sremska Mitrovica", "Sremska Mitrovica", "Srem"),
    (12, "Acme Ruma", "Ruma", "Srem"),
]

CATEGORIES = {
    "Dairy": ["Yogurt", "Milk", "Kefir", "Butter", "Cheese"],
    "Bakery": ["Bread", "Rolls", "Pastry", "Crackers", "Rusks"],
    "Produce": ["Apples", "Potatoes", "Tomatoes", "Peppers", "Onions"],
    "Meat": ["Chicken", "Sausage", "Ham", "Beef", "Pork"],
    "Frozen": ["Peas", "Spinach", "Berries", "Dumplings", "Pizza"],
    "Drinks": ["Juice", "Water", "Tea", "Coffee", "Lemonade"],
    "Pantry": ["Flour", "Rice", "Pasta", "Oil", "Sugar"],
    "Snacks": ["Biscuits", "Chips", "Nuts", "Wafers", "Pretzels"],
}
VARIANTS = ["Classic", "Light", "Organic"]

TRANSLITERATE = str.maketrans("čćšžđČĆŠŽĐ", "ccszdCCSZD")


def below(rng: random.Random, n: int) -> int:
    """A whole number from 0 up to, but not including, n."""
    return int(rng.random() * n)


def pick(rng: random.Random, items: Sequence[str]) -> str:
    return items[below(rng, len(items))]


def sample(rng: random.Random, n: int, k: int) -> list[int]:
    """k distinct whole numbers below n, in random order."""
    return sorted(range(n), key=lambda _: rng.random())[:k]


def check_digit(digits: str) -> int:
    """The JMBG check digit of the first 12 digits."""
    d = [int(c) for c in digits]
    total = sum(weight * (d[i] + d[i + 6]) for i, weight in enumerate([7, 6, 5, 4, 3, 2]))
    m = 11 - total % 11
    return 0 if m > 9 else m


def national_id(rng: random.Random, birth: date) -> str:
    prefix = f"{birth.day:02d}{birth.month:02d}{birth.year % 1000:03d}66{below(rng, 1000):03d}"
    return prefix + str(check_digit(prefix))


def customers(rng: random.Random) -> list[list[str]]:
    """400 customers and 6 extra rows that repeat a customer id with a newer loyalty tier."""
    rows: list[list[str]] = []
    for customer_id in range(10001, 10401):
        first = pick(rng, FIRST_NAMES)
        last = pick(rng, LAST_NAMES)
        address = f"{first}.{last}.{customer_id}".translate(TRANSLITERATE).lower()
        birth = date(1950, 1, 1) + timedelta(days=below(rng, 19000))
        rows.append(
            [
                str(customer_id),
                first,
                last,
                f"{address}@example.com",
                f"+381 60 555 {below(rng, 10000):04d}",
                national_id(rng, birth),
                birth.isoformat(),
                pick(rng, CITIES),
                pick(rng, LOYALTY_TIERS),
            ]
        )
    duplicates = [list(rows[index]) for index in sample(rng, len(rows), 6)]
    for duplicate in duplicates:
        duplicate[8] = "gold" if duplicate[8] != "gold" else "silver"
        rows.insert(below(rng, len(rows)), duplicate)
    return rows


def orders(rng: random.Random) -> list[list[str]]:
    """1,500 orders from 2026, by date, 300 of them with the date as dd.mm.yyyy."""
    days = sorted(below(rng, 270) for _ in range(1500))
    dotted = set(sample(rng, 1500, 300))
    rows: list[list[str]] = []
    for index, offset in enumerate(days):
        day = date(2026, 1, 1) + timedelta(days=offset)
        shown = day.strftime("%d.%m.%Y") if index in dotted else day.isoformat()
        customer = str(10001 + below(rng, 400))
        store = str(1 + below(rng, 12))
        rows.append([str(500001 + index), customer, store, shown, pick(rng, STATUSES)])
    return rows


def products(rng: random.Random) -> list[list[str]]:
    """120 products: 5 kinds in each of 8 categories, in 3 variants."""
    rows: list[list[str]] = []
    for category, nouns in CATEGORIES.items():
        for noun in nouns:
            for variant in VARIANTS:
                price = 50 + below(rng, 1450)
                rows.append([str(1001 + len(rows)), f"{variant} {noun}", category, f"{price / 10:.2f}"])
    return rows


def order_lines(rng: random.Random, order_rows: list[list[str]], product_rows: list[list[str]]) -> list[list[str]]:
    """3,000 lines over the orders, 30 of them on a product that does not exist, 120 with a decimal comma."""
    per_order = [1] * len(order_rows)
    extra = 3000 - len(order_rows)
    while extra:
        index = below(rng, len(order_rows))
        if per_order[index] < 4:
            per_order[index] += 1
            extra -= 1
    rows: list[list[str]] = []
    for order, count in zip(order_rows, per_order, strict=True):
        for line_no in range(1, count + 1):
            product = product_rows[below(rng, len(product_rows))]
            price = float(product[3]) * [1.0, 0.95, 0.9][below(rng, 3)]
            rows.append([order[0], str(line_no), product[0], str(1 + below(rng, 6)), f"{price:.2f}"])
    planted = sample(rng, len(rows), 150)
    for offset, index in enumerate(planted[:30]):
        rows[index][2] = str(9001 + offset)
    for index in planted[30:]:
        rows[index][4] = rows[index][4].replace(".", ",")
    return rows


def promotions(rng: random.Random, product_rows: list[list[str]]) -> list[list[str]]:
    """60 promotions: 12 products have three each and 24 products have one."""
    chosen = sample(rng, len(product_rows), 36)
    targets = [index for index in chosen[:12] for _ in range(3)] + chosen[12:]
    rows: list[list[str]] = []
    for offset, index in enumerate(targets):
        start = date(2026, 1, 1) + timedelta(days=below(rng, 250))
        end = start + timedelta(days=7 + below(rng, 15))
        discount = 5 + 5 * below(rng, 6)
        rows.append([str(9001 + offset), product_rows[index][0], start.isoformat(), end.isoformat(), str(discount)])
    return rows


def write(target: Path, name: str, header: list[str], rows: list[list[str]]) -> None:
    with (target / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the sample CSVs of the acme-data fixture.")
    parser.add_argument("target", type=Path, nargs="?", default=TARGET, help="output directory")
    args = parser.parse_args(argv)
    target: Path = args.target
    target.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    customer_rows = customers(rng)
    order_rows = orders(rng)
    product_rows = products(rng)
    line_rows = order_lines(rng, order_rows, product_rows)
    promotion_rows = promotions(rng, product_rows)
    store_rows = [[str(store_id), name, city, region] for store_id, name, city, region in STORES]
    write(
        target,
        "customers.csv",
        [
            "customer_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "national_id",
            "birth_date",
            "city",
            "loyalty_tier",
        ],
        customer_rows,
    )
    write(target, "orders.csv", ["order_id", "customer_id", "store_id", "order_date", "status"], order_rows)
    write(target, "order_lines.csv", ["order_id", "line_no", "product_id", "quantity", "unit_price"], line_rows)
    write(target, "products.csv", ["product_id", "name", "category", "list_price"], product_rows)
    write(target, "stores.csv", ["store_id", "name", "city", "region"], store_rows)
    write(
        target,
        "promotions.csv",
        ["promotion_id", "product_id", "start_date", "end_date", "discount_pct"],
        promotion_rows,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
