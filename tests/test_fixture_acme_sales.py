"""The acme-sales fixture: the made-up sales analytics project the data-analyst skills are tested and shown on.

Every constant below is checked here against the fixture itself, recomputed from the CSVs without the skills' scripts.
The evals and the script tests import them, so keep them in step with the data (make_data.py builds it).

NET_REVENUE, LINES and MIX_SPLIT: a change in net revenue from September to October, mostly mix, with an exact split.
LATE: 4,200.00 of October arrived after the 2 November run, so the reported fall is 4,200.00 larger than the real one.
RECONCILE: the ERP and the ledger differ for October by causes that add up to the whole gap, one of them unexplained.
METRIC: two conflicting definitions of net revenue and the steps between them.
REPORT and PLANTED: what is wrong with the October review, with file:line.
"""

from __future__ import annotations

import csv
import filecmp
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

import build_fixture
import pytest
from conftest import ROOT, git

NET_REVENUE: dict[str, Decimal] = {
    "september": Decimal("96000.00"),
    "october_final": Decimal("85390.00"),
    "october_reported": Decimal("81190.00"),
    "change_final": Decimal("-10610.00"),
    "change_reported": Decimal("-14810.00"),
}
LINES: dict[str, dict[str, tuple[int, Decimal]]] = {
    "september": {
        "premium": (400, Decimal("40000.00")),
        "standard": (800, Decimal("40000.00")),
        "value": (800, Decimal("16000.00")),
    },
    "october": {
        "premium": (260, Decimal("26000.00")),
        "standard": (820, Decimal("40590.00")),
        "value": (940, Decimal("18800.00")),
    },
}
MIX_SPLIT: dict[str, Decimal] = {
    "volume": Decimal("960.00"),
    "mix": Decimal("-11160.00"),
    "rate": Decimal("-410.00"),
    "mix_premium": Decimal("-7488.00"),
    "mix_standard": Decimal("24.00"),
    "mix_value": Decimal("-3696.00"),
    "rate_standard": Decimal("-410.00"),
}
LATE: dict[str, Any] = {
    "as_of": "2026-11-02T06:00:00Z",
    "day": "2026-10-27",
    "rows": 32,
    "amount": Decimal("4200.00"),
    "rows_that_day": 53,
    "by_line": {"premium": Decimal("3000.00"), "standard": Decimal("1200.00")},
}
RECONCILE: dict[str, Any] = {
    "erp_total": Decimal("85390.00"),
    "ledger_total": Decimal("83884.00"),
    "gap": Decimal("1506.00"),
    "not_invoiced": (6, Decimal("412.60")),
    "staff_filter": (8, Decimal("590.00")),
    "time_zone_october_only_in_erp": (5, Decimal("431.20")),
    "time_zone_october_only_in_ledger": (4, Decimal("-318.00")),
    "timing": (7, Decimal("777.70")),
    "duplicates_in_ledger": (4, Decimal("-268.00")),
    "only_in_ledger": (2, Decimal("-150.00")),
    "unexplained": (3, Decimal("35.00")),
    "rounding": Decimal("-4.50"),
}
METRIC: dict[str, Any] = {
    "finance": Decimal("85390.00"),
    "bi": Decimal("87625.03"),
    "gap": Decimal("2235.03"),
    "finance_file": "models/marts/mart_net_revenue.sql",
    "bi_file": "reports/dashboards/revenue_dashboard.sql",
    "bi_changed_on": "2026-10-14",
}
REPORT: dict[str, Any] = {
    "revenue_claimed": Decimal("88600.00"),
    "revenue_correct": Decimal("85390.00"),
    "double_counted": Decimal("3210.00"),
    "double_counted_orders": 40,
    "region_total_claimed": Decimal("81842.62"),
    "region_null_rows": 30,
    "region_null_amount": Decimal("3114.50"),
    "region_unknown_rows": 6,
    "region_total_correct": Decimal("84957.12"),
    "september_partial": Decimal("74607.00"),
    "september_partial_days": 24,
    "uplift_claimed_pct": 14.5,
    "october_like_for_like": Decimal("62799.98"),
    "conversion_claimed_pct": Decimal("5.22"),
    "conversion_correct_pct": Decimal("2.61"),
    "web_orders": 600,
    "sessions_logged_in": 11_500,
    "sessions_total": 23_000,
    "average_of_averages": Decimal("118.89"),
    "true_store_average": Decimal("96.09"),
    "small_sample_store": "6",
    "small_sample_rows": 6,
    "small_sample_average": Decimal("240.00"),
    "desktop_pct": Decimal("4.43"),
    "mobile_pct": Decimal("1.81"),
}
SIMPSON: dict[tuple[str, str], tuple[int, int]] = {
    ("desktop", "direct"): (4_000, 240),
    ("desktop", "search"): (2_000, 60),
    ("desktop", "paid_social"): (1_000, 10),
    ("mobile", "direct"): (1_000, 70),
    ("mobile", "search"): (1_000, 35),
    ("mobile", "paid_social"): (14_000, 185),
}

