#!/usr/bin/env python3
"""Generate the data of the acme-pipeline fixture: deliveries, ops records and a sample of a served table.

Usage: python3 fixtures/acme-pipeline/make_data.py [--extras DIR] [--ref DIR]

It writes extras/ (on disk in the built fixture, not committed) and files/ref/stores.csv (committed). Everything is
made up: Acme Foods, its 30 franchise stores, every person, e-mail (example.com and example.org), phone (the 555
range) and IBAN (a valid checksum on a made-up bank code). Only `Random.random()` is used, because it is the one
method whose sequence Python guarantees across versions, so the same seed gives the same bytes on every interpreter.

The ops records cover the deliveries of 2026-10-05 to 2026-11-04; each delivery holds the rows of the day before.
What is planted (tests/test_fixture_acme_pipeline.py holds the numbers and recomputes them from the files):

- the ERP orders export switches to a decimal comma on 2026-11-03, so silver.orders fails on 11-03 (twice) and 11-04
  and gold.sales_daily is last built on 11-02; the 11-04 export also drops `sales_rep_code`;
- the ERP files arrive around 07:30 on working days, after the 06:00 of the contract;
- a new store, S-031, orders from 2026-10-27 but is missing from ref/stores.csv, so its rows go to quarantine;
- the four Szeged stores are closed on Hungarian public holidays and bill a deposit in HUF on some days;
- the CRM test deliveries of 11-03 and 11-04 break the vendor's own document in the ways the source-profile skill
  must find;
- the billing export, the storage list and the query log hold the cost story.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
EXTRAS = HERE / "extras"
REF = HERE / "files" / "ref"
ORDERS_SQL = HERE / "files" / "pipeline" / "silver" / "orders.sql"
SEED = 20261104

FIRST_DELIVERY = date(2026, 10, 5)
LAST_DELIVERY = date(2026, 11, 4)
DELIVERIES = [FIRST_DELIVERY + timedelta(days=n) for n in range((LAST_DELIVERY - FIRST_DELIVERY).days + 1)]
ERP_ON_DISK = DELIVERIES[-3:]
CRM_DELIVERIES = [date(2026, 11, 3), date(2026, 11, 4)]
COMMA_FROM = date(2026, 11, 3)  # the ERP orders export writes amounts with a decimal comma from this delivery on
NO_SALES_REP_FROM = date(2026, 11, 4)  # and no longer carries sales_rep_code from this one
NEW_STORE = ("S-031", "C-20431", "SR-02")
NEW_STORE_FROM = date(2026, 10, 27)  # the order day of S-031's first orders
PLACEHOLDER_STORE = ("S-000", "C-00000", "SR-00")  # what the ERP fills in when a phone order has no store
HU_CLOSED = {date(2026, 10, 23), date(2026, 11, 1)}  # Hungarian public holidays: national day and All Saints
SUMMER_TIME_UNTIL = date(2026, 10, 25)  # Europe/Belgrade is +02:00 before this day and +01:00 from it
RERUN = (date(2026, 11, 3), 9 * 3600 + 12 * 60 + 8)  # the on-call engineer ran load_erp_orders again at 09:12

# store_id, name, city, country, currency, franchisee customer_id, franchisee name, sales rep, opened_on
STORES = [
    ("S-001", "Acme Market Novi Sad Centar", "Novi Sad", "RS", "RSD", "Zoran", "Milić", "2018-03-01"),
    ("S-002", "Acme Market Novi Sad Liman 1", "Novi Sad", "RS", "RSD", "Vesna", "Kordić", "2018-05-14"),
    ("S-003", "Acme Market Novi Sad Liman 2", "Novi Sad", "RS", "RSD", "Dejan", "Stepić", "2019-02-04"),
    ("S-004", "Acme Market Novi Sad Detelinara", "Novi Sad", "RS", "RSD", "Snežana", "Bulović", "2019-06-17"),
    ("S-005", "Acme Market Novi Sad Grbavica", "Novi Sad", "RS", "RSD", "Miloš", "Kerac", "2019-09-02"),
    ("S-006", "Acme Market Novi Sad Klisa", "Novi Sad", "RS", "RSD", "Jelena", "Vranešević", "2020-03-09"),
    ("S-007", "Acme Market Petrovaradin", "Novi Sad", "RS", "RSD", "Goran", "Lalošević", "2020-05-25"),
    ("S-008", "Acme Market Sremska Kamenica", "Novi Sad", "RS", "RSD", "Marija", "Teofanov", "2020-10-12"),
    ("S-009", "Acme Market Zrenjanin", "Zrenjanin", "RS", "RSD", "Nenad", "Šuvakov", "2021-02-01"),
    ("S-010", "Acme Market Subotica", "Subotica", "RS", "RSD", "Ivana", "Dulić", "2021-04-19"),
    ("S-011", "Acme Market Sombor", "Sombor", "RS", "RSD", "Branislav", "Ćosić", "2021-06-07"),
    ("S-012", "Acme Market Kikinda", "Kikinda", "RS", "RSD", "Danijela", "Mrkšić", "2021-09-13"),
    ("S-013", "Acme Market Pančevo", "Pančevo", "RS", "RSD", "Aleksandar", "Vučetin", "2022-01-17"),
    ("S-014", "Acme Market Sremska Mitrovica", "Sremska Mitrovica", "RS", "RSD", "Tamara", "Brkljač", "2022-03-21"),
    ("S-015", "Acme Market Vršac", "Vršac", "RS", "RSD", "Slobodan", "Jovin", "2022-05-30"),
    ("S-016", "Acme Market Vrbas", "Vrbas", "RS", "RSD", "Milica", "Gajin", "2022-08-22"),
    ("S-017", "Acme Market Bačka Palanka", "Bačka Palanka", "RS", "RSD", "Radovan", "Kosovac", "2022-10-03"),
    ("S-018", "Acme Market Ruma", "Ruma", "RS", "RSD", "Ljiljana", "Petkov", "2023-02-06"),
    ("S-019", "Acme Market Inđija", "Inđija", "RS", "RSD", "Vladimir", "Ostojin", "2023-04-24"),
    ("S-020", "Acme Market Stara Pazova", "Stara Pazova", "RS", "RSD", "Sanja", "Ratkov", "2023-06-12"),
    ("S-021", "Acme Market Bečej", "Bečej", "RS", "RSD", "Predrag", "Zubić", "2023-09-04"),
    ("S-022", "Acme Market Kula", "Kula", "RS", "RSD", "Gordana", "Mamuzić", "2024-01-15"),
    ("S-023", "Acme Market Temerin", "Temerin", "RS", "RSD", "Đorđe", "Pejin", "2024-03-18"),
    ("S-024", "Acme Market Šid", "Šid", "RS", "RSD", "Nataša", "Bajić", "2024-05-27"),
    ("S-025", "Acme Market Senta", "Senta", "RS", "RSD", "Ištvan", "Varga", "2024-09-09"),
    ("S-026", "Acme Market Apatin", "Apatin", "RS", "RSD", "Biljana", "Rašeta", "2025-02-03"),
    ("S-027", "Acme Market Szeged Belváros", "Szeged", "HU", "EUR", "Bence", "Szalai", "2025-04-07"),
    ("S-028", "Acme Market Szeged Újszeged", "Szeged", "HU", "EUR", "Réka", "Halász", "2025-06-02"),
    ("S-029", "Acme Market Szeged Tarján", "Szeged", "HU", "EUR", "Ádám", "Kerekes", "2025-09-15"),
    ("S-030", "Acme Market Szeged Kiskundorozsma", "Szeged", "HU", "EUR", "Zsófia", "Bodor", "2026-03-02"),
]

# product_id, price in RSD cents, weight in grams per piece
PRODUCTS = [
    ("P-1001", 8900, 1000),
    ("P-1002", 11900, 1000),
    ("P-1003", 22900, 920),
    ("P-1004", 13900, 1030),
    ("P-1005", 18900, 1000),
    ("P-1006", 68900, 500),
    ("P-1007", 34900, 250),
    ("P-1008", 25900, 600),
    ("P-1009", 39900, 200),
    ("P-1010", 14900, 40),
    ("P-1011", 11900, 500),
    ("P-1012", 19900, 1000),
    ("P-1013", 22900, 500),
    ("P-1014", 9900, 400),
    ("P-1015", 44900, 680),
    ("P-1016", 29900, 400),
    ("P-1017", 119900, 900),
    ("P-1018", 16900, 100),
    ("P-1019", 15900, 300),
    ("P-1020", 7900, 1550),
    ("P-1021", 18900, 1050),
    ("P-1022", 10900, 540),
    ("P-1023", 149900, 1000),
    ("P-1024", 21900, 450),
]
DEPOSIT = ("P-9001", 5000, 0)  # the Hungarian bottle deposit, 50 HUF a piece, billed in HUF

TRANSLITERATE = str.maketrans(
    {"č": "c", "ć": "c", "š": "s", "ž": "z", "đ": "dj", "Č": "C", "Ć": "C", "Š": "S", "Ž": "Z", "Đ": "Dj",
     "á": "a", "é": "e", "í": "i", "ó": "o", "ö": "o", "ő": "o", "ú": "u", "ü": "u", "ű": "u", "Á": "A", "Ú": "U"}
)  # fmt: skip
FIRST_NAMES = [
    "Ana", "Bojan", "Danica", "Dragan", "Ivana", "Jasmina", "Lazar", "Marko", "Mirjana", "Nikolina", "Ognjen",
    "Petra", "Radmila", "Saša", "Stevan", "Svetlana", "Uroš", "Vera", "Zlatko", "Željka",
]  # fmt: skip
LAST_NAMES = [
    "Andrić", "Babin", "Crnjanski", "Dragić", "Ergić", "Grujin", "Ilić", "Jakšić", "Kovačev", "Lukin", "Malešev",
    "Nedić", "Oljača", "Pavlov", "Radić", "Simin", "Tomić", "Uzelac", "Vasin", "Zec",
]  # fmt: skip
CITIES = ["Novi Sad", "Zrenjanin", "Subotica", "Sombor", "Kikinda", "Pančevo", "Vršac", "Ruma", "Bečej", "Inđija"]
COMPANY_KINDS = ["Market", "Prodavnica", "Pekara", "Kafana", "Restoran", "Mini market", "Diskont", "Bistro"]
COMPANY_WORDS = ["Lipa", "Bagrem", "Dunav", "Ravnica", "Salaš", "Fruška", "Tisa", "Begej", "Klas", "Jasen", "Breza"]
JOB_TITLES = ["vlasnik", "direktor", "nabavka", "šef smene", "računovodstvo", "menadžer prodavnice"]
SUBJECTS = {
    "visit": "Obilazak prodavnice",
    "call": "Dogovor o porudžbini",
    "offer": "Ponuda za novogodišnji asortiman",
    "complaint": "Reklamacija na isporuku",
}
CHANNELS = {"visit": "field", "call": "phone", "offer": "email", "complaint": "phone"}

# CRM planted counts: fixed numbers, placed at drawn rows
CRM_ACCOUNTS = 609  # distinct customer_id in the 11-04 delivery; the two newest are missing from 11-03
CRM_DUPLICATED = 5
CRM_INACTIVE = 38
CRM_CLOSED_X = 7
CRM_MIGRATED = 23  # created_on 1900-01-01: opened before the CRM, date unknown
CRM_CONTACTS = 911
CRM_NEW_CONTACTS = 6  # missing from 11-03
CRM_ORPHANS = 14
CRM_NULL_TOKENS = {"": 41, "N/A": 17, "NULL": 9, "-": 12}
CRM_DMY_CONSENT = 58
CRM_IBANS = 126
CRM_LEGACY_REFS = 540
CRM_ACTIVITIES = {date(2026, 11, 3): 243, date(2026, 11, 4): 268}

QUERY_PLAN = [  # consumer, table, queries on a working day, queries on a weekend day
    ("bi_sales_board", "gold.sales_daily", 24, 24),
    ("store_ops_app", "gold.sales_daily", 24, 24),
    ("franchise_portal", "gold.sales_daily", 24, 24),
    ("regional_managers_report", "gold.sales_daily", 24, 24),
    ("finance_cash_plan", "gold.sales_daily", 1, 1),
    ("finance_cash_plan", "silver.invoices", 1, 1),
    ("finance_cash_plan", "silver.payments", 1, 1),
    ("stock_planner", "gold.stock_levels", 2, 1),
    ("key_account_team", "silver.customers", 3, 0),
]
STORAGE = [  # table, layer, GB; 0.04 EUR per GB and month
    ("bronze.erp_orders_history_full", "bronze", "812.00"),
    ("bronze.erp_orders", "bronze", "46.50"),
    ("silver.orders", "silver", "38.75"),
    ("bronze.erp_invoices", "bronze", "9.25"),
    ("silver.invoices", "silver", "7.50"),
    ("bronze.erp_payments", "bronze", "3.50"),
    ("silver.payments", "silver", "2.75"),
    ("gold.sales_daily", "gold", "2.25"),
    ("bronze.erp_returns", "bronze", "1.25"),
    ("silver.returns", "silver", "1.00"),
    ("silver.customers", "silver", "0.50"),
    ("gold.stock_levels", "gold", "0.25"),
]
ETL_EUR_PER_HOUR = 200  # cents
DEV_EUR_PER_HOUR = 120  # cents
STORAGE_CENTS_PER_GB = 4
MISSING_TAX_ID = ["C-21877", "C-23310"]
MISSING_TAX_ID_FROM = (date(2026, 10, 20), "C-24102")
CUSTOMERS_START = 24_180


class Draw:
    """Random draws built on Random.random() alone, so the same seed gives the same data on every Python."""

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def unit(self) -> float:
        return self.rng.random()

    def between(self, low: int, high: int) -> int:
        return low + int(self.rng.random() * (high - low + 1))

    def pick(self, items: list[Any]) -> Any:
        return items[int(self.rng.random() * len(items))]

    def chance(self, p: float) -> bool:
        return self.rng.random() < p

    def sample(self, n: int, k: int) -> list[int]:
        """k distinct whole numbers below n, in random order."""
        keys = [(self.rng.random(), i) for i in range(n)]
        return [i for _, i in sorted(keys)[:k]]


@dataclass
class Line:
    order_id: str
    line_no: int
    order_date: date
    store_id: str
    customer_id: str
    product_id: str
    quantity: int
    weight_g: int
    amount: int  # cents
    currency: str
    status: str
    sales_rep_code: str


def customer_of(index: int) -> str:
    return f"C-{20101 + index}"


def email_of(first: str, last: str, domain: str = "example.com") -> str:
    return f"{first}.{last}@{domain}".translate(TRANSLITERATE).lower()


def money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def comma(cents: int) -> str:
    return money(cents).replace(".", ",")


def serbian(cents: int) -> str:
    """1234550 -> 12.345,50: a dot between thousands and a decimal comma."""
    whole = f"{cents // 100:,}".replace(",", ".")
    return f"{whole},{cents % 100:02d}"


def offset(day: date) -> str:
    return "+02:00" if day < SUMMER_TIME_UNTIL else "+01:00"


def stamp(day: date, seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    return f"{day.isoformat()}T{hours:02d}:{rest // 60:02d}:{rest % 60:02d}{offset(day)}"


def clock(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}"


def eur_price(rsd_cents: int) -> int:
    return (rsd_cents * 10 + 586) // 1172


Item = tuple[str, int, int, int, str]  # product_id, quantity, weight in grams, amount in cents, currency


def day_lines(draw: Draw, day: date) -> list[Line]:
    """The ERP order lines of one order day: every store, the new store from its first day and the placeholder."""
    lines: list[Line] = []
    orders = [0]

    def add_order(store_id: str, customer_id: str, rep: str, items: list[Item]) -> None:
        orders[0] += 1
        order_id = f"SO-{day:%y%m%d}-{orders[0]:04d}"
        for line_no, (product_id, quantity, weight, amount, currency) in enumerate(items, start=1):
            status = "cancelled" if draw.chance(0.025) else "delivered"
            lines.append(
                Line(order_id, line_no, day, store_id, customer_id, product_id, quantity, weight, amount, currency,
                     status, rep)
            )  # fmt: skip

    def items_for(currency: str, count: int) -> list[Item]:
        items = []
        for _ in range(count):
            product_id, price, weight = draw.pick(PRODUCTS)
            quantity = 6 * draw.between(1, 16)
            unit = eur_price(price) if currency == "EUR" else price
            items.append((product_id, quantity, quantity * weight, quantity * unit, currency))
        return items

    sources = [(s[0], customer_of(i), f"SR-{1 + i % 8:02d}", s[3], s[4]) for i, s in enumerate(STORES)]
    if day >= NEW_STORE_FROM:
        sources.append((*NEW_STORE, "RS", "RSD"))
    sources.append((*PLACEHOLDER_STORE, "RS", "RSD"))
    for store_id, customer_id, rep, country, currency in sources:
        if country == "HU" and day in HU_CLOSED:
            continue
        if store_id == PLACEHOLDER_STORE[0]:
            for item in items_for(currency, draw.between(3, 7)):
                add_order(store_id, customer_id, rep, [item])
            continue
        if store_id == NEW_STORE[0]:
            count = draw.between(102, 124)
        else:
            count = draw.between(8, 16) if day.weekday() == 6 else draw.between(24, 36)
        items = items_for(currency, count)
        start = 0
        while start < len(items):
            size = draw.between(1, 6)
            add_order(store_id, customer_id, rep, items[start : start + size])
            start += size
        if country == "HU" and draw.chance(0.4):
            quantity = 12 * draw.between(4, 20)
            add_order(store_id, customer_id, rep, [(DEPOSIT[0], quantity, 0, quantity * DEPOSIT[1], "HUF")])
    if day == date(2026, 11, 3):
        ordinary = [n for n, line in enumerate(lines) if line.currency == "RSD" and line.status == "delivered"]
        for n in (ordinary[len(ordinary) // 4], ordinary[len(ordinary) // 2], ordinary[3 * len(ordinary) // 4]):
            lines[n].status = "on_hold"
    return lines


def order_lines(draw: Draw) -> dict[date, list[Line]]:
    """The ERP order lines of every order day of the period, keyed by order day."""
    return {delivery - timedelta(days=1): day_lines(draw, delivery - timedelta(days=1)) for delivery in DELIVERIES}


def known_store(store_id: str) -> bool:
    return any(store_id == s[0] for s in STORES)


def write_csv(path: Path, header: list[str], rows: list[list[str]], delimiter: str = ",") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def erp_files(
    draw: Draw, lines_by_day: dict[date, list[Line]]
) -> dict[date, dict[str, tuple[list[str], list[list[str]]]]]:
    """The four ERP files of every delivery, as (header, rows); only the last three are written to disk."""
    result: dict[date, dict[str, tuple[list[str], list[list[str]]]]] = {}
    for delivery in DELIVERIES:
        day = delivery - timedelta(days=1)
        lines = lines_by_day[day]
        header = ["order_id", "line_no", "order_date", "store_id", "customer_id", "product_id", "quantity",
                  "weight_g", "amount", "currency", "status", "sales_rep_code"]  # fmt: skip
        shown = money if delivery < COMMA_FROM else comma
        if delivery >= NO_SALES_REP_FROM:
            header = header[:-1]
        orders = []
        for line in lines:
            row = [line.order_id, str(line.line_no), line.order_date.isoformat(), line.store_id, line.customer_id,
                   line.product_id, str(line.quantity), str(line.weight_g), shown(line.amount), line.currency,
                   line.status, line.sales_rep_code]  # fmt: skip
            orders.append(row[: len(header)])
        by_order: dict[str, list[Line]] = defaultdict(list)
        for line in lines:
            by_order[line.order_id].append(line)
        invoices = []
        for n, (order_id, order) in enumerate(by_order.items(), start=1):
            billed = sum(line.amount for line in order if line.status != "cancelled")
            if billed:
                invoices.append(
                    [f"INV-{day:%y%m%d}-{n:04d}", order_id, day.isoformat(), order[0].store_id, serbian(billed),
                     order[0].currency, (day + timedelta(days=30)).isoformat()]
                )  # fmt: skip
        returnable = [line for line in lines if line.status == "delivered" and line.product_id != DEPOSIT[0]]
        returns = []
        for n in range(1, draw.between(8, 20) + 1):
            line = draw.pick(returnable)
            back = min(line.quantity, draw.between(1, 6))
            returns.append(
                [f"RT-{day:%y%m%d}-{n:03d}", line.order_id, day.isoformat(), line.store_id,
                 money(line.amount // line.quantity * back), line.currency,
                 draw.pick(["damaged", "expired", "wrong_item", "quality"])]
            )  # fmt: skip
        payments = []
        for n in range(1, draw.between(60, 110) + 1):
            invoiced = day - timedelta(days=draw.between(25, 35))
            currency = "EUR" if draw.chance(0.1) else "RSD"
            amount = draw.between(2_000, 60_000) if currency == "EUR" else draw.between(50_000, 4_000_000)
            payments.append(
                [f"PM-{day:%y%m%d}-{n:03d}", f"INV-{invoiced:%y%m%d}-{draw.between(1, 250):04d}", day.isoformat(),
                 money(amount), currency, draw.pick(["transfer", "transfer", "transfer", "card", "cash"])]
            )  # fmt: skip
        result[delivery] = {
            "orders.csv": (header, orders),
            "invoices.csv": (
                ["invoice_id", "order_id", "invoice_date", "store_id", "amount", "currency", "due_date"],
                invoices,
            ),
            "returns.csv": (
                ["return_id", "order_id", "return_date", "store_id", "amount", "currency", "reason"],
                returns,
            ),
            "payments.csv": (["payment_id", "invoice_id", "paid_on", "amount", "currency", "method"], payments),
        }
    return result


def iban(draw: Draw) -> str:
    """A Serbian IBAN with a valid checksum on the made-up bank code 999."""
    bban = "999" + "".join(str(draw.between(0, 9)) for _ in range(15))
    check = 98 - int(bban + "272800") % 97
    return f"RS{check:02d}{bban}"


def crm_customers(draw: Draw) -> list[list[str]]:
    """All CRM accounts with the planted duplicates; the last two accounts are new on 11-04."""
    rows: list[list[str]] = []
    statuses = ["A"] * CRM_ACCOUNTS
    picked = draw.sample(CRM_ACCOUNTS - 2, CRM_INACTIVE + CRM_CLOSED_X)
    for index in picked[:CRM_INACTIVE]:
        statuses[index] = "I"
    for index in picked[CRM_INACTIVE:]:
        statuses[index] = "X"
    migrated = set(draw.sample(CRM_ACCOUNTS - 2, CRM_MIGRATED))
    for index in range(CRM_ACCOUNTS):
        new = index >= CRM_ACCOUNTS - 2
        created = date(2026, 11, 3) if new else date(2015, 1, 5) + timedelta(days=draw.between(0, 4280))
        status = statuses[index]
        closed = "9999-12-31" if status == "A" else (created + timedelta(days=draw.between(200, 900))).isoformat()
        if status != "A" and closed > "2026-10-31":
            closed = "2026-10-30"
        rows.append(
            [f"CRM-{10001 + index}", f"{draw.pick(COMPANY_KINDS)} {draw.pick(COMPANY_WORDS)} {draw.between(1, 40)}",
             f"1{draw.between(0, 99_999_999):08d}", draw.pick(["retail", "retail", "horeca", "franchise", "prospect"]),
             status, draw.pick(CITIES), "RS", money(100 * 1000 * draw.between(5, 400)),
             "1900-01-01" if index in migrated else created.isoformat(), closed, "", f"KAM-{draw.between(1, 9):02d}"]
        )  # fmt: skip
    originals = list(rows)
    for index in draw.sample(CRM_ACCOUNTS - 2, CRM_DUPLICATED):
        twin = list(originals[index])
        twin[5] = draw.pick([c for c in CITIES if c != twin[5]])
        twin[7] = money(100 * 1000 * draw.between(5, 400))
        position = rows.index(originals[index])
        rows.insert(draw.between(position + 1, len(rows) - 2), twin)
    return rows


def crm_contacts(draw: Draw, account_ids: list[str]) -> list[list[str]]:
    """All CRM contacts; the last six are new on 11-04 and belong to the two new accounts or to old ones."""
    old = CRM_CONTACTS - CRM_NEW_CONTACTS
    orphans = set(draw.sample(old, CRM_ORPHANS))
    tokens: dict[int, str] = {}
    free = draw.sample(old, sum(CRM_NULL_TOKENS.values()))
    start = 0
    for token, count in CRM_NULL_TOKENS.items():
        for index in free[start : start + count]:
            tokens[index] = token
        start += count
    dmy = set(draw.sample(old, CRM_DMY_CONSENT))
    ibans = set(draw.sample(old, CRM_IBANS))
    seen: dict[str, int] = defaultdict(int)
    rows: list[list[str]] = []
    for index in range(CRM_CONTACTS):
        if index in orphans:
            customer_id = f"CRM-{19001 + index}"
        elif index >= old:
            customer_id = account_ids[-1 - index % 2] if index % 3 else draw.pick(account_ids[:-2])
        else:
            customer_id = draw.pick(account_ids[:-2])
        first, last = draw.pick(FIRST_NAMES), draw.pick(LAST_NAMES)
        base = email_of(first, last, "example.org" if draw.chance(0.2) else "example.com")
        seen[base] += 1
        address = base if seen[base] == 1 else base.replace("@", f"{seen[base]}@")
        consent = date(2019, 1, 1) + timedelta(days=draw.between(0, 2860))
        rows.append(
            [f"CT-{50001 + index}", customer_id, first, last, tokens.get(index, draw.pick(JOB_TITLES)), address,
             f"+381 6{draw.between(0, 6)} 555 {draw.between(0, 9999):04d}", iban(draw) if index in ibans else "",
             consent.strftime("%d.%m.%Y") if index in dmy else consent.isoformat(),
             f"OLD-{index + 1:05d}" if index < CRM_LEGACY_REFS else ""]
        )  # fmt: skip
    return rows


def crm_activities(draw: Draw, delivery: date, account_ids: list[str], contacts: list[list[str]]) -> list[list[str]]:
    by_account: dict[str, list[str]] = defaultdict(list)
    for contact in contacts:
        by_account[contact[1]].append(contact[0])
    rows = []
    for n in range(CRM_ACTIVITIES[delivery]):
        customer_id = draw.pick(account_ids[:-2])
        kind = draw.pick(["visit", "visit", "call", "call", "call", "offer", "offer", "complaint"])
        people = by_account.get(customer_id, [])
        contact_id = draw.pick(people) if people and draw.chance(0.85) else ""
        value = serbian(100 * draw.between(800, 480_000)) if kind == "offer" else ""
        row = [f"ACT-{delivery:%m%d}{n + 1:04d}", customer_id, contact_id, (delivery - timedelta(days=1)).isoformat(),
               kind, CHANNELS[kind], SUBJECTS[kind], value, f"KAM-{draw.between(1, 9):02d}"]  # fmt: skip
        if delivery < date(2026, 11, 4):
            del row[5]
        rows.append(row)
    return rows


def cast_line() -> int:
    lines = ORDERS_SQL.read_text(encoding="utf-8").splitlines()
    return next(n for n, line in enumerate(lines, start=1) if "cast(amount as numeric" in line)


def arrival(draw: Draw, delivery: date) -> int:
    """Seconds after midnight when the ERP files came: before 06:00 at weekends, around 07:30 on working days."""
    if delivery.weekday() >= 5:
        return 5 * 3600 + 38 * 60 + draw.between(0, 18 * 60)
    return 7 * 3600 + 5 * 60 + draw.between(0, 33 * 60)


def ops(
    draw: Draw,
    lines_by_day: dict[date, list[Line]],
    files: dict[date, dict[str, tuple[list[str], list[list[str]]]]],
) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    deliveries: list[dict[str, Any]] = []
    usage: list[list[str]] = []
    queries: list[list[str]] = []
    customers = CUSTOMERS_START
    silver_rows = 2_961_208
    gold_rows = 24_315
    built_at = ""
    last_built = (FIRST_DELIVERY, 0)
    line_of_cast = cast_line()

    def task(
        run_id: str, job: str, name: str, layer: str, attempt: int, day: date, start: int, end: int, status: str,
        counts: tuple[int, int, int] = (0, 0, 0), error: str | None = None, message: str | None = None,
    ) -> None:  # fmt: skip
        runs.append(
            {"run_id": run_id, "job": job, "task": name, "layer": layer, "attempt": attempt,
             "start": stamp(day, start), "end": stamp(day, end), "status": status, "rows_read": counts[0],
             "rows_written": counts[1], "rows_changed": counts[2], "error": error, "message": message}
        )  # fmt: skip

    def check(day: date, name: str, table: str, layer: str, status: str, rows: int | None, note: str | None) -> None:
        checks.append(
            {"date": day.isoformat(), "check": name, "table": table, "layer": layer, "status": status,
             "failing_rows": rows, "note": note}
        )  # fmt: skip

    for delivery in DELIVERIES:
        day = delivery - timedelta(days=1)
        lines = lines_by_day[day]
        weekend = delivery.weekday() >= 5
        failing = delivery >= COMMA_FROM

        # 04:15 rebuild_customers: a full reload of the ERP customer master
        new = draw.between(0, 3)
        customers += new
        changed = new + draw.between(3, 14)
        run_id = f"rebuild_customers-{delivery}-1"
        start = 4 * 3600 + 15 * 60 + draw.between(0, 4)
        end = start + draw.between(480, 600)
        missing = list(MISSING_TAX_ID) + ([MISSING_TAX_ID_FROM[1]] if delivery >= MISSING_TAX_ID_FROM[0] else [])
        task(run_id, "rebuild_customers", "silver.customers", "silver", 1, delivery, start, end, "success",
             (customers, customers - len(missing), changed))  # fmt: skip
        for customer_id in missing:
            quarantine.append(
                {"date": delivery.isoformat(), "table": "silver.customers", "rule": "missing_tax_id",
                 "row_id": customer_id, "value": "", "run_id": run_id}
            )  # fmt: skip
        check(delivery, "customers_email_format", "silver.customers", "silver", "warn", draw.between(37, 41), None)
        check(delivery, "customers_id_unique", "silver.customers", "silver", "pass", 0, None)

        # the ERP files arrive
        came = arrival(draw, delivery)
        for n, name in enumerate(["orders.csv", "invoices.csv", "returns.csv", "payments.csv"]):
            at = came + (0 if n == 0 else draw.between(5, 60) + 60 * n)
            deliveries.append(
                {"source": "erp", "file": f"sources/erp/{delivery}/{name}", "arrived_at": stamp(delivery, at),
                 "rows": len(files[delivery][name][1])}
            )  # fmt: skip

        # 06:30 load_erp_orders, and 09:12 a manual rerun on the first failing day
        attempts = [(1, 6 * 3600 + 30 * 60)]
        if delivery == RERUN[0]:
            attempts.append((2, RERUN[1]))
        unknown = [line for line in lines if not known_store(line.store_id)]
        silver_end = 0
        for attempt, begin in attempts:
            run_id = f"load_erp_orders-{delivery}-{attempt}"
            start = begin + draw.between(0, 2)
            if came > start:
                end = came + draw.between(20, 40)
                late = (came - 6 * 3600 - 30 * 60) // 60
                message = f"orders.csv arrived {clock(came)}, {late} minutes after the 06:30 start"
                task(run_id, "load_erp_orders", "wait_for_file", "landing", attempt, delivery, start, end, "warning",
                     message=message)  # fmt: skip
            else:
                end = start + 2
                task(run_id, "load_erp_orders", "wait_for_file", "landing", attempt, delivery, start, end, "success")
            start = end + draw.between(1, 3)
            end = start + draw.between(120, 180)
            n = len(lines)
            task(run_id, "load_erp_orders", "bronze.erp_orders", "bronze", attempt, delivery, start, end, "success",
                 (n, n, n))  # fmt: skip
            if attempt == 1:
                check(delivery, "erp_orders_not_empty", "bronze.erp_orders", "bronze", "pass", 0, None)
                check(delivery, "erp_orders_key_unique", "bronze.erp_orders", "bronze", "pass", 0, None)
            start = end + draw.between(1, 3)
            if failing:
                value = files[delivery]["orders.csv"][1][0][8]
                error = (
                    f'silver.orders: invalid input syntax for type numeric: "{value}" '
                    f"(pipeline/silver/orders.sql line {line_of_cast}, column amount)"
                )
                end = start + draw.between(30, 50)
                task(run_id, "load_erp_orders", "silver.orders", "silver", attempt, delivery, start, end, "failed",
                     (n, 0, 0), error=error)  # fmt: skip
            else:
                end = start + draw.between(120, 240)
                kept = n - len(unknown)
                task(run_id, "load_erp_orders", "silver.orders", "silver", attempt, delivery, start, end, "success",
                     (n, kept, kept))  # fmt: skip
                for line in unknown:
                    quarantine.append(
                        {"date": delivery.isoformat(), "table": "silver.orders", "rule": "unknown_store_id",
                         "row_id": f"{line.order_id}/{line.line_no}", "value": line.store_id, "run_id": run_id}
                    )  # fmt: skip
                silver_rows += kept
                check(delivery, "orders_amount_positive", "silver.orders", "silver", "pass", 0, None)
                if day.weekday() != 6:
                    closed = [s[0] for s in STORES if not any(line.store_id == s[0] for line in lines)]
                    note = None
                    if closed:
                        note = (
                            f"Orders of {day:%A} {day.day} {day:%B}: the four Szeged stores (S-027 to S-030) were "
                            "closed for the Hungarian national holiday. Expected, no action."
                        )
                    check(delivery, "orders_every_store_ordered", "silver.orders", "silver",
                          "fail" if closed else "pass", len(closed), note)  # fmt: skip
            if attempt == 1:
                silver_end = end

        # 07:00 build_sales_daily, after load_erp_orders
        run_id = f"build_sales_daily-{delivery}-1"
        if failing:
            start = 7 * 3600
            task(run_id, "build_sales_daily", "gold.sales_daily", "gold", 1, delivery, start, start + 1, "skipped",
                 error="skipped: load_erp_orders failed for this delivery")  # fmt: skip
        else:
            start = max(7 * 3600, silver_end + draw.between(5, 20))
            end = start + draw.between(360, 480)
            new_rows = len({(line.store_id, line.currency) for line in lines if known_store(line.store_id)})
            gold_rows += new_rows
            task(run_id, "build_sales_daily", "gold.sales_daily", "gold", 1, delivery, start, end, "success",
                 (silver_rows, gold_rows, new_rows))  # fmt: skip
            check(delivery, "sales_daily_key_unique", "gold.sales_daily", "gold", "pass", 0, None)
            built_at = stamp(delivery, end)
            last_built = (delivery, end)
        built_day, built_end = last_built
        if failing:
            note = f"last built {built_day} {clock(built_end)}, due 08:00 daily"
            check(delivery, "sales_daily_fresh", "gold.sales_daily", "gold", "fail", None, note)
        else:
            check(delivery, "sales_daily_fresh", "gold.sales_daily", "gold", "pass", None, None)

        # 07:45 load_erp_finance
        run_id = f"load_erp_finance-{delivery}-1"
        start = 7 * 3600 + 45 * 60 + draw.between(0, 2)
        for name, layer, file in [
            ("bronze.erp_invoices", "bronze", "invoices.csv"),
            ("bronze.erp_returns", "bronze", "returns.csv"),
            ("bronze.erp_payments", "bronze", "payments.csv"),
            ("silver.invoices", "silver", "invoices.csv"),
            ("silver.returns", "silver", "returns.csv"),
            ("silver.payments", "silver", "payments.csv"),
        ]:
            end = start + draw.between(30, 75)
            n = len(files[delivery][file][1])
            task(run_id, "load_erp_finance", name, layer, 1, delivery, start, end, "success", (n, n, n))
            if name == "silver.invoices":
                check(delivery, "invoices_amount_parsed", "silver.invoices", "silver", "pass", 0, None)
            start = end + draw.between(1, 3)

        check(delivery, "stock_levels_fresh", "gold.stock_levels", "gold", "pass", None, None)
        check(delivery, "stock_levels_non_negative", "gold.stock_levels", "gold", "pass", 0, None)

        # the billing export: node hours per job, the dev cluster by the hour it is up
        hours = {
            "build_sales_daily": None if failing else draw.between(300, 330),
            "load_erp_finance": draw.between(18, 24),
            "load_erp_orders": (21 if delivery == RERUN[0] else 12) if failing else draw.between(30, 40),
            "rebuild_customers": draw.between(70, 80),
            "refresh_stock": 216,
        }
        for name, centi in hours.items():
            if centi is not None:
                usage.append(
                    [delivery.isoformat(), "job", name, "etl", money(centi), money(centi * ETL_EUR_PER_HOUR // 100)]
                )
        usage.append([delivery.isoformat(), "cluster", "dev-adhoc", "dev-adhoc", "24.00", money(24 * DEV_EUR_PER_HOUR)])

        for consumer, table, working, rest in QUERY_PLAN:
            count = rest if weekend else working
            if consumer == "key_account_team" and not weekend:
                count = draw.between(2, 4)
            if count:
                queries.append([delivery.isoformat(), consumer, table, str(count)])
        if not weekend:
            queries.append([delivery.isoformat(), "analyst_adhoc", "silver.orders", str(draw.between(2, 9))])

    for delivery in CRM_DELIVERIES:
        came = 4 * 3600 + 45 * 60 + draw.between(0, 8 * 60)
        for n, name in enumerate(["customers.csv", "contacts.csv", "activities.csv"]):
            deliveries.append(
                {"source": "crm", "file": f"sources/crm/{delivery}/{name}",
                 "arrived_at": stamp(delivery, came + 20 * n), "rows": 0}
            )  # fmt: skip

    runs.sort(key=lambda r: r["start"])
    deliveries.sort(key=lambda r: r["arrived_at"])
    return {
        "runs": runs,
        "checks": checks,
        "quarantine": quarantine,
        "deliveries": deliveries,
        "usage": usage,
        "queries": queries,
        "built_at": built_at,
    }


def sales_daily(lines_by_day: dict[date, list[Line]], built_at: str, emails: dict[str, str]) -> list[list[str]]:
    """The sample of gold.sales_daily as `make samples` exported it after the last build (2026-11-02)."""
    names = {s[0]: s[1] for s in STORES}
    customers = {s[0]: customer_of(i) for i, s in enumerate(STORES)}
    rows = []
    for day in sorted(lines_by_day):
        if day > date(2026, 11, 1):
            continue
        groups: dict[tuple[str, str], list[Line]] = defaultdict(list)
        for line in lines_by_day[day]:
            if known_store(line.store_id):
                groups[(line.store_id, line.currency)].append(line)
        for (store_id, currency), group in sorted(groups.items()):
            gross = sum(line.amount for line in group)
            cancelled = sum(line.amount for line in group if line.status == "cancelled")
            grams = sum(line.weight_g for line in group)
            rows.append(
                [day.isoformat(), store_id, names[store_id], currency, str(len({line.order_id for line in group})),
                 str(len(group)), money(gross), money(cancelled), money(gross - cancelled),
                 f"{grams // 1000}.{grams % 1000:03d}", customers[store_id], emails[customers[store_id]], built_at]
            )  # fmt: skip
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the data of the acme-pipeline fixture.")
    parser.add_argument("--extras", type=Path, default=EXTRAS, help="where the uncommitted files go")
    parser.add_argument("--ref", type=Path, default=REF, help="where ref/stores.csv goes")
    args = parser.parse_args(argv)
    extras: Path = args.extras
    lines_by_day = order_lines(Draw(SEED))
    files = erp_files(Draw(SEED + 1), lines_by_day)
    records = ops(Draw(SEED + 2), lines_by_day, files)

    emails = {customer_of(i): email_of(s[5], s[6]) for i, s in enumerate(STORES)}
    write_csv(
        args.ref / "stores.csv",
        ["store_id", "store_name", "city", "country", "currency", "customer_id", "opened_on", "active"],
        [[s[0], s[1], s[2], s[3], s[4], customer_of(i), s[7], "true"] for i, s in enumerate(STORES)],
    )
    for delivery in ERP_ON_DISK:
        for name, (header, rows) in files[delivery].items():
            write_csv(extras / "sources" / "erp" / delivery.isoformat() / name, header, rows)

    crm = Draw(SEED + 3)
    customers = crm_customers(crm)
    account_ids = list(dict.fromkeys(row[0] for row in customers))
    contacts = crm_contacts(crm, account_ids)
    crm_rows: dict[str, dict[str, int]] = {}
    for delivery in CRM_DELIVERIES:
        newest = delivery == CRM_DELIVERIES[-1]
        day_customers = customers if newest else [row for row in customers if row[0] not in account_ids[-2:]]
        day_contacts = contacts if newest else contacts[: CRM_CONTACTS - CRM_NEW_CONTACTS]
        activities = crm_activities(crm, delivery, account_ids, day_contacts)
        folder = extras / "sources" / "crm" / delivery.isoformat()
        write_csv(
            folder / "customers.csv",
            ["customer_id", "company_name", "tax_id", "segment", "status", "city", "country", "credit_limit",
             "created_on", "closed_on", "parent_customer_id", "key_account_manager"],
            day_customers,
        )  # fmt: skip
        write_csv(
            folder / "contacts.csv",
            ["contact_id", "customer_id", "first_name", "last_name", "job_title", "email", "phone", "iban",
             "consent_date", "legacy_crm_ref"],
            day_contacts,
        )  # fmt: skip
        header = ["activity_id", "customer_id", "contact_id", "activity_date", "type", "channel", "subject",
                  "deal_value", "owner"]  # fmt: skip
        if not newest:
            header.remove("channel")
        write_csv(folder / "activities.csv", header, activities, delimiter=";")
        crm_rows[delivery.isoformat()] = {
            "customers.csv": len(day_customers),
            "contacts.csv": len(day_contacts),
            "activities.csv": len(activities),
        }
    for record in records["deliveries"]:
        if record["source"] == "crm":
            day, name = record["file"].split("/")[2:]
            record["rows"] = crm_rows[day][name]

    write_jsonl(extras / "ops" / "runs.jsonl", records["runs"])
    write_jsonl(extras / "ops" / "checks.jsonl", records["checks"])
    write_jsonl(extras / "ops" / "quarantine.jsonl", records["quarantine"])
    write_jsonl(extras / "ops" / "deliveries.jsonl", records["deliveries"])
    write_csv(
        extras / "ops" / "usage.csv",
        ["date", "resource_type", "resource", "cluster", "compute_hours", "compute_eur"],
        records["usage"],
    )
    write_csv(
        extras / "ops" / "storage.csv",
        ["table", "layer", "gb", "eur_per_month"],
        [[t, layer, gb, money(round(float(gb) * 100) * STORAGE_CENTS_PER_GB // 100)] for t, layer, gb in STORAGE],
    )
    write_csv(extras / "ops" / "query_log.csv", ["date", "consumer", "table", "queries"], records["queries"])
    write_csv(
        extras / "samples" / "gold" / "sales_daily.csv",
        ["sales_date", "store_id", "store_name", "currency", "orders", "order_lines", "gross_revenue",
         "cancelled_amount", "net_revenue", "kg_eq", "customer_id", "customer_email", "built_at"],
        sales_daily(lines_by_day, records["built_at"], emails),
    )  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
