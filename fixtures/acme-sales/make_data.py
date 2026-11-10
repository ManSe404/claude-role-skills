#!/usr/bin/env python3
"""Generate the sample data of the acme-sales fixture into extras/data/ and the report's numbers into files/.

Usage: python3 fixtures/acme-sales/make_data.py [TARGET_DIR]

Everything is made up: Acme Home Goods, its six stores and every person. E-mails are at example.com and phones are
in the 555 range. Only `Random.random()` is used, because it is the one method whose sequence Python guarantees across
versions, so the same seed gives the same bytes on every interpreter.

Rows are built as blocks with an exact number of units and an exact sum in cents, so each planted effect is an exact
number and not an accident of the random draw. The tests recompute all of it from the CSVs:

- net revenue (finance definition) goes from 96,000.00 in September to 85,390.00 in October, mostly through mix;
- 4,200.00 of October arrived late (order day 27 October, loaded after the 2 November run), so the number reported
  on that run, 81,190.00, shows a drop that is partly fake;
- the ERP and the finance ledger differ for October by causes that add up to the whole gap;
- the October review report double counts through a promotion join, drops NULL regions with `<>`, uses logged-in
  sessions as its denominator, averages store averages, compares 24 days of September with all of October, ranks a
  store with 6 orders first and hides a Simpson's reversal between devices.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
TARGET = HERE / "extras" / "data"
REPORT = HERE / "files" / "reports" / "october_review"
SEED = 20261102

FIRST_NAMES = ["Ana", "Bojan", "Danica", "Goran", "Ivana", "Jasna", "Lazar", "Marija", "Nada", "Petar", "Sava", "Vera"]
LAST_NAMES = ["Borović", "Cerović", "Dubović", "Grabić", "Hrastić", "Javorac", "Kestenić", "Lipić", "Topolić", "Vrbić"]

# (month, line): (units, cents) of completed orders; the exact totals every planted split is built from.
TOTALS = {
    (9, "premium"): (400, 4_000_000),
    (9, "standard"): (800, 4_000_000),
    (9, "value"): (800, 1_600_000),
    (10, "premium"): (260, 2_600_000),
    (10, "standard"): (820, 4_059_000),
    (10, "value"): (940, 1_880_000),
}
ORDINARY_ROWS = {
    (9, "premium"): 170,
    (9, "standard"): 335,
    (9, "value"): 340,
    (10, "premium"): 100,
    (10, "standard"): 300,
    (10, "value"): 337,
}
AS_OF = "2026-11-02T06:00:00Z"


@dataclass
class Block:
    tag: str
    month: int
    line: str
    units: int
    cents: int
    rows: int
    whole_euros: bool = False
    channel: str | None = None
    store_id: int | None = None
    region: str | None = None  # empty string means no region at all


# Every special block sits inside one of the totals above; the ordinary rows get what is left of each total.
BLOCKS = [
    Block("late", 10, "premium", 30, 300_000, 18),
    Block("late", 10, "standard", 24, 120_000, 14),
    Block("not_invoiced", 10, "value", 20, 41_260, 6),
    Block("staff", 10, "standard", 12, 59_000, 8, channel="staff"),
    Block("staff", 9, "standard", 10, 50_000, 5, channel="staff"),
    Block("tz_out", 10, "value", 21, 43_120, 5),
    Block("tz_in", 9, "standard", 8, 31_800, 4, whole_euros=True),
    Block("timing", 10, "standard", 14, 77_770, 7),
    Block("manual", 10, "premium", 3, 36_000, 3, whole_euros=True),
    Block("dup_b", 10, "value", 13, 26_800, 4, whole_euros=True),
    Block("null_region", 10, "standard", 62, 311_450, 30, region=""),
    Block("double_promo", 10, "standard", 64, 321_000, 40),
    Block("store6", 10, "premium", 12, 144_000, 6, channel="store", store_id=6),
]
OCT_WEB_ORDERS = 600
OCT_STORE_ROWS = {1: 120, 2: 70, 3: 40, 4: 20, 5: 14}
MANUAL_DIFFS = [1_000, 2_000, 500]  # the ledger is lower by these, in cents

# (device, source): (sessions, orders) in October. Mobile beats desktop in every source, desktop wins overall.
SESSIONS = {
    ("desktop", "direct"): (4_000, 240),
    ("desktop", "search"): (2_000, 60),
    ("desktop", "paid_social"): (1_000, 10),
    ("mobile", "direct"): (1_000, 70),
    ("mobile", "search"): (1_000, 35),
    ("mobile", "paid_social"): (14_000, 185),
}


@dataclass
class Order:
    block: str
    month: int
    line: str
    units: int
    cents: int
    status: str = "completed"
    channel: str = ""
    store_id: int | None = None
    region: str = ""
    ts: datetime = datetime(2000, 1, 1)
    loaded: datetime = datetime(2000, 1, 1)
    order_id: str = ""
    fee_cents: int = 0
    shipped: date | None = None
    customer: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def split_exact(total: int, parts: int, rng: random.Random, low: int = 1, jitter: float = 0.35) -> list[int]:
    """`parts` integers of at least `low` that sum exactly to `total`, each near the mean."""
    weights = [1 + jitter * (2 * rng.random() - 1) for _ in range(parts)]
    return split_weighted(total, weights, low)


def split_weighted(total: int, weights: list[float], low: int) -> list[int]:
    scale = sum(weights)
    shares = [max(low, int(total * w / scale)) for w in weights]
    diff = total - sum(shares)
    i = 0
    while diff:
        j = i % len(shares)
        if diff > 0:
            shares[j] += 1
            diff -= 1
        elif shares[j] > low:
            shares[j] -= 1
            diff += 1
        i += 1
    return shares


def build_block(block: Block, rng: random.Random) -> list[Order]:
    units = split_exact(block.units, block.rows, rng, low=1)
    if block.whole_euros:
        euros = split_weighted(block.cents // 100, [u * (0.9 + 0.2 * rng.random()) for u in units], 1)
        cents = [e * 100 for e in euros]
    else:
        cents = split_weighted(block.cents, [u * (0.85 + 0.3 * rng.random()) for u in units], 100)
    return [
        Order(block.tag, block.month, block.line, u, c, channel=block.channel or "", store_id=block.store_id)
        for u, c in zip(units, cents, strict=True)
    ]


def stamp(order: Order, rng: random.Random) -> None:
    """Dates per block: late rows sit on 27 October, boundary rows on the two month ends in the UTC clock."""
    if order.block == "late":
        day = date(2026, 10, 27)
        hour = 8 + int(rng.random() * 12)
    elif order.block == "tz_out":
        day, hour = date(2026, 10, 31), 23
    elif order.block == "tz_in":
        day, hour = date(2026, 9, 30), 22
    elif order.block == "timing":
        day, hour = date(2026, 10, 28 + int(rng.random() * 3)), 9 + int(rng.random() * 10)
    else:
        days = 30 if order.month == 9 else 31
        day = date(2026, order.month, 1 + int(rng.random() * days))
        hour = 8 + int(rng.random() * 12)
    order.ts = datetime(day.year, day.month, day.day, hour, int(rng.random() * 60), int(rng.random() * 60))
    if order.block == "late":
        order.loaded = datetime(2026, 11, 4, 3, 15, int(rng.random() * 60))
    else:
        order.loaded = datetime(day.year, day.month, day.day, 0, 0, 0) + timedelta(
            days=1, hours=2, minutes=int(rng.random() * 50), seconds=int(rng.random() * 60)
        )
    if order.status == "cancelled":
        order.shipped = None
    else:
        order.shipped = day + timedelta(days=int(rng.random() * 4))


def make_orders(rng: random.Random) -> tuple[list[Order], list[tuple[str, str, str, int]]]:
    orders: list[Order] = []
    used = dict.fromkeys(TOTALS, (0, 0))
    for block in BLOCKS:
        key = (block.month, block.line)
        used[key] = (used[key][0] + block.units, used[key][1] + block.cents)
        orders += build_block(block, rng)
    for key, (units, cents) in TOTALS.items():
        rest = Block("ordinary", key[0], key[1], units - used[key][0], cents - used[key][1], ORDINARY_ROWS[key])
        orders += build_block(rest, rng)
    # Returned and cancelled orders sit outside the finance number, so they never touch the totals above.
    for month in (9, 10):
        for status, count, each in (("returned", 16 + month, 9_000), ("cancelled", 12, 3_500)):
            for _ in range(count):
                cents = int(each * (0.6 + 0.8 * rng.random()))
                line = ["premium", "standard", "value"][int(rng.random() * 3)]
                orders.append(Order("other", month, line, 1 + int(rng.random() * 3), cents, status=status))
    for order in orders:
        stamp(order, rng)
    _assign_channels(orders, rng)
    regions = ["north", "south", "west"]
    for order in orders:
        if order.block == "null_region":
            order.region = ""
        else:
            order.region = regions[int(rng.random() * 3)]
        if order.channel == "web":
            order.fee_cents = 490 if order.cents < 5_000 else 0
        order.customer = 1 + int(rng.random() * 400)
    oct_completed = sorted(
        (o for o in orders if o.month == 10 and o.status == "completed" and o.block == "ordinary"),
        key=lambda o: (o.ts, o.cents),
    )
    for order in oct_completed[::120][:6]:
        order.region = "unknown"
    orders.sort(key=lambda o: (o.ts, o.loaded, o.units, o.cents, o.line))
    for number, order in enumerate(orders, start=100_001):
        order.order_id = f"SO-{number}"
    promotions: list[tuple[str, str, str, int]] = []
    for order in orders:
        if order.block == "double_promo":
            promotions.append((order.order_id, "AUTUMN10", "standard", 500))
            promotions.append((order.order_id, "LOYALTY5", "standard", 250))
        elif order.status == "completed" and rng.random() < 0.18:
            promotions.append((order.order_id, "WELCOME5", order.line, 500))
    return orders, promotions


def _assign_channels(orders: list[Order], rng: random.Random) -> None:
    fixed = [o for o in orders if o.channel]
    for order in fixed:
        if order.channel == "store" and order.store_id is None:
            order.store_id = 1 + int(rng.random() * 5)
    open_october = [o for o in orders if not o.channel and o.month == 10 and o.status == "completed"]
    keyed = sorted(open_october, key=lambda o: rng.random())
    webs = keyed[:OCT_WEB_ORDERS]
    stores = keyed[OCT_WEB_ORDERS:]
    for order in webs:
        order.channel = "web"
    position = 0
    for store, count in OCT_STORE_ROWS.items():
        for order in stores[position : position + count]:
            order.channel = "store"
            order.store_id = store
        position += count
    assert position == len(stores), (position, len(stores))
    for order in orders:
        if not order.channel:
            if rng.random() < 0.65:
                order.channel = "web"
            else:
                order.channel = "store"
                order.store_id = 1 + int(rng.random() * 6)


def money(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def ledger_rows(orders: list[Order], rng: random.Random) -> list[list[str]]:
    rows: list[list[str]] = []
    posted: list[Order] = [o for o in orders if o.status == "completed" and o.block not in ("staff", "not_invoiced")]
    manual = iter(MANUAL_DIFFS)
    for order in posted:
        offset = 1 if order.ts >= datetime(2026, 10, 25) else 2
        moment = order.ts + timedelta(hours=offset)
        if order.block == "timing":
            moment = datetime(2026, 11, 3 + int(rng.random() * 4), 7, int(rng.random() * 60), int(rng.random() * 60))
        cents = (order.cents + 50) // 100 * 100
        if order.block == "manual":
            cents = order.cents - next(manual)
        rows.append([order.order_id, moment.strftime("%Y-%m-%d %H:%M:%S"), money(cents)])
        if order.block == "dup_b":
            rows.append([order.order_id, moment.strftime("%Y-%m-%d %H:%M:%S"), money(cents)])
    rows.append(["MAN-0001", "2026-10-29 10:00:00", "100.00"])
    rows.append(["MAN-0002", "2026-10-30 11:30:00", "50.00"])
    rows.sort(key=lambda r: (r[1], r[0]))
    return rows


def write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def customers(rng: random.Random) -> list[list[str]]:
    rows = []
    for i in range(1, 401):
        first = FIRST_NAMES[int(rng.random() * len(FIRST_NAMES))]
        last = LAST_NAMES[int(rng.random() * len(LAST_NAMES))]
        ascii_name = last.lower().translate(str.maketrans("šćčžđ", "sccel"))
        rows.append(
            [
                f"C{i:04d}",
                f"{first} {last}",
                f"{first.lower()}.{ascii_name}{i}@example.com",
                f"+381 11 555 {1000 + i}",
                ["consumer", "consumer", "consumer", "trade"][int(rng.random() * 4)],
            ]
        )
    return rows


def sessions_rows(rng: random.Random) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for (device, source), (sessions, orders) in SESSIONS.items():
        logged = (sessions // 2, sessions - sessions // 2)
        ordered = (orders // 2, orders - orders // 2)
        for flag, count, won in ((True, logged[0], ordered[0]), (False, logged[1], ordered[1])):
            daily = split_exact(count, 31, rng, low=1, jitter=0.25)
            daily_orders = split_exact(won, 31, rng, low=0, jitter=0.5)
            for day in range(31):
                rows.append(
                    [f"2026-10-{day + 1:02d}", device, source, str(flag).lower(), daily[day], daily_orders[day]]
                )
    rows.sort(key=lambda r: (r[0], r[1], r[2], r[3]))
    return rows


def report_numbers(orders: list[Order], promotions: list[tuple[str, str, str, int]]) -> dict[str, Any]:
    oct_done = [o for o in orders if o.month == 10 and o.status == "completed"]
    promo_rows: dict[str, int] = {}
    for order_id, *_ in promotions:
        promo_rows[order_id] = promo_rows.get(order_id, 0) + 1
    # revenue_by_line.sql: every promotion row repeats the order, so an order with two promotions counts twice.
    by_line: dict[str, int] = {}
    for order in oct_done:
        by_line[order.line] = by_line.get(order.line, 0) + order.cents * max(1, promo_rows.get(order.order_id, 0))
    # revenue_by_region.sql: `region <> 'unknown'` also drops every row whose region is NULL.
    by_region: dict[str, int] = {}
    for order in oct_done:
        if order.region and order.region != "unknown":
            by_region[order.region] = by_region.get(order.region, 0) + order.cents
    stores: dict[int, list[int]] = {}
    for order in oct_done:
        if order.channel == "store" and order.store_id is not None:
            stores.setdefault(order.store_id, []).append(order.cents)
    store_avgs = {sid: sum(v) / len(v) for sid, v in stores.items()}
    avg_of_avgs = round(sum(store_avgs.values()) / len(store_avgs) / 100, 2)
    sep_24 = sum(
        o.cents for o in orders if o.month == 9 and o.status == "completed" and o.ts.date() <= date(2026, 9, 24)
    )
    oct_total = sum(o.cents for o in oct_done)
    uplift = round(100 * (oct_total - sep_24) / sep_24, 1)
    web_orders = sum(1 for o in oct_done if o.channel == "web")
    return {
        "by_line": by_line,
        "by_region": by_region,
        "stores": {sid: (len(v), sum(v)) for sid, v in sorted(stores.items())},
        "avg_of_avgs": avg_of_avgs,
        "sep_24": sep_24,
        "oct_total": oct_total,
        "uplift": uplift,
        "web_orders": web_orders,
    }


REPORT_MD = """# October sales review (draft for the Friday meeting)