# (number, short name, file, regex for the flawed line)
PLANTED: list[tuple[int, str, str, str]] = [
    (
        1,
        "double counting through a join",
        "reports/october_review/revenue_by_line.sql",
        r"^left join analytics\.order_promotions as p$",
    ),
    (
        2,
        "a filter that silently drops rows",
        "reports/october_review/revenue_by_region.sql",
        r"^  and region <> 'unknown'$",
    ),
    (
        3,
        "partial period compared with a full one",
        "reports/october_review/sep_vs_oct.sql",
        r"between '2026-09-01' and '2026-09-24'",
    ),
    (4, "wrong denominator", "reports/october_review/conversion.sql", r"sum\(orders\) / sum\(case when logged_in"),
    (
        5,
        "average of averages",
        "reports/october_review/avg_order_by_store.sql",
        r"^select avg\(avg_order\) as avg_order_all_stores$",
    ),
    (6, "a store with 6 orders ranked first", "reports/october_review/report.md", r"Store 6 is our best store"),
    (7, "Simpson's reversal between devices", "reports/october_review/report.md", r"Desktop converts at"),
    (
        8,
        "a chart axis that does not start at zero",
        "reports/october_review/monthly_chart.ipynb",
        r"set_ylim\(70_000, 90_000\)",
    ),
]
PLANTED_AT: dict[int, str] = {
    1: "reports/october_review/revenue_by_line.sql:6",
    2: "reports/october_review/revenue_by_region.sql:8",
    3: "reports/october_review/sep_vs_oct.sql:5",
    4: "reports/october_review/conversion.sql:5",
    5: "reports/october_review/avg_order_by_store.sql:17",
    6: "reports/october_review/report.md:14",
    7: "reports/october_review/report.md:12",
    8: "reports/october_review/monthly_chart.ipynb:7",
}

HEAD = "fe28e88"
COMMITS = 5
FILES = ROOT / "fixtures" / "acme-sales" / "files"
MAKE_DATA = ROOT / "fixtures" / "acme-sales" / "make_data.py"
LAYOUT = [
    ".gitignore",
    "README.md",
    "dbt_project.yml",
    "docs/questions/metric-spec.md",
    "docs/questions/number-moved.md",
    "docs/questions/number-reconcile.md",
    "docs/questions/report-review.md",
    "models/marts/mart_net_revenue.sql",
    "models/marts/schema.yml",
    "models/sources.yml",
    "models/staging/stg_orders.sql",
    "reports/dashboards/revenue_dashboard.sql",
    "reports/october_review/avg_order_by_store.sql",
    "reports/october_review/conversion.sql",
    "reports/october_review/conversion_by_device.sql",
    "reports/october_review/monthly_chart.ipynb",
    "reports/october_review/orders_by_status.sql",
    "reports/october_review/output/avg_order_by_store.csv",
    "reports/october_review/output/conversion.csv",
    "reports/october_review/output/conversion_by_device.csv",
    "reports/october_review/output/orders_by_status.csv",
    "reports/october_review/output/revenue_by_line.csv",
    "reports/october_review/output/revenue_by_region.csv",
    "reports/october_review/output/sep_vs_oct.csv",
    "reports/october_review/report.md",
    "reports/october_review/revenue_by_line.sql",
    "reports/october_review/revenue_by_region.sql",
    "reports/october_review/sep_vs_oct.sql",
]
CSV_FILES = ["customers.csv", "ledger.csv", "order_promotions.csv", "orders.csv", "sessions.csv"]
PERSONAL_COLUMNS = {"customers": ("full_name", "email", "phone"), "orders": ("customer_name", "customer_email")}


