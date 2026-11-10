"""The data-engineer scripts of data-cost, data-migration and data-product: on the acme-pipeline fixture, against
its answer key, and on small cases of their own."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import build_fixture
import pytest
from conftest import ROOT, load, run_json
from test_fixture_acme_pipeline import DECOYS, DECOYS_AT, FACTS, PLANTED, PLANTED_AT

SKILLS = ROOT / "plugins" / "data-engineer" / "skills"
COST = SKILLS / "data-cost" / "scripts" / "cost_breakdown.py"
ESTATE = SKILLS / "data-migration" / "scripts" / "estate_inventory.py"
PRODUCT = SKILLS / "data-product" / "scripts" / "product_facts.py"
cost = load(COST)
estate = load(ESTATE)
product = load(PRODUCT)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-pipeline fixture with its extras, built once for this module. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-pipeline"
    build_fixture.build("acme-pipeline", target)
    return target


@pytest.fixture(scope="module")
def costs(repo: Path) -> Any:
    return run_json(COST, str(repo))


@pytest.fixture(scope="module")
def legacy(repo: Path) -> Any:
    return run_json(ESTATE, str(repo / "legacy" / "inventory.csv"))


@pytest.fixture(scope="module")
def served(repo: Path) -> Any:
    return run_json(PRODUCT, str(repo), "--table", "gold.sales_daily", "--grain", "store_id,sales_date")


def pin(key: str, name: str, planted: bool = True) -> str:
    """file:line of an answer-key entry."""
    entries = PLANTED if planted else DECOYS
    lines = PLANTED_AT if planted else DECOYS_AT
    rel = next(e[2] for skill in entries.values() for e in skill if e[:2] == (key, name))
    return f"{rel}:{lines[(key, name)]}"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------- data-cost on the fixture


def test_cost_reads_every_input_and_adds_up_to_the_facts(costs: Any) -> None:
    facts = FACTS["data-cost"]
    assert costs["inputs"]["not_found"] == []
    assert {role: costs["inputs"][role]["file"] for role in ("usage", "storage", "queries", "runs")} == {
        "usage": "ops/usage.csv",
        "storage": "ops/storage.csv",
        "queries": "ops/query_log.csv",
        "runs": "ops/runs.jsonl",
    }
    assert costs["period"]["days"] == facts["period_days"] and costs["currency"] == "EUR"
    totals = costs["totals"]
    assert Decimal(totals["compute_eur"]) == facts["compute_total"]
    assert Decimal(totals["storage_eur_per_month"]) == facts["storage_total"]
    assert Decimal(totals["storage_gb"]) == facts["storage_gb"]
    assert Decimal(totals["total_eur"]) == facts["total"]
    by_resource = {j["job"]: Decimal(j["eur"]) for j in costs["by_job"] if Decimal(j["eur"])}
    by_resource |= {c["cluster"]: Decimal(c["eur"]) for c in costs["candidates"]["compute_without_jobs"]}
    assert by_resource == facts["compute_eur"]
    assert costs["adds_up"]["equals_compute_total"] is True
    # Every split adds up: tables to their job, jobs and clusters to the compute total, tables to the grand total.
    for job in costs["by_job"]:
        assert sum((Decimal(v) for v in job.get("tables", {}).values()), Decimal(0)) in (Decimal(job["eur"]), 0)
    table_total = sum((Decimal(t["total_eur"]) for t in costs["by_table"]), Decimal(0))
    assert table_total + facts["never_stops"]["eur"] == facts["total"]
    assert sum((Decimal(c["eur"]) for c in costs["by_cluster"]), Decimal(0)) == facts["compute_total"]
    assert sum((Decimal(p["eur"]) for p in costs["by_pipeline"]), Decimal(0)) == facts["compute_total"] - Decimal(
        "892.80"
    )


def test_cost_finds_the_table_nobody_reads(costs: Any) -> None:
    unread = FACTS["data-cost"]["unread_table"]
    first = costs["candidates"]["unread_tables"][0]
    assert (first["table"], Decimal(first["gb"]), Decimal(first["eur_per_month"]), first["queries"]) == (
        unread["table"],
        unread["gb"],
        unread["eur_per_month"],
        unread["queries"],
    )
    assert first["defined_in"] == ["pipeline/bronze/erp_orders_history_full.sql:4"]
    assert "Drop it once finance has signed the reconciliation off." in first["notes"]
    assert pin("DC1", "a one-off copy to drop after sign-off").startswith(first["defined_in"][0].split(":")[0])
    # Bronze tables the pipeline reads are not unread, though no consumer queries them.
    assert "bronze.erp_orders" not in {u["table"] for u in costs["candidates"]["unread_tables"]}


def test_cost_finds_the_full_reload_of_a_table_that_barely_changes(costs: Any) -> None:
    full = FACTS["data-cost"]["full_reload"]
    flagged = [r for r in costs["candidates"]["full_reloads"] if r["barely_changes"]]
    assert [r["job"] for r in flagged] == [full["job"]]
    reload = flagged[0]
    assert (reload["rows_written"], reload["rows_changed"], reload["max_changed_a_run"]) == (
        full["rows_written"],
        full["rows_changed"],
        full["max_changed_a_day"],
    )
    assert Decimal(reload["eur"]) == full["eur"] and reload["runs"] == FACTS["data-cost"]["period_days"]
    assert pin("DC2", "the job loads in full") in reload["evidence"]
    assert pin("DC2", "a full reload every morning") in reload["evidence"]


def test_cost_finds_the_schedule_faster_than_the_reads(costs: Any) -> None:
    frequent = FACTS["data-cost"]["too_frequent"]
    flagged = [s for s in costs["candidates"]["schedules"] if s["faster_than_reads"]]
    assert [s["job"] for s in flagged] == [frequent["job"]]
    job = flagged[0]
    assert Decimal(job["runs_a_day"]) == frequent["runs_a_day"] and job["runs_in_period"] == frequent["runs"]
    assert Decimal(job["eur"]) == frequent["eur"] and job["where"] == pin("DC3", "every 5 minutes")
    assert job["tables"][0]["table"] == frequent["table"]
    assert job["tables"][0]["consumer_queries"] == frequent["queries"]
    assert job["tables"][0]["consumer_max_a_day"] == 2


def test_cost_finds_the_cluster_that_runs_with_no_jobs(costs: Any) -> None:
    never = FACTS["data-cost"]["never_stops"]
    [cluster] = costs["candidates"]["compute_without_jobs"]
    assert cluster["cluster"] == never["cluster"]
    assert (Decimal(cluster["hours"]), Decimal(cluster["eur"])) == (never["hours"], never["eur"])
    assert (cluster["weekend_days_billed"], Decimal(cluster["weekend_eur"])) == (
        never["weekend_days"],
        never["weekend_eur"],
    )
    assert cluster["jobs_defined"] == cluster["jobs_billed"] == never["jobs"]
    assert cluster["days_up_24_hours"] == FACTS["data-cost"]["period_days"]


def test_cost_does_not_flag_the_most_expensive_job_whose_table_is_read_every_hour(costs: Any) -> None:
    decoy = FACTS["data-cost"]["decoy"]
    assert costs["by_job"][0]["job"] == decoy["job"] and Decimal(costs["by_job"][0]["eur"]) == decoy["eur"]
    candidates = costs["candidates"]
    assert decoy["table"] not in {u["table"] for u in candidates["unread_tables"]}
    assert not [r for r in candidates["full_reloads"] if r["job"] == decoy["job"] and r["barely_changes"]]
    assert not [s for s in candidates["schedules"] if s["job"] == decoy["job"] and s["faster_than_reads"]]
    table = next(t for t in costs["by_table"] if t["table"] == decoy["table"])
    assert table["consumer_queries"] == decoy["queries"] and len(table["consumers"]) == decoy["consumers"]
    assert DECOYS_AT[("DC-D1", "the most expensive job")] > 1


# ---------------------------------------------------------------------------- data-cost on small inputs


def test_allocate_splits_to_the_cent_and_adds_up() -> None:
    parts = cost.allocate(Decimal("10.00"), {"a": Decimal(1), "b": Decimal(1), "c": Decimal(1)})
    assert sum(parts.values()) == Decimal("10.00") and sorted(parts.values()) == [
        Decimal("3.33"),
        Decimal("3.33"),
        Decimal("3.34"),
    ]
    assert sum(cost.allocate(Decimal("0.05"), {"a": Decimal(0), "b": Decimal(0)}).values()) == Decimal("0.05")


@pytest.mark.parametrize(
    ("text", "value"),
    [("28.80", "28.80"), ("28,80", "28.80"), ("1.234,50", "1234.50"), ("1,234.50", "1234.50"), ("1,234", "1234")],
)
def test_to_decimal_reads_both_separators(text: str, value: str) -> None:
    assert cost.to_decimal(text) == Decimal(value)


def test_cost_reads_json_lines_with_other_field_names_and_hides_e_mail_consumers(tmp_path: Path) -> None:
    root = tmp_path / "platform"
    usage = [
        {"usage_date": "2026-10-01", "job_name": "nightly", "warehouse": "wh", "cost_eur": "4.00"},
        {"usage_date": "2026-10-02", "job_name": "nightly", "warehouse": "wh", "cost_eur": "4.00"},
        {"usage_date": "2026-10-01", "job_name": "wh", "warehouse": "wh", "cost_eur": "24.00"},
    ]
    write(root / "exports" / "billing.jsonl", "\n".join(json.dumps(u) for u in usage) + "\n")
    write(root / "exports" / "sizes.csv", "Table_Name;Size_GB;Cost\nmart.sales;10,5;0,42\nmart.old;20;0,80\n")
    write(
        root / "exports" / "access.csv",
        "Query_Date,User_Name,Object_Name\n2026-10-01,ana.petrovic@example.com,mart.sales\n2026-10-02,bi,mart.sales\n",
    )
    write(
        root / "jobs" / "nightly.yml",
        'name: nightly\ncron: "0 2 * * *"\nwarehouse: wh\nsteps:\n  - table: mart.sales\n',
    )
    result = run_json(COST, str(root))
    assert result["inputs"]["usage"]["fields"]["cluster"] == "warehouse"
    assert result["inputs"]["storage"]["fields"]["gb"] == "size_gb"
    assert result["totals"] == {
        "compute_eur": "32.00",
        "storage_eur_per_month": "1.22",
        "storage_gb": "30.5",
        "storage_eur_in_period": "0.08",
        "total_eur": "32.08",
    }
    assert result["period"]["storage_counted_as"] == "2 of 30 days"
    assert [u["table"] for u in result["candidates"]["unread_tables"]] == ["mart.old"]
    text = json.dumps(result)
    assert "ana.petrovic" not in text and not EMAIL.search(text) and "e-mail hidden" in text


def test_cost_prices_hours_with_a_rate_when_the_export_has_no_cost(tmp_path: Path) -> None:
    write(tmp_path / "usage.csv", "date,job,cluster,compute_hours\n2026-10-01,a,etl,1.50\n2026-10-02,a,etl,2.00\n")
    result = run_json(COST, str(tmp_path), "--rate", "etl=2.00")
    assert result["totals"]["compute_eur"] == "7.00"


def test_cron_counts_runs_in_a_period() -> None:
    every_five = cost.parse_cron("*/5 * * * *")
    weekdays = cost.parse_cron("30 8-16 * * 1-5")
    assert cost.runs_between(every_five, cost.date(2026, 10, 1), cost.date(2026, 10, 31)) == 288 * 31
    assert cost.runs_between(weekdays, cost.date(2026, 11, 2), cost.date(2026, 11, 8)) == 9 * 5
    assert cost.parse_cron("61 * * * *") is None and cost.parse_cron("@reboot") is None


def test_yaml_reader_reads_the_flat_shapes() -> None:
    text = (
        'name: job  # a comment\nschedule: "*/5 * * * *"\ndepends_on:\n  - a\n  - b\nsteps:\n  - task: x.y\n'
        "    sql: p/q.sql\n  - task: x.z\nallowed: [one, two]\nnested:\n  key: 'v # not a comment'\n"
    )
    assert cost.parse_yaml(text) == {
        "name": "job",
        "schedule": "*/5 * * * *",
        "depends_on": ["a", "b"],
        "steps": [{"task": "x.y", "sql": "p/q.sql"}, {"task": "x.z"}],
        "allowed": ["one", "two"],
        "nested": {"key": "v # not a comment"},
    }


# ---------------------------------------------------------------------------- data-migration on the fixture


def test_estate_reads_the_inventory_and_every_script(legacy: Any) -> None:
    facts = FACTS["data-migration"]
    assert legacy["inputs"]["jobs"] == facts["jobs"] == legacy["inputs"]["scripts_found"]
    assert legacy["inputs"]["scripts_missing"] == [] and legacy["inputs"]["scripts_not_in_inventory"] == []
    assert legacy["as_of"]["time"].startswith(facts["as_of"])


def test_estate_finds_the_dead_jobs(legacy: Any, repo: Path) -> None:
    facts = FACTS["data-migration"]
    assert legacy["status"]["dead"] == facts["dead"]
    assert len(legacy["status"]["on schedule"]) == facts["jobs"] - len(facts["dead"])
    jobs = {j["job"]: j for j in legacy["jobs"]}
    for key, name, _, pattern in PLANTED["data-migration"]:
        if key == "DM1":
            job = jobs[name.split()[0]]
            assert re.search(pattern, f"{job['job']},{job['script']},{job['last_run']} ")
            assert job["days_since_last_run"] > facts["dead_after_days"] and job["missed_runs"] >= 3
    as_export = run_json(ESTATE, str(repo / "legacy" / "inventory.csv"), "--as-of", "2026-11-04 06:00")
    assert as_export["status"]["dead"] == facts["dead"]


def test_estate_keeps_the_monthly_job_that_ran_on_its_day(legacy: Any) -> None:
    monthly = FACTS["data-migration"]["monthly_on_schedule"]
    job = next(j for j in legacy["jobs"] if j["job"] == monthly["job"])
    assert job["status"] == "on schedule" and job["missed_runs"] == 0
    assert job["last_due"].startswith(monthly["last_run"]) and job["next_due"].startswith(monthly["next_run"])
    assert job["cadence"] == "monthly on day 15 02:30"


def test_estate_finds_the_identical_scripts(legacy: Any) -> None:
    [group] = legacy["identical_scripts"]
    assert group["jobs"] == FACTS["data-migration"]["identical_sql"]
    assert len({tuple(t) for t in group["targets"].values()}) == 2
    assert legacy["near_identical_scripts"] == []


def test_estate_finds_the_file_link_the_inventory_does_not_declare(legacy: Any) -> None:
    hidden = FACTS["data-migration"]["undeclared_file_dependency"]
    assert [(u["writer"], u["reader"], u["what"]) for u in legacy["undeclared_links"]] == [
        (hidden["writer"], hidden["reader"], hidden["path"])
    ]
    assert len([link for link in legacy["links"] if link["kind"] == "file"]) == 3
    assert ["load_price_list", "stage_price_list"] in legacy["groups"]
    order = legacy["order"]
    assert order.index(hidden["writer"]) < order.index(hidden["reader"])


def test_estate_finds_the_outside_consumer_and_shows_only_the_placeholder(legacy: Any) -> None:
    outside = FACTS["data-migration"]["outside_consumer"]
    [send] = legacy["outside_consumers"]
    assert (send["job"], send["host"], send["scheme"], send["direction"]) == (
        outside["job"],
        outside["host"],
        "sftp",
        "out",
    )
    assert f"legacy/jobs/send_partner_orders.sh:{send['line']}" == pin("DM4", "the partner's SFTP server")
    job = next(j for j in legacy["jobs"] if j["job"] == outside["job"])
    assert job["credentials"] == [{"line": send["line"], "placeholder": outside["secret"], "literal": False}]
    assert "SFTP_PASSWORD" in legacy["env"]


def test_estate_finds_two_jobs_writing_one_table_at_the_same_minute(legacy: Any) -> None:
    same = FACTS["data-migration"]["same_minute_same_table"]
    [clash] = legacy["same_target"]
    assert (clash["target"], clash["jobs"], clash["min_minutes_apart"], clash["at_once"]) == (
        same["table"],
        same["jobs"],
        0,
        True,
    )
    assert set(clash["schedules"].values()) == {same["schedule"]}


# ---------------------------------------------------------------------------- data-migration on small inputs


def test_estate_never_prints_a_literal_secret(tmp_path: Path) -> None:
    write(
        tmp_path / "jobs" / "push.sh",
        '#!/bin/sh\nlftp -u "acme,hunter2secret" sftp://files.example.org <<EOF\nput /data/out.csv\nEOF\n'
        "curl -T /data/out.csv ftp://bob:s3cretvalue@ftp.example.org/in/\n"
        'PGPASSWORD=topsecretvalue psql -c "select 1"\n',
    )
    write(tmp_path / "jobs" / "make.sql", "insert into dw.out select * from src.a;\n")
    write(
        tmp_path / "inventory.csv",
        "job,script,schedule,last_run,owner\npush,jobs/push.sh,0 5 * * *,2026-11-04 05:00,ops@example.com\n"
        "make,jobs/make.sql,0 4 * * *,2026-11-04 04:00,b.stanar\n",
    )
    result = run_json(ESTATE, str(tmp_path / "inventory.csv"))
    text = json.dumps(result)
    for secret in ("hunter2secret", "s3cretvalue", "topsecretvalue", "ops@example.com"):
        assert secret not in text
    job = next(j for j in result["jobs"] if j["job"] == "push")
    assert {c["literal"] for c in job["credentials"]} == {True} and len(job["credentials"]) == 3
    assert {o["host"] for o in result["outside_consumers"]} == {"files.example.org", "ftp.example.org"}
    assert all(o["direction"] == "out" for o in result["outside_consumers"])


def test_estate_reads_a_crontab_and_finds_a_transitive_link(tmp_path: Path) -> None:
    write(tmp_path / "a.sql", "insert into stage.a select * from src.x;\n")
    write(tmp_path / "b.sql", "insert into stage.b select * from stage.a;\n")
    write(tmp_path / "c.sql", "insert into mart.c select * from stage.a join stage.b using (id);\n")
    write(tmp_path / "crontab", 'MAILTO=""\n# nightly\n0 1 * * * psql -f /opt/etl/a.sql\n0 2 * * * psql -f b.sql\n')
    result = run_json(ESTATE, str(tmp_path / "crontab"), "--as-of", "2026-11-04 03:00")
    assert result["inputs"]["kind"] == "crontab" and result["inputs"]["jobs"] == 2
    assert {j["job"]: j["cadence"] for j in result["jobs"]} == {"a": "daily 01:00", "b": "daily 02:00"}
    assert result["inputs"]["scripts_not_in_inventory"] == ["c.sql"]
    assert [(link["writer"], link["reader"], link["declared"]) for link in result["links"]] == [("a", "b", "no")]


def test_estate_counts_missed_runs_against_the_schedule() -> None:
    cron = estate.parse_cron("0 6 * * 1")
    last = estate.datetime(2026, 10, 5, 6, 0)
    assert estate.missed_since(cron, last, estate.datetime(2026, 11, 4, 5, 0)) == 4
    assert estate.cadence("0 6 * * 1", cron) == "weekly Mon 06:00"
    assert estate.cadence("*/30 8-16 * * 1-5", estate.parse_cron("*/30 8-16 * * 1-5")).startswith("every 30 minutes")


# ---------------------------------------------------------------------------- data-product on the fixture


def test_product_finds_its_inputs(served: Any) -> None:
    facts = FACTS["data-product"]
    inputs = served["inputs"]
    assert (inputs["definition_sql"], inputs["sample"], inputs["job_definition"]) == (
        "pipeline/gold/sales_daily.sql",
        facts["sample"],
        "jobs/build_sales_daily.yaml",
    )
    assert inputs["query_log"]["file"] == "ops/query_log.csv" and inputs["check_results"]["file"] == "ops/checks.jsonl"
    assert served["sample"]["rows"] == facts["sample_rows"]


def test_product_finds_the_real_grain(served: Any) -> None:
    facts = FACTS["data-product"]
    documented, *_ = served["sample"]["grain_tested"]
    assert documented["key"] == ["store_id", "sales_date"]
    assert (documented["distinct_keys"], documented["keys_with_more_than_one_row"], documented["max_rows_a_key"]) == (
        facts["store_days"],
        facts["store_days_with_two_rows"],
        2,
    )
    assert documented["columns_that_differ_inside_a_key"]["currency"] == facts["store_days_with_two_rows"]
    assert {"sales_date": "2026-10-04", "store_id": "S-030"} in documented["examples"]
    assert facts["real_grain"] in served["sample"]["smallest_unique_keys"]
    assert served["sample"]["value_counts"]["currency"] == facts["rows_by_currency"]
    key_check = next(c for c in served["checks"]["on_the_table"] if c["key_columns"])
    assert key_check["key_columns"] == facts["real_grain"] and key_check["where"].startswith("checks/gold.yaml:")
    stated = served["product_document"]["stated"]["grain"]
    assert stated["where"] == pin("DPR4", "the documented grain") and "store and day" in stated["text"]


def test_product_finds_the_personal_column_and_shows_no_value(served: Any, repo: Path) -> None:
    facts = FACTS["data-product"]
    column = facts["personal_column"]
    found = served["sample"]["personal_columns"]
    assert list(found) == [column] and found[column]["values_that_look_personal"] == facts["sample_rows"]
    assert served["definition"]["personal_by_name"] == [column]
    line = next(c["line"] for c in served["definition"]["columns"] if c["column"] == column)
    assert f"pipeline/gold/sales_daily.sql:{line}" == pin("DPR2", "the served table carries an e-mail")
    assert column not in served["sample"]["value_counts"] and column not in served["sample"]["distinct"]


def test_product_names_the_conflicting_definitions_of_net_revenue(served: Any) -> None:
    net = served["definitions"]["net_revenue"]
    places = [d["where"] for d in net["definitions"]]
    assert pin("DPR1", "net revenue without returns in the product document") in places
    assert pin("DPR1", "net revenue with returns in the BI metrics") in places
    assert "pipeline/gold/sales_daily.sql:13" in places
    [conflict] = net["term_conflicts"]
    assert conflict["term"] == "returns"
    assert conflict["included_in"] == [pin("DPR1", "net revenue with returns in the BI metrics")]
    assert conflict["excluded_in"] == [pin("DPR1", "net revenue without returns in the product document")]
    assert conflict["not_in_the_sql"] == ["pipeline/gold/sales_daily.sql:13"]


def test_product_leaves_the_documented_kg_eq_alone(served: Any) -> None:
    kg = served["definitions"]["kg_eq"]
    assert pin("DPR-D1", "kg_eq is documented", planted=False) in [d["where"] for d in kg["definitions"]]
    assert kg["term_conflicts"] == []
    assert all(not c["term_conflicts"] for name, c in served["definitions"].items() if name != "net_revenue")


def test_product_sees_no_owner_and_no_freshness_promise_but_the_job_sla(served: Any) -> None:
    facts = FACTS["data-product"]
    document = served["product_document"]
    assert document["file"] == facts["document"] and document["names_an_owner"] is False
    assert document["states_a_time"] == []
    assert document["stated"]["questions"]["where"] == pin("DPR3", "no owner named")
    assert document["stated"]["refreshed"]["where"] == pin("DPR3", "no freshness promise")
    job = served["job"]
    assert job["sla"] == facts["sla_in_job"] and f"{job['file']}:{job['sla_line']}" == pin(
        "DPR3", "the job has an SLA the document leaves out"
    )
    assert document["documented_not_in_table"] == [] and document["in_table_not_documented"] == []
    assert served["contract"] == [
        {"file": "contracts/erp.yaml", "role": "a source contract that lists the table as a consumer"}
    ]


def test_product_counts_consumers_freshness_and_checks(served: Any) -> None:
    facts = FACTS["data-product"]
    consumers = served["consumers"]
    assert [c["consumer"] for c in consumers["by_consumer"]] == facts["consumers"]
    assert consumers["queries"] == facts["queries"]
    assert sum(c["max_a_day"] == 24 for c in consumers["by_consumer"]) == 4
    fresh = served["freshness"]
    assert fresh["last_success_end"] == FACTS["pipeline-incident"]["gold_last_built"]
    assert fresh["not_successful_on"] == FACTS["pipeline-incident"]["gold_skipped"]
    assert served["sample"]["latest_freshness_value"] == FACTS["pipeline-incident"]["gold_last_built"]
    results = served["checks"]["results"]
    assert results["sales_daily_fresh"]["not_passed_on"] == ["2026-11-03", "2026-11-04"]
    assert results["customers_email_format"]["statuses"] == {"warn": 31}
    assert served["checks"]["test_cases"]["sales_daily_key_unique"][0]["result"] == "fail"
    assert served["history"]["pipeline/gold/sales_daily.sql"]


# ---------------------------------------------------------------------------- data-product on small inputs


def test_product_profiles_a_small_sample_without_printing_personal_values(tmp_path: Path) -> None:
    write(
        tmp_path / "models" / "mart_customers.sql",
        "create or replace table mart.customers as\nselect\n  c.id as customer_id,\n  c.mail as contact_email,\n"
        "  c.iban as payout_account,\n  c.region\nfrom stage.customers as c;\n",
    )
    write(
        tmp_path / "data" / "customers.jsonl",
        "\n".join(
            json.dumps(
                {"customer_id": i, "contact_email": f"person{i}@example.com", "payout_account": iban, "region": r}
            )
            for i, (iban, r) in enumerate([("RS35105008123123123173", "north"), ("RS35105008123123123173", "south")])
        )
        + "\n",
    )
    write(tmp_path / "docs" / "customers.md", "# mart.customers\n\nGrain: one row per customer.\nOwner: CRM team.\n")
    result = run_json(PRODUCT, str(tmp_path), "--table", "mart.customers", "--grain", "customer_id")
    text = json.dumps(result)
    assert not EMAIL.search(text) and "RS35105008123123123173" not in text
    personal = result["sample"]["personal_columns"]
    assert set(personal) == {"contact_email", "payout_account"}
    assert personal["payout_account"]["by_value"] == "bank account"
    assert result["sample"]["grain_tested"][0]["unique"] is True
    assert result["product_document"]["names_an_owner"] is True
    assert result["definition"]["personal_by_name"] == ["contact_email"]


def test_term_states_read_negation() -> None:
    assert product.term_states("returns are not deducted", False) == {"returns": "excluded"}
    assert product.term_states("gross minus returns and discounts", False) == {
        "returns": "included",
        "discounts": "included",
    }
    assert product.term_states("sum(amount) - sum(return_amount)", True) == {}


# ---------------------------------------------------------------------------- personal data never reaches the output


def test_no_script_output_shows_a_personal_value(repo: Path, costs: Any, legacy: Any, served: Any) -> None:
    values: set[str] = set()
    for path in [*repo.glob("sources/crm/*/contacts.csv"), repo / "samples/gold/sales_daily.csv"]:
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                values |= {row[c] for c in ("email", "customer_email", "phone", "iban") if row.get(c)}
    assert len(values) > 1000
    for output in (costs, legacy, served):
        text = json.dumps(output, ensure_ascii=False)
        assert not [v for v in values if v in text]
        assert not EMAIL.search(text)


def test_the_scripts_run_with_isolated_python(repo: Path) -> None:
    done = subprocess.run(
        [sys.executable, "-I", str(PRODUCT), str(repo), "--table", "gold.stock_levels"],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    result = json.loads(done.stdout)
    assert result["definition"]["file"] == "pipeline/gold/stock_levels.sql" and result["sample"] is None
    assert result["job"]["job"] == "refresh_stock"