Prepared by Milena Hrast on 5 November 2026 for the leadership team. Numbers come from the queries in this folder;
their output is saved under `output/`. Data was refreshed on 5 November.

## Headlines

1. Net revenue in October was EUR {oct_inflated}, led by the standard line (`revenue_by_line.sql`).
2. By region, the three regions together brought EUR {region_total} (`revenue_by_region.sql`).
3. October is up {uplift}% on September, EUR {oct_total} against EUR {sep_24} (`sep_vs_oct.sql`).
4. Web conversion was {conversion}% in October, against a target of 4% (`conversion.sql`).
5. Desktop converts at {desktop}% and mobile at {mobile}%, so we propose moving mobile budget to desktop
   (`conversion_by_device.sql`).
6. The average order in a store was EUR {avg_of_avgs}. Store 6 is our best store with an average order of
   EUR {store6_avg}, and we propose it as the model for the others (`avg_order_by_store.sql`).

## Monthly revenue

The chart in `monthly_chart.ipynb` shows September and October side by side. Orders by status are in
`orders_by_status.sql`, for reference.
"""


def write_report(numbers: dict[str, Any], orders: list[Order], target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    output = target / "output"
    output.mkdir(parents=True, exist_ok=True)
    by_line = sorted(numbers["by_line"].items())
    write_csv(
        output / "revenue_by_line.csv",
        ["product_line", "net_revenue"],
        [[k, money(v)] for k, v in by_line],
    )
    by_region = sorted(numbers["by_region"].items())
    write_csv(output / "revenue_by_region.csv", ["region", "net_revenue"], [[k, money(v)] for k, v in by_region])
    write_csv(
        output / "sep_vs_oct.csv",
        ["period", "net_revenue"],
        [["2026-09", money(numbers["sep_24"])], ["2026-10", money(numbers["oct_total"])]],
    )
    conversion = numbers["web_orders"] / 11_500
    write_csv(
        output / "conversion.csv",
        ["month", "orders", "sessions", "conversion_pct"],
        [["2026-10", numbers["web_orders"], 11_500, f"{conversion * 100:.2f}"]],
    )
    devices = {
        "desktop": (sum(v[1] for k, v in SESSIONS.items() if k[0] == "desktop"), 7_000),
        "mobile": (sum(v[1] for k, v in SESSIONS.items() if k[0] == "mobile"), 16_000),
    }
    write_csv(
        output / "conversion_by_device.csv",
        ["device", "orders", "sessions", "conversion_pct"],
        [[d, o, s, f"{100 * o / s:.2f}"] for d, (o, s) in devices.items()],
    )
    write_csv(
        output / "avg_order_by_store.csv",
        ["store_id", "orders", "avg_order"],
        [[sid, n, f"{total / n / 100:.2f}"] for sid, (n, total) in numbers["stores"].items()],
    )
    statuses: dict[str, int] = {}
    for order in orders:
        if order.month == 10:
            statuses[order.status] = statuses.get(order.status, 0) + 1
    write_csv(output / "orders_by_status.csv", ["status", "orders"], sorted([k, v] for k, v in statuses.items()))
    n6, total6 = numbers["stores"][6]
    (target / "report.md").write_text(
        REPORT_MD.format(
            oct_inflated=money(sum(numbers["by_line"].values())),
            region_total=money(sum(numbers["by_region"].values())),
            uplift=numbers["uplift"],
            oct_total=money(numbers["oct_total"]),
            sep_24=money(numbers["sep_24"]),
            conversion=f"{conversion * 100:.2f}",
            desktop=f"{100 * devices['desktop'][0] / devices['desktop'][1]:.2f}",
            mobile=f"{100 * devices['mobile'][0] / devices['mobile'][1]:.2f}",
            avg_of_avgs=f"{numbers['avg_of_avgs']:.2f}",
            store6_avg=f"{total6 / n6 / 100:.2f}",
        ),
        encoding="utf-8",
    )
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": ["# Monthly net revenue\n", "Bars for the Friday deck, from `output/sep_vs_oct.csv`.\n"],
            },
            {
                "cell_type": "code",
                "execution_count": 1,
                "metadata": {},
                "outputs": [],
                "source": [
                    "import matplotlib.pyplot as plt\n",
                    "\n",
                    "months = ['2026-09', '2026-10']\n",
                    f"revenue = [{numbers['sep_24'] / 100:.2f}, {numbers['oct_total'] / 100:.2f}]\n",
                    "fig, ax = plt.subplots()\n",
                    "ax.bar(months, revenue)\n",
                    "ax.set_ylim(70_000, 90_000)\n",
                    "ax.set_title('Net revenue is growing')\n",
                ],
            },
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (target / "monthly_chart.ipynb").write_text(json.dumps(notebook, indent=1) + "\n", encoding="utf-8")


def generate(data_dir: Path, report_dir: Path) -> None:
    rng = random.Random(SEED)
    orders, promotions = make_orders(rng)
    people = customers(rng)
    names = {row[0]: row for row in people}
    data_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        data_dir / "orders.csv",
        [
            "order_id",
            "order_ts",
            "order_date",
            "shipped_date",
            "loaded_at",
            "channel",
            "store_id",
            "region",
            "product_line",
            "customer_id",
            "customer_name",
            "customer_email",
            "units",
            "net_amount",
            "shipping_fee",
            "status",
        ],
        [
            [
                o.order_id,
                o.ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                o.ts.date().isoformat(),
                o.shipped.isoformat() if o.shipped else "",
                o.loaded.strftime("%Y-%m-%dT%H:%M:%SZ"),
                o.channel,
                o.store_id if o.store_id is not None else "",
                o.region,
                o.line,
                f"C{o.customer:04d}",
                names[f"C{o.customer:04d}"][1],
                names[f"C{o.customer:04d}"][2],
                o.units,
                money(o.cents),
                money(o.fee_cents),
                o.status,
            ]
            for o in orders
        ],
    )
    ledger = ledger_rows(orders, rng)
    write_csv(
        data_dir / "ledger.csv",
        ["ledger_id", "order_id", "posted_at", "account", "amount", "currency", "batch_id"],
        [
            [
                f"L{number:06d}",
                order_id,
                posted,
                "4000-SALES",
                amount,
                "EUR",
                f"BATCH-{posted[:10].replace('-', '')}",
            ]
            for number, (order_id, posted, amount) in enumerate(ledger, start=1)
        ],
    )
    write_csv(
        data_dir / "order_promotions.csv",
        ["order_id", "promo_code", "applied_line", "promo_cents"],
        [list(p) for p in promotions],
    )
    write_csv(
        data_dir / "sessions.csv", ["day", "device", "source", "logged_in", "sessions", "orders"], sessions_rows(rng)
    )
    write_csv(data_dir / "customers.csv", ["customer_id", "full_name", "email", "phone", "segment"], people)
    write_report(report_numbers(orders, promotions), orders, report_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the acme-sales sample data.")
    parser.add_argument("target", type=Path, nargs="?", default=TARGET, help="folder for the CSVs")
    parser.add_argument("--report", type=Path, default=REPORT, help="folder for the report's numbers")
    args = parser.parse_args(argv)
    generate(args.target, args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