def read_csv(repo: Path, name: str) -> list[dict[str, str]]:
    with (repo / "data" / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def tracked(repo: Path) -> list[str]:
    return git(repo, "ls-files").splitlines()


@pytest.fixture(scope="module")
def orders(sales_repo: Path) -> list[dict[str, str]]:
    return read_csv(sales_repo, "orders.csv")


def is_october(row: dict[str, str]) -> bool:
    return row["order_date"].startswith("2026-10")


def completed(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [r for r in rows if r["status"] == "completed"]


def test_builds_deterministically_with_the_same_head(tmp_path: Path) -> None:
    heads = {build_fixture.build("acme-sales", tmp_path / name) for name in ("one", "two")}
    assert heads == {HEAD}


def test_the_generator_makes_the_same_data_from_the_same_seed(tmp_path: Path) -> None:
    data, report = tmp_path / "data", tmp_path / "report"
    subprocess.run([sys.executable, str(MAKE_DATA), str(data), "--report", str(report)], check=True, timeout=120)
    stored = ROOT / "fixtures" / "acme-sales" / "extras" / "data"
    for name in CSV_FILES:
        assert filecmp.cmp(data / name, stored / name, shallow=False), name
    for path in report.rglob("*"):
        if path.is_file():
            target = FILES / "reports" / "october_review" / path.relative_to(report)
            assert filecmp.cmp(path, target, shallow=False), path


def test_layout_and_history(sales_repo: Path) -> None:
    assert sorted(tracked(sales_repo)) == LAYOUT
    assert sorted(p.name for p in (sales_repo / "data").iterdir()) == CSV_FILES
    assert not [rel for rel in tracked(sales_repo) if rel.startswith("data/")]
    assert git(sales_repo, "status", "--porcelain") == ""
    log = git(sales_repo, "log", "--format=%h %s").splitlines()
    assert len(log) == COMMITS
    assert log[0].startswith(HEAD)
    authors = set(git(sales_repo, "log", "--format=%ae").split())
    assert len(authors) == 2 and all(a.endswith("@example.com") for a in authors)
    assert all(
        "2026-08-01" <= d <= "2026-11-30" for d in git(sales_repo, "log", "--format=%ad", "--date=short").split()
    )


def test_the_last_commit_equals_the_stored_files(sales_repo: Path) -> None:
    for path in FILES.rglob("*"):
        if path.is_file():
            rel = path.relative_to(FILES).as_posix()
            assert git(sales_repo, "show", f"HEAD:{rel}") == path.read_text(encoding="utf-8"), rel


def test_net_revenue_change_is_mostly_mix_with_an_exact_split(orders: list[dict[str, str]]) -> None:
    sums: dict[str, dict[str, list[Decimal]]] = defaultdict(lambda: defaultdict(lambda: [Decimal(0), Decimal(0)]))
    for row in completed(orders):
        key = "september" if row["order_date"].startswith("2026-09") else "october"
        sums[key][row["product_line"]][0] += int(row["units"])
        sums[key][row["product_line"]][1] += Decimal(row["net_amount"])
    for month, lines in LINES.items():
        for line, (units, amount) in lines.items():
            assert sums[month][line] == [units, amount], (month, line)
    sep, oct_ = LINES["september"], LINES["october"]
    v0 = Fraction(sum(u for u, _ in sep.values()))
    v1 = Fraction(sum(u for u, _ in oct_.values()))
    r0 = sum(Fraction(a) for _, a in sep.values())
    r1 = sum(Fraction(a) for _, a in oct_.values())
    assert Decimal(float(r0)) == NET_REVENUE["september"]
    assert r1 - r0 == Fraction(NET_REVENUE["change_final"])
    average = r0 / v0
    mix_by_line = {}
    rate_by_line = {}
    for line in sep:
        u0, a0 = sep[line]
        u1, a1 = oct_[line]
        p0, p1 = Fraction(a0) / u0, Fraction(a1) / u1
        mix_by_line[line] = (Fraction(u1) - v1 * Fraction(u0) / v0) * (p0 - average)
        rate_by_line[line] = u1 * (p1 - p0)
    volume = (v1 - v0) * average
    mix = sum(mix_by_line.values())
    rate = sum(rate_by_line.values())
    assert volume == Fraction(MIX_SPLIT["volume"])
    assert mix == Fraction(MIX_SPLIT["mix"])
    assert rate == Fraction(MIX_SPLIT["rate"])
    assert volume + mix + rate == r1 - r0
    assert mix_by_line["premium"] == Fraction(MIX_SPLIT["mix_premium"])
    assert mix_by_line["standard"] == Fraction(MIX_SPLIT["mix_standard"])
    assert mix_by_line["value"] == Fraction(MIX_SPLIT["mix_value"])
    assert rate_by_line["standard"] == Fraction(MIX_SPLIT["rate_standard"])


def test_one_day_of_late_rows_fakes_part_of_the_fall(orders: list[dict[str, str]]) -> None:
    cutoff = datetime.fromisoformat(LATE["as_of"].replace("Z", "+00:00"))
    late = [
        r
        for r in completed(orders)
        if is_october(r) and datetime.fromisoformat(r["loaded_at"].replace("Z", "+00:00")) > cutoff
    ]
    assert len(late) == LATE["rows"]
    assert {r["order_date"] for r in late} == {LATE["day"]}
    assert sum(Decimal(r["net_amount"]) for r in late) == LATE["amount"]
    by_line: dict[str, Decimal] = defaultdict(Decimal)
    for row in late:
        by_line[row["product_line"]] += Decimal(row["net_amount"])
    assert dict(by_line) == LATE["by_line"]
    that_day = [r for r in completed(orders) if r["order_date"] == LATE["day"]]
    assert len(that_day) == LATE["rows_that_day"]
    assert sum(Decimal(r["net_amount"]) for r in completed(orders) if is_october(r)) == NET_REVENUE["october_final"]
    reported = NET_REVENUE["october_final"] - LATE["amount"]
    assert reported == NET_REVENUE["october_reported"]
    assert reported - NET_REVENUE["september"] == NET_REVENUE["change_reported"]


def test_the_two_systems_differ_by_known_amounts_from_known_causes(
    orders: list[dict[str, str]], sales_repo: Path
) -> None:
    ledger = read_csv(sales_repo, "ledger.csv")
    october = [r for r in completed(orders) if is_october(r)]
    erp_total = sum(Decimal(r["net_amount"]) for r in october)
    in_month = [r for r in ledger if r["posted_at"].startswith("2026-10")]
    ledger_total = sum(Decimal(r["amount"]) for r in in_month)
    gap = erp_total - ledger_total
    assert erp_total == RECONCILE["erp_total"] and ledger_total == RECONCILE["ledger_total"] and gap == RECONCILE["gap"]
    posted_counts = Counter(r["order_id"] for r in ledger)
    by_id = {r["order_id"]: r for r in orders}
    keys_in_erp = {r["order_id"] for r in october}
    keys_in_ledger = {r["order_id"] for r in in_month}
    only_erp = keys_in_erp - keys_in_ledger
    not_invoiced = [k for k in only_erp if k not in posted_counts and by_id[k]["channel"] != "staff"]
    staff = [k for k in only_erp if by_id[k]["channel"] == "staff"]
    assert all(k not in posted_counts for k in staff)
    amount = lambda keys: sum(Decimal(by_id[k]["net_amount"]) for k in keys)  # noqa: E731
    assert (len(not_invoiced), amount(not_invoiced)) == RECONCILE["not_invoiced"]
    assert (len(staff), amount(staff)) == RECONCILE["staff_filter"]
    ledger_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in ledger:
        ledger_by_key[row["order_id"]].append(row)
    posted_elsewhere = [k for k in only_erp if k in posted_counts]

    # Time zone: the ledger clock is 1 or 2 hours ahead of the ERP's UTC clock; timing is days later.
    def lag(key: str) -> float:
        a = datetime.fromisoformat(by_id[key]["order_ts"].rstrip("Z"))
        b = datetime.fromisoformat(ledger_by_key[key][0]["posted_at"])
        return (b - a).total_seconds() / 3600

    zoned = [k for k in posted_elsewhere if lag(k) < 15]
    timing = [k for k in posted_elsewhere if lag(k) >= 15]
    assert (len(zoned), amount(zoned)) == RECONCILE["time_zone_october_only_in_erp"]
    assert (len(timing), amount(timing)) == RECONCILE["timing"]
    late_in = [r for r in in_month if r["order_id"] not in keys_in_erp and r["order_id"] in by_id]
    assert (len(late_in), -sum(Decimal(r["amount"]) for r in late_in)) == RECONCILE["time_zone_october_only_in_ledger"]
    assert all(lag(r["order_id"]) < 15 for r in late_in)
    manual = [r for r in in_month if not r["order_id"].startswith("SO-")]
    assert (len(manual), -sum(Decimal(r["amount"]) for r in manual)) == RECONCILE["only_in_ledger"]
    duplicates: list[dict[str, str]] = []
    seen: set[str] = set()
    rest: list[dict[str, str]] = []
    for row in in_month:
        if row["order_id"] in seen:
            duplicates.append(row)
        else:
            seen.add(row["order_id"])
            rest.append(row)
    assert (len(duplicates), -sum(Decimal(r["amount"]) for r in duplicates)) == RECONCILE["duplicates_in_ledger"]
    differences = {
        r["order_id"]: Decimal(by_id[r["order_id"]]["net_amount"]) - Decimal(r["amount"])
        for r in rest
        if r["order_id"] in keys_in_erp and r["order_id"].startswith("SO-")
    }
    manual_adjusted = {k: v for k, v in differences.items() if abs(v) > Decimal("0.50")}
    assert (len(manual_adjusted), sum(manual_adjusted.values())) == RECONCILE["unexplained"]
    assert sorted(manual_adjusted.values()) == [Decimal("5.00"), Decimal("10.00"), Decimal("20.00")]
    rounding = sum(v for k, v in differences.items() if k not in manual_adjusted)
    assert rounding == RECONCILE["rounding"]
    # The whole gap, cause by cause, and nothing else.
    causes = [
        RECONCILE["not_invoiced"][1],
        RECONCILE["staff_filter"][1],
        RECONCILE["time_zone_october_only_in_erp"][1],
        RECONCILE["time_zone_october_only_in_ledger"][1],
        RECONCILE["timing"][1],
        RECONCILE["duplicates_in_ledger"][1],
        RECONCILE["only_in_ledger"][1],
        RECONCILE["unexplained"][1],
        RECONCILE["rounding"],
    ]
    assert sum(causes) == RECONCILE["gap"]


def test_two_conflicting_definitions_of_net_revenue(orders: list[dict[str, str]], sales_repo: Path) -> None:
    finance_sql = (sales_repo / METRIC["finance_file"]).read_text(encoding="utf-8")
    bi_sql = (sales_repo / METRIC["bi_file"]).read_text(encoding="utf-8")
    assert "sum(net_amount) as net_revenue" in finance_sql and "status = 'completed'" in finance_sql
    assert "order_date" in finance_sql
    assert "sum(net_amount + shipping_fee) as net_revenue" in bi_sql
    assert "shipped_date" in bi_sql and "'returned'" in bi_sql and "channel <> 'staff'" in bi_sql
    finance = sum(Decimal(r["net_amount"]) for r in completed(orders) if is_october(r))
    bi = sum(
        Decimal(r["net_amount"]) + Decimal(r["shipping_fee"])
        for r in orders
        if r["shipped_date"].startswith("2026-10")
        and r["status"] in ("completed", "returned")
        and r["channel"] != "staff"
    )
    assert finance == METRIC["finance"] and bi == METRIC["bi"] and bi - finance == METRIC["gap"]
    assert (
        git(sales_repo, "log", "--format=%ad", "--date=short", "--", METRIC["bi_file"]).split()[0]
        == METRIC["bi_changed_on"]
    )


def test_the_report_numbers_are_the_flawed_ones(sales_repo: Path) -> None:
    report = (sales_repo / "reports/october_review/report.md").read_text(encoding="utf-8")
    for needle in (
        "EUR 88600.00",
        "EUR 81842.62",
        "up 14.5%",
        "EUR 74607.00",
        "5.22%",
        "4.43%",
        "1.81%",
        "EUR 118.89",
        "EUR 240.00",
    ):
        assert needle in report, needle
    output = sales_repo / "reports/october_review/output"
    by_line = {
        r["product_line"]: Decimal(r["net_revenue"]) for r in csv.DictReader((output / "revenue_by_line.csv").open())
    }
    assert sum(by_line.values()) == REPORT["revenue_claimed"]
    regions = {
        r["region"]: Decimal(r["net_revenue"]) for r in csv.DictReader((output / "revenue_by_region.csv").open())
    }
    assert sum(regions.values()) == REPORT["region_total_claimed"]


def test_double_counting_and_a_silently_dropped_filter(orders: list[dict[str, str]], sales_repo: Path) -> None:
    promos = Counter(r["order_id"] for r in read_csv(sales_repo, "order_promotions.csv"))
    october = [r for r in completed(orders) if is_october(r)]
    inflated = sum(Decimal(r["net_amount"]) * max(1, promos.get(r["order_id"], 0)) for r in october)
    assert inflated == REPORT["revenue_claimed"]
    assert sum(Decimal(r["net_amount"]) for r in october) == REPORT["revenue_correct"]
    assert inflated - REPORT["revenue_correct"] == REPORT["double_counted"]
    assert sum(1 for r in october if promos.get(r["order_id"], 0) > 1) == REPORT["double_counted_orders"]
    empty = [r for r in october if r["region"] == ""]
    unknown = [r for r in october if r["region"] == "unknown"]
    assert len(empty) == REPORT["region_null_rows"]
    assert sum(Decimal(r["net_amount"]) for r in empty) == REPORT["region_null_amount"]
    assert len(unknown) == REPORT["region_unknown_rows"]
    kept = [r for r in october if r["region"] not in ("", "unknown")]
    assert sum(Decimal(r["net_amount"]) for r in kept) == REPORT["region_total_claimed"]
    assert REPORT["region_total_claimed"] + REPORT["region_null_amount"] == REPORT["region_total_correct"]


def test_partial_period_and_small_sample_and_average_of_averages(orders: list[dict[str, str]]) -> None:
    october = [r for r in completed(orders) if is_october(r)]
    partial = sum(
        Decimal(r["net_amount"]) for r in completed(orders) if "2026-09-01" <= r["order_date"] <= "2026-09-24"
    )
    assert partial == REPORT["september_partial"]
    assert round((sum(Decimal(r["net_amount"]) for r in october) - partial) / partial * 100, 1) == Decimal("14.5")
    like_for_like = sum(Decimal(r["net_amount"]) for r in october if r["order_date"] <= "2026-10-24")
    assert like_for_like == REPORT["october_like_for_like"]
    stores: dict[str, list[Decimal]] = defaultdict(list)
    for row in october:
        if row["channel"] == "store":
            stores[row["store_id"]].append(Decimal(row["net_amount"]))
    assert len(stores) == 6
    assert len(stores[REPORT["small_sample_store"]]) == REPORT["small_sample_rows"]
    assert sum(stores["6"]) / len(stores["6"]) == REPORT["small_sample_average"]
    average_of_averages = sum(sum(v) / len(v) for v in stores.values()) / 6
    true_average = sum(sum(v) for v in stores.values()) / sum(len(v) for v in stores.values())
    assert round(average_of_averages, 2) == REPORT["average_of_averages"]
    assert round(true_average, 2) == REPORT["true_store_average"]


def test_wrong_denominator_and_simpsons_reversal(sales_repo: Path) -> None:
    rows = read_csv(sales_repo, "sessions.csv")
    cells: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    logged_in = 0
    total_orders = 0
    for row in rows:
        cells[(row["device"], row["source"])][0] += int(row["sessions"])
        cells[(row["device"], row["source"])][1] += int(row["orders"])
        logged_in += int(row["sessions"]) if row["logged_in"] == "true" else 0
        total_orders += int(row["orders"])
    assert {k: tuple(v) for k, v in cells.items()} == SIMPSON
    assert total_orders == REPORT["web_orders"]
    assert logged_in == REPORT["sessions_logged_in"]
    assert round(Decimal(total_orders) / logged_in * 100, 2) == REPORT["conversion_claimed_pct"]
    assert round(Decimal(total_orders) / REPORT["sessions_total"] * 100, 2) == REPORT["conversion_correct_pct"]
    overall = {
        d: sum(c[1] for k, c in cells.items() if k[0] == d) / sum(c[0] for k, c in cells.items() if k[0] == d)
        for d in ("desktop", "mobile")
    }
    assert overall["desktop"] > overall["mobile"]
    assert round(Decimal(overall["desktop"]) * 100, 2) == REPORT["desktop_pct"]
    assert round(Decimal(overall["mobile"]) * 100, 2) == REPORT["mobile_pct"]
    sources = {k[1] for k in cells}
    for source in sources:
        desktop = cells[("desktop", source)]
        mobile = cells[("mobile", source)]
        assert mobile[1] / mobile[0] > desktop[1] / desktop[0], source


@pytest.mark.parametrize(("number", "name", "rel", "pattern"), PLANTED, ids=[p[1] for p in PLANTED])
def test_planted_problem_sits_on_its_line(sales_repo: Path, number: int, name: str, rel: str, pattern: str) -> None:
    text = (sales_repo / rel).read_text(encoding="utf-8")
    if rel.endswith(".ipynb"):
        cells = json.loads(text)["cells"]
        lines = "".join("".join(c["source"]) for c in cells if c["cell_type"] == "code").splitlines()
    else:
        lines = text.splitlines()
    hits = [n for n, line in enumerate(lines, start=1) if re.search(pattern, line)]
    assert len(hits) == 1, f"{pattern!r} matches lines {hits} of {rel}"
    assert f"{rel}:{hits[0]}" == PLANTED_AT[number]


def test_fixture_is_fictional_and_no_personal_value_is_in_the_committed_files(sales_repo: Path) -> None:
    for name in CSV_FILES:
        with (sales_repo / "data" / name).open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        for columns in PERSONAL_COLUMNS.get(name.removesuffix(".csv"), ()):
            for column in [columns] if isinstance(columns, str) else columns:
                assert column in rows[0]
    customers = read_csv(sales_repo, "customers.csv")
    assert all(r["email"].endswith("@example.com") for r in customers)
    for rel in LAYOUT:
        text = (sales_repo / rel).read_text(encoding="utf-8")
        assert (
            "@example.com" in text or re.search(r"[\w.+-]+@\w", text) is None or "finance-reporting@example.com" in text
        )
    all_text = "\n".join((sales_repo / rel).read_text(encoding="utf-8") for rel in LAYOUT)
    for row in customers[:50]:
        assert row["email"] not in all_text and row["full_name"] not in all_text
