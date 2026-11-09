"""The acme-data fixture: the made-up data warehouse the data-architect skills are tested and shown on.

PLANTED lists the eight problems a review of it must find: (number, short name, file, regex for the flawed line).
PLANTED_AT says where each one sits in the built fixture. EDGES is the table-level lineage a reader of the code must
find, as (read, written or consumer) in unqualified lower-case names, with the ERP sources kept as erp.<table> and a
report or export named after its file stem. NOT_TABLES are fake names that must never be read as tables. DATA holds the
counts planted in the sample CSVs. The evals and the script tests import these, so keep them in step with the fixture.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from datetime import date
from pathlib import Path

import build_fixture
import pytest
from conftest import ROOT, git

PLANTED: list[tuple[int, str, str, str]] = [
    (
        1,
        "join on a key that is not unique",
        "models/marts/fct_sales.sql",
        r"left join \{\{ ref\('stg_promotions'\) \}\} as promo on l\.product_id = promo\.product_id$",
    ),
    (
        2,
        "load that cannot be rerun",
        "warehouse/procs/load_daily_sales.sql",
        r"^\s+INSERT INTO \[dw\]\.\[fct_daily_sales\] ",
    ),
    (3, "report reads the staging layer", "reports/store_performance.sql", r"^inner join staging\.stg_orders as o "),
    (4, "personal data served unmasked", "exports/marketing_contacts.sql", r"^\s+c\.email, c\.national_id,$"),
    (5, "money stored as a float", "warehouse/ddl/fct_daily_sales.sql", r"^\s+\[net_amount\] FLOAT\b"),
    (
        6,
        "history overwritten in place",
        "warehouse/procs/merge_dim_product.sql",
        r"^\s+t\.list_price = s\.list_price,$",
    ),
    (7, "keys of the main fact without tests", "models/marts/schema.yml", r"^  - name: fct_sales$"),
    (
        8,
        "dynamic SQL by concatenation",
        "warehouse/procs/export_by_region.sql",
        r"^\s+SET @sql = N'.*' \+ @region \+ N'.*';$",
    ),
]

PLANTED_AT: dict[int, str] = {
    1: "models/marts/fct_sales.sql:33",
    2: "warehouse/procs/load_daily_sales.sql:19",
    3: "reports/store_performance.sql:10",
    4: "exports/marketing_contacts.sql:6",
    5: "warehouse/ddl/fct_daily_sales.sql:8",
    6: "warehouse/procs/merge_dim_product.sql:13",
    7: "models/marts/schema.yml:31",
    8: "warehouse/procs/export_by_region.sql:10",
}

EDGES: list[tuple[str, str]] = [
    ("erp.orders", "stg_orders"),
    ("erp.order_lines", "stg_order_lines"),
    ("erp.customers", "stg_customers"),
    ("erp.products", "stg_products"),
    ("erp.stores", "stg_stores"),
    ("erp.promotions", "stg_promotions"),
    ("stg_orders", "int_order_lines"),
    ("stg_order_lines", "int_order_lines"),
    ("int_order_lines", "fct_sales"),
    ("stg_promotions", "fct_sales"),
    ("dim_product", "fct_sales"),
    ("stg_customers", "dim_customer"),
    ("stg_products", "dim_product"),
    ("stg_stores", "dim_store"),
    ("stg_promotions", "mart_old_campaigns"),
    ("fct_sales", "fct_daily_sales"),
    ("fct_sales", "store_performance"),
    ("dim_store", "store_performance"),
    ("stg_orders", "store_performance"),
    ("dim_customer", "marketing_contacts"),
    ("erp.stock_levels", "stock_snapshot"),
    ("dim_store", "stock_snapshot"),
    ("dim_product", "stock_snapshot"),
]

NOT_TABLES: list[str] = ["old_orders_backup", "retired_table", "finance_ledger"]

DATA: dict[str, int] = {
    "customers_rows": 406,
    "customers_distinct_ids": 400,
    "orphan_lines": 30,
    "decimal_comma_prices": 120,
    "dmy_order_dates": 300,
    "order_lines_rows": 3000,
    "orders_rows": 1500,
}

HEAD = "0734a04"
COMMITS = 10

FILES = ROOT / "fixtures" / "acme-data" / "files"
EXTRAS = ROOT / "fixtures" / "acme-data" / "extras" / "data"
MAKE_DATA = ROOT / "fixtures" / "acme-data" / "make_data.py"

LAYOUT = [
    ".gitignore",
    "README.md",
    "dbt_project.yml",
    "docs/briefs/new-platform.md",
    "docs/briefs/reports-only.md",
    "exports/marketing_contacts.sql",
    "models/intermediate/int_order_lines.sql",
    "models/marts/dim_customer.sql",
    "models/marts/dim_product.sql",
    "models/marts/dim_store.sql",
    "models/marts/fct_sales.sql",
    "models/marts/mart_old_campaigns.sql",
    "models/marts/schema.yml",
    "models/staging/schema.yml",
    "models/staging/stg_customers.sql",
    "models/staging/stg_order_lines.sql",
    "models/staging/stg_orders.sql",
    "models/staging/stg_products.sql",
    "models/staging/stg_promotions.sql",
    "models/staging/stg_stores.sql",
    "notebooks/stock_snapshot.ipynb",
    "reports/store_performance.sql",
    "warehouse/ddl/dim_product.sql",
    "warehouse/ddl/fct_daily_sales.sql",
    "warehouse/procs/export_by_region.sql",
    "warehouse/procs/load_daily_sales.sql",
    "warehouse/procs/merge_dim_product.sql",
]
CSV_FILES = ["customers.csv", "order_lines.csv", "orders.csv", "products.csv", "promotions.csv", "stores.csv"]


@pytest.fixture(scope="module")
def sql(data_repo: Path) -> dict[str, str]:
    return {
        rel: (data_repo / rel).read_text(encoding="utf-8")
        for rel in LAYOUT
        if rel.endswith(".sql") or rel.endswith(".ipynb")
    }


def read_csv(repo: Path, name: str) -> list[dict[str, str]]:
    with (repo / "data" / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def planted_line(repo: Path, rel: str, pattern: str) -> int:
    """The 1-based line in repo/rel that pattern matches; it must match exactly one line."""
    lines = (repo / rel).read_text(encoding="utf-8").splitlines()
    hits = [number for number, line in enumerate(lines, start=1) if re.search(pattern, line)]
    assert len(hits) == 1, f"{pattern!r} matches lines {hits} of {rel}, expected exactly one"
    return hits[0]


def tracked(repo: Path) -> list[str]:
    return git(repo, "ls-files").splitlines()


def block(text: str, name: str) -> str:
    """The part of a schema.yml from `- name: <name>` up to the next model at the same indent."""
    match = re.search(rf"^  - name: {name}\n(.*?)(?=^  - name: |\Z)", text, re.MULTILINE | re.DOTALL)
    assert match, name
    return match.group(1)


def test_builds_deterministically_with_the_same_head(tmp_path: Path) -> None:
    heads = {build_fixture.build("acme-data", tmp_path / name) for name in ("one", "two")}
    assert heads == {HEAD}


def test_history_has_every_commit_two_authors_and_fictional_dates(data_repo: Path) -> None:
    log = git(data_repo, "log", "--format=%h %s").splitlines()
    assert len(log) == COMMITS
    assert log[0] == f"{HEAD} Briefs: reporting for Acme Bakery and the next Acme Foods platform"
    assert log[-1].endswith(" Start the warehouse: ERP sources, staging for orders and order lines")
    emails = set(git(data_repo, "log", "--format=%ae").split())
    assert len(emails) == 2
    assert all(email.endswith("@example.com") for email in emails)
    days = git(data_repo, "log", "--format=%ad", "--date=short").split()
    assert all("2026-06-01" <= day <= "2026-10-31" for day in days)


def test_layout_is_exact_and_the_last_commit_equals_the_stored_files(data_repo: Path) -> None:
    assert sorted(tracked(data_repo)) == sorted(LAYOUT)
    for path in FILES.rglob("*"):
        if path.is_file():
            rel = path.relative_to(FILES).as_posix()
            assert git(data_repo, "show", f"HEAD:{rel}") == path.read_text(encoding="utf-8"), rel


def test_extras_are_on_disk_but_not_committed(data_repo: Path) -> None:
    assert sorted(p.name for p in (data_repo / "data").iterdir()) == CSV_FILES
    assert not [rel for rel in tracked(data_repo) if rel.startswith("data/")]
    assert git(data_repo, "status", "--porcelain") == ""


@pytest.mark.parametrize(("number", "name", "rel", "pattern"), PLANTED, ids=[p[1] for p in PLANTED])
def test_planted_problem_sits_on_its_line(
    data_repo: Path, record_property: Callable[[str, object], None], number: int, name: str, rel: str, pattern: str
) -> None:
    line = planted_line(data_repo, rel, pattern)
    record_property("planted", f"{number} {name}: {rel}:{line}")
    assert f"{rel}:{line}" == PLANTED_AT[number]


def test_the_planted_problems_are_not_mitigated_elsewhere(data_repo: Path, sql: dict[str, str]) -> None:
    staging_yml = (data_repo / "models/staging/schema.yml").read_text(encoding="utf-8")
    promotions = block(staging_yml, "stg_promotions")
    assert re.search(r"- name: promotion_id\n\s+tests:\n\s+- unique", promotions)
    assert not re.search(r"- name: product_id\n\s+tests:\n\s+- unique", promotions)

    load = sql["warehouse/procs/load_daily_sales.sql"]
    assert "WHERE sale_date = @load_date;" in load
    assert not re.search(r"\b(delete|merge|truncate)\b|not\s+exists", load, re.IGNORECASE)
    # The key of the table is a surrogate, so a rerun doubles the day instead of failing on a duplicate key.
    assert "[daily_sales_id] BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY" in sql["warehouse/ddl/fct_daily_sales.sql"]

    export = sql["exports/marketing_contacts.sql"]
    assert "from marts.dim_customer as c" in export
    assert not re.search(r"hash|mask|md5|sha\d|left\(", export, re.IGNORECASE)

    assert not [rel for rel, text in sql.items() if "FLOAT" in text and "fct_daily_sales.sql" not in rel]
    assert "[list_price] DECIMAL(10, 2)" in sql["warehouse/ddl/dim_product.sql"]

    merge = sql["warehouse/procs/merge_dim_product.sql"]
    assert "MERGE [dw].[dim_product] AS t" in merge
    assert "WHEN MATCHED THEN UPDATE SET" in merge
    assert not re.search(r"valid_from|valid_to|is_current|history", merge, re.IGNORECASE)
    fact = sql["models/marts/fct_sales.sql"]
    assert "{{ ref('dim_product') }}" in fact
    assert "l.quantity * p.list_price as list_amount" in fact

    marts_yml = (data_repo / "models/marts/schema.yml").read_text(encoding="utf-8")
    fct = block(marts_yml, "fct_sales")
    assert "columns:" in fct
    assert "- name: order_id" in fct
    assert "tests:" not in fct
    for dimension in ("dim_customer", "dim_product", "dim_store"):
        assert re.search(r"tests:\n\s+- unique\n\s+- not_null", block(marts_yml, dimension)), dimension

    assert "EXEC(@sql);" in sql["warehouse/procs/export_by_region.sql"]


def test_only_the_planted_report_reads_staging_and_marts_stay_in_their_lane(sql: dict[str, str]) -> None:
    hits = [
        (rel, name)
        for rel, text in sql.items()
        if rel.startswith(("reports/", "exports/"))
        for name in re.findall(r"\bstaging\.(\w+)", text)
    ]
    assert hits == [("reports/store_performance.sql", "stg_orders")]
    for rel, text in sql.items():
        if rel.startswith("models/marts/"):
            assert "source(" not in text, rel
            for name in re.findall(r"ref\('(\w+)'\)", text):
                assert name.startswith(("stg_", "int_", "dim_")), (rel, name)


def test_nobody_reads_the_old_campaign_mart(sql: dict[str, str]) -> None:
    assert not [rel for rel, text in sql.items() if "mart_old_campaigns" in text]


def test_every_lineage_edge_is_in_the_code(sql: dict[str, str]) -> None:
    consumers = {Path(rel).stem: rel for rel in sql if not rel.startswith("warehouse/")}
    consumers["fct_daily_sales"] = "warehouse/procs/load_daily_sales.sql"
    for read, consumer in EDGES:
        rel = consumers[consumer]
        short = read.rsplit(".", 1)[-1]
        forms = [
            rf"ref\('{short}'\)",
            rf"source\('erp','{short}'\)",
            rf"\b(?:marts|staging)\.{short}\b",
            rf"\[marts\]\.\[{short}\]",
            rf"""spark\.read\.table\(\\"{re.escape(read)}\\"\)""",
            rf"""spark\.table\(\\"{re.escape(read)}\\"\)""",
        ]
        assert any(re.search(form, sql[rel]) for form in forms), (read, consumer, rel)


def test_the_traps_for_a_table_reader_are_there(sql: dict[str, str]) -> None:
    text = "\n".join(sql.values())
    assert "-- FROM old_orders_backup" in text
    assert "/* JOIN retired_table */" in text
    assert "'Figures FROM finance_ledger are not included'" in text
    assert "EXTRACT(YEAR FROM order_date)" in text
    for name in NOT_TABLES:
        assert len(re.findall(rf"\b{name}\b", text)) == 1, name
    for rel, body in sql.items():
        if rel.startswith("models/") and rel.endswith(".sql"):
            assert "{{" in body, rel
        if rel.startswith("warehouse/"):
            assert "[dw].[" in body, rel
    assert "{{ config(" in sql["models/marts/fct_sales.sql"]
    assert "with orders as (" in sql["models/intermediate/int_order_lines.sql"]
    assert sql["models/marts/fct_sales.sql"].rstrip().endswith("select * from final")
    assert "WITH (NOLOCK)" in sql["warehouse/procs/load_daily_sales.sql"]


def test_the_notebook_is_valid_and_has_its_reads_and_writes(data_repo: Path) -> None:
    notebook = json.loads((data_repo / "notebooks/stock_snapshot.ipynb").read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    assert isinstance(notebook["cells"], list)
    for cell in notebook["cells"]:
        assert cell["cell_type"] in {"markdown", "code"}
        assert isinstance(cell["id"], str)
        assert isinstance(cell["metadata"], dict)
        assert isinstance(cell["source"], list)
        if cell["cell_type"] == "code":
            assert cell["execution_count"] is None
            assert cell["outputs"] == []
    code = "".join("".join(c["source"]) + "\n" for c in notebook["cells"] if c["cell_type"] == "code")
    assert 'spark.read.table("erp.stock_levels")' in code
    assert 'spark.table("dim_store")' in code
    assert '.saveAsTable("marts.stock_snapshot")' in code
    assert len(re.findall(r'spark\.sql\("[^"{}]+"\)', code)) == 1
    assert len(re.findall(r'spark\.sql\(f"[^"]*\{\w+\}[^"]*"\)', code)) == 1


def test_the_data_counts_are_true(data_repo: Path) -> None:
    customers = read_csv(data_repo, "customers.csv")
    orders = read_csv(data_repo, "orders.csv")
    lines = read_csv(data_repo, "order_lines.csv")
    products = read_csv(data_repo, "products.csv")
    promotions = read_csv(data_repo, "promotions.csv")

    ids = Counter(row["customer_id"] for row in customers)
    assert len(customers) == DATA["customers_rows"]
    assert len(ids) == DATA["customers_distinct_ids"]
    assert sorted(ids.values())[-7:] == [1, 2, 2, 2, 2, 2, 2]

    assert len(orders) == DATA["orders_rows"]
    dotted = [row for row in orders if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", row["order_date"])]
    iso = [row for row in orders if re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["order_date"])]
    assert len(dotted) == DATA["dmy_order_dates"]
    assert len(iso) == DATA["orders_rows"] - DATA["dmy_order_dates"]

    known = {row["product_id"] for row in products}
    assert len(lines) == DATA["order_lines_rows"]
    assert sum(row["product_id"] not in known for row in lines) == DATA["orphan_lines"]
    comma = [row for row in lines if re.fullmatch(r"\d+,\d{2}", row["unit_price"])]
    dot = [row for row in lines if re.fullmatch(r"\d+\.\d{2}", row["unit_price"])]
    assert len(comma) == DATA["decimal_comma_prices"]
    assert len(dot) == DATA["order_lines_rows"] - DATA["decimal_comma_prices"]
    raw = (data_repo / "data" / "order_lines.csv").read_text(encoding="utf-8")
    assert len(re.findall(r'"\d+,\d{2}"', raw)) == DATA["decimal_comma_prices"]

    assert len(products) == 120
    assert len(read_csv(data_repo, "stores.csv")) == 12
    assert len(promotions) == 60
    assert len({row["promotion_id"] for row in promotions}) == 60
    assert max(Counter(row["product_id"] for row in promotions).values()) > 1


def test_national_ids_are_valid_fictional_jmbgs(data_repo: Path) -> None:
    for row in read_csv(data_repo, "customers.csv"):
        national_id = row["national_id"]
        assert re.fullmatch(r"\d{13}", national_id)
        assert national_id[7:9] == "66", row["customer_id"]
        d = [int(c) for c in national_id]
        weights = [7, 6, 5, 4, 3, 2]
        m = 11 - sum(w * (d[i] + d[i + 6]) for i, w in enumerate(weights)) % 11
        assert d[12] == (0 if m > 9 else m), row["customer_id"]
        birth = date.fromisoformat(row["birth_date"])
        assert national_id[:7] == f"{birth.day:02d}{birth.month:02d}{birth.year % 1000:03d}", row["customer_id"]


def test_only_example_addresses_and_fictional_phones(data_repo: Path) -> None:
    for name in CSV_FILES:
        text = (data_repo / "data" / name).read_text(encoding="utf-8")
        assert all(d == "example.com" for d in re.findall(r"@([\w.-]+)", text)), name
    for row in read_csv(data_repo, "customers.csv"):
        assert row["email"].endswith("@example.com"), row["customer_id"]
        assert re.fullmatch(r"\+381 60 555 \d{4}", row["phone"]), row["customer_id"]


def test_the_data_is_small_and_the_generator_reproduces_it(tmp_path: Path) -> None:
    assert sorted(p.name for p in EXTRAS.iterdir()) == CSV_FILES
    assert sum(p.stat().st_size for p in EXTRAS.iterdir()) < 400_000
    subprocess.run([sys.executable, str(MAKE_DATA), str(tmp_path)], check=True, capture_output=True, timeout=60)
    for name in CSV_FILES:
        assert (tmp_path / name).read_bytes() == (EXTRAS / name).read_bytes(), name


def test_briefs_state_their_facts_without_naming_an_architecture(data_repo: Path) -> None:
    briefs = data_repo / "docs" / "briefs"
    reports = " ".join((briefs / "reports-only.md").read_text(encoding="utf-8").split())
    platform = " ".join((briefs / "new-platform.md").read_text(encoding="utf-8").split())
    for fact in ["Acme Bakery", "One ERP", "budget spreadsheet", "3 GB", "40 MB a month", "once a day"]:
        assert fact in reports, fact
    for fact in ["one analyst", "no data engineer", "Power BI", "10 people"]:
        assert fact in reports, fact
    for fact in ["14 sources", "ERP", "CRM", "web events", "shelf sensors", "supplier PDFs"]:
        assert fact in platform, fact
    for fact in ["35 TB", "1 TB a month", "under 2 minutes", "Everything else is daily", "shelf-image model"]:
        assert fact in platform, fact
    for fact in ["raw photos", "EU-only residency", "personal data", "Six data engineers", "one central team"]:
        assert fact in platform, fact
    assert "120 BI users" in platform
    architecture = re.compile(
        r"\b(lakehouse|data lake|warehouse|database|mesh|streaming|kafka|medallion|dbt|spark|scheduled SQL)\b", re.I
    )
    assert not architecture.search(reports + " " + platform)
