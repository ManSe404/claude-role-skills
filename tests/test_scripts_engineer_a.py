"""The data-engineer scripts of source-profile, source-contract, pipeline-incident and data-quality: on the
acme-pipeline fixture against its answer key, and on small cases of their own."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import build_fixture
import pytest
from conftest import ROOT, load, run_json
from test_fixture_acme_pipeline import DECOYS, FACTS, PLANTED

SKILLS = ROOT / "plugins" / "data-engineer" / "skills"
SOURCE_FORMAT = SKILLS / "source-profile" / "scripts" / "source_format.py"
CONTRACT_CHECK = SKILLS / "source-contract" / "scripts" / "contract_check.py"
RUN_TRACE = SKILLS / "pipeline-incident" / "scripts" / "run_trace.py"
QUALITY = SKILLS / "data-quality" / "scripts" / "quality_summary.py"
source_format = load(SOURCE_FORMAT)
contract_check = load(CONTRACT_CHECK)
run_trace = load(RUN_TRACE)
quality_summary = load(QUALITY)

Check = Callable[[dict[str, Any]], bool]


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-pipeline fixture with its extras (deliveries, run records, checks), built once for this module."""
    target = tmp_path_factory.mktemp("fixture") / "acme-pipeline"
    build_fixture.build("acme-pipeline", target)
    return target


def run_in(repo: Path, script: Path, *args: str) -> Any:
    """Run a script from inside the repository, the way Claude runs it, and parse its JSON."""
    done = subprocess.run(
        [sys.executable, str(script), *args], cwd=repo, capture_output=True, text=True, check=True, timeout=120
    )
    return json.loads(done.stdout)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def column(report: dict[str, Any], file: str, name: str) -> dict[str, Any]:
    entry = next(f for f in report["files"] if f["file"] == file)
    return next(c for c in entry["columns"] if c["name"] == name)


def file_of(report: dict[str, Any], name: str) -> dict[str, Any]:
    return next(f for f in report["files"] if f["file"] == name)


# ---------------------------------------------------------------------------- source_format on the fixture


@pytest.fixture(scope="module")
def profile(pipeline: Path) -> dict[str, Any]:
    facts = FACTS["source-profile"]
    out: dict[str, Any] = run_in(
        pipeline, SOURCE_FORMAT, facts["previous"], facts["delivery"], "--doc", facts["vendor_document"]
    )
    return out


def conflict(report: dict[str, Any], what: str, where: str) -> bool:
    return any(c["what"] == what and where in (c.get("file"), c.get("column")) for c in report["doc"]["conflicts"])


SP: dict[str, Check] = {
    "SP1": lambda r: (
        file_of(r, "activities.csv")["delimiter"] == ";"
        and conflict(r, "delimiter", "activities.csv")
        and column(r, "activities.csv", "deal_value")["numbers"]["decimal_comma"]
        == FACTS["source-profile"]["decimal_comma_values"]
        and column(r, "customers.csv", "credit_limit")["numbers"]["decimal_point"]
        == FACTS["source-profile"]["decimal_point_values"]
        and conflict(r, "decimal separator", "activities.deal_value")
    ),
    "SP2": lambda r: (
        column(r, "contacts.csv", "consent_date")["date_formats"] == FACTS["source-profile"]["consent_date_formats"]
        and conflict(r, "date format", "contacts.consent_date")
    ),
    "SP3": lambda r: (
        column(r, "contacts.csv", "job_title")["null_tokens"] == FACTS["source-profile"]["null_tokens"]["tokens"]
    ),
    "SP4": lambda r: (
        file_of(r, "customers.csv")["key"]["distinct"] == FACTS["source-profile"]["customer_ids"]["distinct"]
        and file_of(r, "customers.csv")["key"]["examples"] == FACTS["source-profile"]["customer_ids"]["duplicated"]
        and set(file_of(r, "customers.csv")["key"]["columns_that_differ"]) == {"city", "credit_limit"}
    ),
    "SP5": lambda r: any(
        ref["file"] == "contacts.csv"
        and ref["points_to"] == "customers.csv"
        and ref["orphan_rows"] == FACTS["source-profile"]["orphan_contacts"]
        for ref in r["references"]
    ),
    "SP6": lambda r: (
        column(r, "customers.csv", "closed_on")["placeholders"] == {"9999-12-31": 568}
        and column(r, "customers.csv", "created_on")["placeholders"] == {"1900-01-01": 24}
        and conflict(r, "placeholder where the document says empty", "customers.closed_on")
    ),
    "SP7": lambda r: (
        r["history"]["deliveries"][1]["files"]["activities.csv"]["added"]
        == [FACTS["source-profile"]["added_column"]["column"]]
    ),
    "SP8": lambda r: (
        {c: column(r, "contacts.csv", c.split(".")[1])["values"] for c in FACTS["source-profile"]["personal_data"]}
        == FACTS["source-profile"]["personal_data"]
        and {"email", "phone", "iban"} <= set(file_of(r, "contacts.csv")["personal_columns"])
    ),
    "SP9": lambda r: (
        r["doc"]["documented_not_delivered"] == FACTS["source-profile"]["documented_not_delivered"]
        and r["doc"]["delivered_not_documented"] == FACTS["source-profile"]["delivered_not_documented"]
    ),
}


@pytest.mark.parametrize("key", sorted({e[0] for e in PLANTED["source-profile"]}))
def test_source_format_surfaces_each_planted_problem(profile: dict[str, Any], key: str) -> None:
    assert SP[key](profile), key


def test_source_format_counts_the_rows_and_drift_of_both_deliveries(profile: dict[str, Any]) -> None:
    facts = FACTS["source-profile"]
    assert {f["file"]: f["rows"] for f in profile["files"]} == facts["rows"]
    first, second = profile["history"]["deliveries"]
    assert {name: entry["rows"] for name, entry in first["files"].items()} == facts["rows_previous"]
    assert second["files"]["activities.csv"]["incremental"] is True  # yesterday's activities only: no deletes
    assert second["files"]["customers.csv"]["keys_gone"] == 0
    assert {f["file"]: f["delimiter"] for f in profile["files"]} == facts["delimiters"]


def test_source_format_leaves_the_decoys_as_consistent(profile: dict[str, Any]) -> None:
    decoy_columns = {"customers.parent_customer_id", "customers.status"}
    assert not [c for c in profile["doc"]["conflicts"] if c.get("column") in decoy_columns]
    consistent = {c["column"]: c for c in profile["doc"]["consistent"]}
    optional = FACTS["source-profile"]["empty_optional_column"]
    assert column(profile, "customers.csv", "parent_customer_id")["empty"] == optional["empty_rows"]
    assert "empty in every row" in consistent[optional["column"]]["what"]
    assert consistent["customers.status"]["data"]["X"] == FACTS["source-profile"]["status_x_rows"]
    assert not [h for h in profile["hits"] if "parent_customer_id" in h or " status" in h]
    assert {e[0] for e in DECOYS["source-profile"]} == {"SP-D1", "SP-D2"}


# ---------------------------------------------------------------------------- source_format on small cases


def test_source_format_reads_formats_tokens_and_composite_keys(tmp_path: Path) -> None:
    write(tmp_path / "a" / "orders.csv", "order_id,line_no,amount,day\nA,1,1.20,2026-01-05\nA,2,2.30,2026-01-07\n")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "orders.csv").write_bytes(
        "﻿order_id;line_no;amount;day\r\nA;1;1,20;05.01.2026\r\nA;2;-;2026-01-07\r\nB;1;NULL;\r\n".encode()
    )
    write(tmp_path / "b" / "events.jsonl", '{"id": "e1", "op": "D"}\n{"id": "e2", "op": null}\n')
    result = run_json(SOURCE_FORMAT, str(tmp_path / "a"), str(tmp_path / "b"))
    orders = file_of(result, "orders.csv")
    assert (orders["delimiter"], orders["byte_order_mark"], orders["line_endings"]) == (";", True, "CRLF")
    assert orders["key"]["columns"] == ["order_id", "line_no"] and orders["key"]["duplicated_keys"] == 0
    amount = column(result, "orders.csv", "amount")
    assert amount["null_tokens"] == {"-": 1, "NULL": 1}
    day = column(result, "orders.csv", "day")
    assert day["date_formats"] == {"DD.MM.YYYY": 1, "YYYY-MM-DD": 1}
    change = result["history"]["deliveries"][1]["files"]["orders.csv"]
    assert change["delimiter_before"] == "," and change["format_changes"]["day"] == "YYYY-MM-DD -> DD.MM.YYYY"
    assert column(result, "events.jsonl", "op")["delete_marker"] is True
    assert column(result, "events.jsonl", "op")["null_tokens"] == {"null (JSON)": 1}


def test_source_format_reads_the_values_a_document_lists() -> None:
    assert source_format.documented_values("A active, I inactive, X closed by credit control") == ["A", "I", "X"]
    assert source_format.documented_values("sr, hu or en") == ["sr", "hu", "en"]
    assert source_format.documented_values("the account's registered name") == []
    doc = source_format.parse_doc(
        "## x.csv\n\n| column | type |\n|---|---|\n| `a` | text |\nSemicolon-separated.", ["x.csv"]
    )
    assert doc["sections"] == {"x.csv": {"a": {"type": "text", "meaning": ""}}} and doc["claims"]["delimiter"] == ";"


def test_source_format_flags_weekdays_without_rows(tmp_path: Path) -> None:
    rows = "\n".join(f"E{n},2026-11-{d:02d}" for n, d in enumerate([2, 3, 5, 6, 9]))  # no Wednesday 4th
    write(tmp_path / "d" / "events.csv", f"event_id,event_date\n{rows}\n")
    result = run_json(SOURCE_FORMAT, str(tmp_path / "d"))
    assert file_of(result, "events.csv")["date_spans"][0]["weekdays_without_rows"] == ["2026-11-04"]


# ---------------------------------------------------------------------------- contract_check on the fixture


@pytest.fixture(scope="module")
def contract(pipeline: Path) -> dict[str, Any]:
    out: dict[str, Any] = run_in(
        pipeline, CONTRACT_CHECK, "check", FACTS["source-contract"]["contract"], "--deliveries", "ops/deliveries.jsonl"
    )
    return out


def shape_of(example: str) -> str:
    return str(contract_check.shape(example))


def amount_shapes(r: dict[str, Any]) -> dict[str, list[str]]:
    return {f["day"]: list(f["column_problems"]["amount"]["type"]["shapes"]) for f in r["files"]}


SC: dict[str, Check] = {
    "SC1": lambda r: (
        r["arrivals"]["deliveries"] == FACTS["source-contract"]["erp_delivery_days"]
        and r["arrivals"]["late"] == FACTS["source-contract"]["late_days"]
        and tuple(r["arrivals"]["late_between"]) == FACTS["source-contract"]["late_arrivals_between"]
        and r["arrivals"]["on_time"] == FACTS["source-contract"]["on_time_days"]
        and set(r["arrivals"]["on_time_by_weekday"]) == {"Sat", "Sun"}
        and r["contract"]["deliver_by"] == FACTS["source-contract"]["deliver_by"]
    ),
    "SC2": lambda r: (
        amount_shapes(r) == {d: [shape_of(s)] for d, s in FACTS["source-contract"]["amount_format"].items()}
        and all(f["column_problems"]["amount"]["type"]["expected"] == "integer (cents)" for f in r["files"])
    ),
    "SC3": lambda r: (
        {(g["field"], g["value"]) for g in r["open_in_the_contract"]} >= {("owner", "TBD"), ("change_process", "TBD")}
    ),
    "SC4": lambda r: (
        r["columns_over_time"]["sales_rep_code"]["missing_from"] == ["2026-11-04"]
        and next(f for f in r["files"] if f["day"] == "2026-11-04")["missing_columns"]
        == [FACTS["source-contract"]["missing_column"]]
    ),
}


@pytest.mark.parametrize("key", sorted({e[0] for e in PLANTED["source-contract"]}))
def test_contract_check_surfaces_each_planted_conflict(contract: dict[str, Any], key: str) -> None:
    assert SC[key](contract), key


def test_contract_check_finds_the_deliveries_and_leaves_the_decoy(contract: dict[str, Any]) -> None:
    assert [f["file"] for f in contract["files"]] == [
        f"sources/erp/{d}/orders.csv" for d in ("2026-11-02", "2026-11-03", "2026-11-04")
    ]
    assert contract["understood"]["deliveries"]["missing"] == []
    latest = contract["files"][-1]
    assert latest["allowed_values_seen"]["status"]["on_hold"] == FACTS["source-contract"]["on_hold_rows"]
    assert not [f for f in contract["files"] if "status" in f["column_problems"]]
    assert not [h for h in contract["hits"] if "on_hold" in h or "status" in h]
    assert all(rule["checked"] for rule in latest["quality"])


def test_contract_check_drafts_a_contract_for_the_crm(pipeline: Path) -> None:
    facts = FACTS["source-profile"]
    result = run_in(
        pipeline, CONTRACT_CHECK, "draft", facts["previous"], facts["delivery"],
        "--deliveries", "ops/deliveries.jsonl", "--doc", facts["vendor_document"],
    )  # fmt: skip
    proposals = {p["file"]: p for p in result["proposals"]}
    assert proposals["customers.csv"]["key_candidates"] == []
    assert proposals["activities.csv"]["columns_not_in_every_delivery"] == ["channel"]
    deal = next(c for c in proposals["activities.csv"]["columns"] if c["name"] == "deal_value")
    assert deal["type"] == "decimal" and deal["number_format"]["decimal_comma"] == facts["decimal_comma_values"]
    contacts = {c["name"]: c for c in proposals["contacts.csv"]["columns"]}
    assert {n for n, c in contacts.items() if c.get("personal")} >= {"email", "phone", "iban"}
    assert "values" not in contacts["email"]
    assert proposals["contacts.csv"]["document"]["in_document_not_delivered"] == ["preferred_language"]
    assert proposals["customers.csv"]["arrivals"]["late"] == 0  # the CRM is on time against the vendor's 05:00


# ---------------------------------------------------------------------------- contract_check on small cases


def test_contract_check_reads_the_yaml_shapes_of_a_contract() -> None:
    text = """# a contract
name: feed
owner: "Data team"   # agreed
columns:
  - name: id
    type: bigint
    required: true
  - name: kind
    allowed: [a, 'b', c]
quality:
  - "id is unique"
notes: |
  first line
  second line
"""
    data = contract_check.parse_yaml(text)
    assert data["owner"] == "Data team" and data["notes"] == "first line\nsecond line"
    assert data["columns"] == [
        {"name": "id", "type": "bigint", "required": True},
        {"name": "kind", "allowed": ["a", "b", "c"]},
    ]
    mapping = contract_check.parse_yaml("fields:\n  id:\n    type: int\n  day:\n    type: date\n")
    assert [c["name"] for c in contract_check.columns_of(mapping)] == ["id", "day"]


def test_contract_check_rules_and_shapes() -> None:
    rows = [{"a": "1", "b": "x", "n": "2,5"}, {"a": "1", "b": "x", "n": "-1"}, {"a": "2", "b": "", "n": "3"}]
    header = ["a", "b", "n"]
    assert contract_check.rule_result("n > 0", rows, header)["rows_breaking"] == 1
    assert contract_check.rule_result("a and b together are unique", rows, header)["rows_breaking"] == 2
    assert contract_check.rule_result("b is not null", rows, header)["rows_breaking"] == 1
    assert contract_check.rule_result("totals reconcile with finance", rows, header)["checked"] is False
    assert [contract_check.shape(v) for v in ("7110.00", "18846,00", "1.234,50")] == ["9.99", "9,99", "9.999,99"]
    assert contract_check.path_pattern("sources/erp/{date}/orders.csv").search("x/sources/erp/2026-11-03/orders.csv")


def test_contract_check_reads_a_csv_delivery_log_in_utc(tmp_path: Path) -> None:
    log = write(
        tmp_path / "log.csv",
        "Path,Received_At\nin/2026-11-02/f.csv,2026-11-02T04:30:00Z\nin/2026-11-03/f.csv,2026-11-03T06:10:00Z\n",
    )
    records = contract_check.read_records(log)
    assert contract_check.understood(records, contract_check.LOG_FIELDS)["fields"] == {
        "file": "Path",
        "arrived_at": "Received_At",
    }
    pattern = contract_check.path_pattern("in/{date}/f.csv")
    result = contract_check.arrivals(records, pattern, None, "06:00", "Europe/Belgrade")
    assert (result["late"], result["on_time"], result["late_between"]) == (1, 1, ["07:10", "07:10"])


# ---------------------------------------------------------------------------- run_trace on the fixture


@pytest.fixture(scope="module")
def trace(pipeline: Path) -> dict[str, Any]:
    out: dict[str, Any] = run_in(pipeline, RUN_TRACE, ".", "--git")
    return out


def failing_column(r: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = r["changed_since_the_last_good_run"]["input_files"][0]["the_failing_column"]
    return entry


PI: dict[str, Check] = {
    "PI1": lambda r: (
        r["run"]["run_id"] == FACTS["pipeline-incident"]["run_id"]
        and r["run"]["first_failed"]["task"] == FACTS["pipeline-incident"]["failed_task"]
        and r["run"]["first_failed"]["layer"] == FACTS["pipeline-incident"]["layer"]
        and r["run"]["error_parts"]["value"] == FACTS["pipeline-incident"]["error_value"]
        and f"{r['code']['file']}:{r['code']['line']}" == FACTS["pipeline-incident"]["cast_at"]
        and "cast(amount as numeric(12, 2))" in r["code"]["text"]
        and r["last_good"]["run_id"].endswith(FACTS["pipeline-incident"]["last_good_delivery"] + "-1")
        and failing_column(r)["last_good"] == {"decimal point": 401}
        and failing_column(r)["failed"] == {"decimal comma": FACTS["pipeline-incident"]["rows_in_bad_delivery"]}
    ),
    "PI2": lambda r: (
        r["past_incidents"][0]["date"] == FACTS["pipeline-incident"]["past_incident"]
        and r["past_incidents"][0]["where_those_are_used"][FACTS["pipeline-incident"]["safe_parse"]]
        == {"called_in": [FACTS["pipeline-incident"]["already_safe"]], "called_in_the_failing_file": False}
    ),
    "PI3": lambda r: (
        sorted({s["file"] for s in r["same_expression_elsewhere"]}) == FACTS["pipeline-incident"]["same_weakness"]
    ),
    "PI4": lambda r: (
        r["downstream"][0]["last_built"] == FACTS["pipeline-incident"]["gold_last_built"]
        and [x["status"] for x in r["downstream"][0]["runs_since_the_failure"]] == ["skipped", "skipped"]
        and "docs/products/sales_daily.md" in r["downstream"][0]["documents_naming_its_tables"]
        and r["downstream"][0]["sla"] == "08:00"
    ),
}


@pytest.mark.parametrize("key", sorted({e[0] for e in PLANTED["pipeline-incident"]}))
def test_run_trace_surfaces_each_planted_problem(trace: dict[str, Any], key: str) -> None:
    assert PI[key](trace), key


def test_run_trace_lists_the_failures_and_leaves_the_decoys(trace: dict[str, Any]) -> None:
    facts = FACTS["pipeline-incident"]
    assert [f["run_id"] for f in trace["failed_runs"]] == facts["failed_runs"]
    assert [s["run_id"] for s in trace["same_error_since"]] == facts["failed_runs"][1:]
    warning = trace["warnings_in_the_run"][0]
    assert (
        warning["task"] == "wait_for_file"
        and f"{facts['late_file']['minutes_after_start']} minutes" in warning["message"]
    )
    assert (warning["runs_with_this_warning"], warning["of_which_the_failed_task_succeeded"]) == (23, 21)
    assert facts["already_safe"] not in {s["file"] for s in trace["same_expression_elsewhere"]}
    assert trace["changed_since_the_last_good_run"]["commits_between"] == []
    assert trace["changed_since_the_last_good_run"]["rows_read"] == {"last_good": 401, "failed": 1038}
    assert trace["tables_without_a_check_result_that_day"] == ["silver.orders"]
    assert all(trace["understood"][k]["missing"] == [] for k in ("runs", "checks", "deliveries"))


def test_run_trace_picks_a_run_by_job_and_day(pipeline: Path) -> None:
    result = run_in(pipeline, RUN_TRACE, ".", "--job", "load_erp_orders", "--date", "2026-11-04")
    assert result["run"]["run_id"] == "load_erp_orders-2026-11-04-1"
    entry = result["changed_since_the_last_good_run"]["input_files"][0]
    assert entry["columns_removed"] == ["sales_rep_code"]
    assert run_in(pipeline, RUN_TRACE, ".", "--run", "no-such-run")["run"] is None


# ---------------------------------------------------------------------------- run_trace on small cases


def test_run_trace_reads_other_field_names_and_shapes(tmp_path: Path) -> None:
    write(
        tmp_path / "logs" / "task_runs.csv",
        "Run,Pipeline,Step,State,Started_At,Finished_At,Error_Message\n"
        "r1,daily,load,succeeded,2026-01-01T05:00:00,2026-01-01T05:01:00,\n"
        "r1,daily,model,succeeded,2026-01-01T05:02:00,2026-01-01T05:03:00,\n"
        "r2,daily,load,succeeded,2026-01-02T05:00:00,2026-01-02T05:01:00,\n"
        "r2,daily,model,error,2026-01-02T05:02:00,2026-01-02T05:03:00,"
        '"model: value too long for x (models/m.sql line 2)"\n',
    )
    write(tmp_path / "models" / "m.sql", "select\n  amount::numeric(10,2) as amount\nfrom t\n")
    write(tmp_path / "models" / "n.sql", "select price::numeric(10,2) from p\n")
    write(tmp_path / "pipelines" / "daily.yaml", "name: daily\nsteps:\n  - task: load\n  - task: model\n")
    result = run_json(RUN_TRACE, str(tmp_path))
    assert result["understood"]["runs"]["fields"]["status"] == "State"
    assert result["understood"]["runs"]["fields"]["start"] == "Started_At"
    assert result["run"]["run_id"] == "r2" and result["last_good"]["run_id"] == "r1"
    assert result["code"]["text"] == "amount::numeric(10,2) as amount"
    assert result["same_expression_elsewhere"] == [
        {"file": "models/n.sql", "line": 1, "text": "select price::numeric(10,2) from p"}
    ]


def test_run_trace_cleans_error_text_and_signs_errors() -> None:
    assert run_trace.clean("bad row ana@example.com RS35105008123123123173") == "bad row [e-mail] [iban]"
    one = run_trace.signature('silver.orders: invalid input syntax for type numeric: "18846,00" (x.sql line 18)')
    two = run_trace.signature('silver.orders: invalid input syntax for type numeric: "5388,00" (x.sql line 18)')
    assert one == two == "invalid input syntax for type numeric"


# ---------------------------------------------------------------------------- quality_summary on the fixture


@pytest.fixture(scope="module")
def quality(pipeline: Path) -> dict[str, Any]:
    out: dict[str, Any] = run_in(pipeline, QUALITY, ".")
    return out


DQ: dict[str, Check] = {
    "DQ1": lambda r: any(
        c["check"] == FACTS["data-quality"]["always_warns"]["check"]
        and c["warn"] == FACTS["data-quality"]["always_warns"]["days"]
        and tuple(c["failing_rows"]) == FACTS["data-quality"]["always_warns"]["failing_rows"]
        for c in r["warn_every_day"]
    ),
    "DQ2": lambda r: (
        [c["check"] for c in r["cannot_fail"]] == [FACTS["data-quality"]["cannot_fail"]["check"]]
        and r["cannot_fail"][0]["where"] == "checks/silver.yaml:7"
        and r["without_a_test_case"] == FACTS["data-quality"]["without_a_test_case"]
    ),
    "DQ3": lambda r: any(
        f["table"] == FACTS["data-quality"]["freshness"]["table"]
        and f["sla"] == FACTS["data-quality"]["freshness"]["sla"]
        and f["failed_on"] == FACTS["data-quality"]["freshness"]["failed_on"]
        and f["days_not_built_by_the_sla"] == FACTS["data-quality"]["freshness"]["failed_on"]
        for f in r["freshness"]
    ),
    "DQ4": lambda r: (
        {k: v for k, v in r["quarantine"]["unknown_store_id"]["step_change"].items()}
        == {k: v for k, v in FACTS["data-quality"]["quarantine"].items() if k not in ("rule", "store")}
        and next(v for v in r["quarantine"]["unknown_store_id"]["values"] if v["value"] == "S-031")
        == {"value": "S-031", "rows": 665, "first": "2026-10-28", "last": "2026-11-02", "in_reference": False}
        and r["quarantine"]["unknown_store_id"]["reference"]["last_in_order"] == ["S-030"]
        and r["quarantine_watched_by_a_check"] is False
    ),
    "DQ5": lambda r: (
        {t: r["verdicts"][t]["verdict"] for t in FACTS["data-quality"]["verdicts"]} == FACTS["data-quality"]["verdicts"]
    ),
}


@pytest.mark.parametrize("key", sorted({e[0] for e in PLANTED["data-quality"]}))
def test_quality_summary_surfaces_each_planted_problem(quality: dict[str, Any], key: str) -> None:
    assert DQ[key](quality), key


def test_quality_summary_counts_the_period_and_leaves_the_holiday(quality: dict[str, Any]) -> None:
    facts = FACTS["data-quality"]
    assert (quality["period"]["from"], quality["period"]["to"]) == facts["period"]
    assert quality["period"]["results"] == facts["results"]
    assert sorted(c["check"] for c in quality["never_failed"]) == facts["never_failed"]
    cannot = next(c for c in quality["checks"] if c["check"] == facts["cannot_fail"]["check"])
    assert (cannot["results"], cannot["fail"]) == (facts["cannot_fail"]["results"], facts["cannot_fail"]["failures"])
    holiday = facts["holiday"]
    [one] = quality["single_failures"]
    assert (one["check"], one["failed_on"], one["failing_rows"]) == (
        holiday["check"],
        holiday["failed_on"],
        holiday["failing_rows"],
    )
    assert one["next"]["date"] == holiday["passed_on"] and "Hungarian national holiday" in one["note"]
    reasons = " ".join(" ".join(v["why"]) for v in quality["verdicts"].values())
    assert holiday["check"] not in reasons
    assert holiday["check"] not in {c["check"] for c in quality["cannot_fail"] + quality["warn_every_day"]}


# ---------------------------------------------------------------------------- quality_summary on small cases


def test_quality_summary_reads_other_field_names(tmp_path: Path) -> None:
    rows = [("2026-01-01", "PASSED"), ("2026-01-02", "WARNING"), ("2026-01-03", "FAILED"), ("2026-01-04", "PASSED")]
    with (tmp_path / "test_results.csv").open("w", newline="", encoding="utf-8") as handle:
        out = csv.writer(handle)
        out.writerow(["Day", "Test", "Model", "Result", "Failures"])
        out.writerows([day, "t_unique", "m.orders", state, n] for n, (day, state) in enumerate(rows))
    write(
        tmp_path / "defs" / "checks.yaml",
        'checks:\n  - name: t_unique\n    table: m.orders\n    query: "select 1 from m.orders where 1 = 0"\n',
    )
    result = run_json(QUALITY, str(tmp_path), "--results", str(tmp_path / "test_results.csv"))
    assert result["understood"]["results"]["fields"]["status"] == "Result"
    [check] = result["checks"]
    assert (check["pass"], check["warn"], check["fail"], check["failing_rows"]) == (2, 1, 1, [0, 3])
    assert check["cannot_fail"]["why"].startswith("a condition that is never true")
    assert result["single_failures"][0]["failed_on"] == "2026-01-03"
    assert result["verdicts"]["m.orders"]["verdict"] == "use with care"  # passed on the last day, but cannot fail


def test_quality_summary_conditions_and_step_changes() -> None:
    assert quality_summary.never_true("where load_date = :d and amount < amount")
    assert quality_summary.never_true("where a.amount <> a.amount")
    assert quality_summary.never_true("where amount < price") is None
    assert quality_summary.never_true("where x is null and x is not null")
    steady = {f"2026-01-{d:02d}": 5 for d in range(1, 11)}
    assert quality_summary.step_change(steady) is None
    jump = steady | {"2026-01-11": 90, "2026-01-12": 95}
    assert quality_summary.step_change(jump) == {
        "from": "2026-01-11",
        "days_before": 10,
        "rows_before": 50,
        "max_a_day_before": 5,
        "days_from": 2,
        "rows_from": 185,
        "min_a_day_from": 90,
    }


def test_quality_summary_never_prints_a_quarantined_personal_value(tmp_path: Path) -> None:
    write(tmp_path / "ops" / "checks.jsonl", '{"date": "2026-01-01", "check": "c", "table": "s.t", "status": "pass"}\n')
    lines = [
        json.dumps(
            {"date": "2026-01-01", "table": "s.t", "rule": "bad_email", "row_id": n, "value": f"p{n}@example.com"}
        )
        for n in range(3)
    ]
    write(tmp_path / "ops" / "quarantine.jsonl", "\n".join(lines) + "\n")
    write(tmp_path / "checks" / "q.yaml", "rules:\n  - name: bad_email\n    table: s.t\n    column: email\n")
    done = subprocess.run(
        [sys.executable, str(QUALITY), str(tmp_path)], capture_output=True, text=True, check=True, timeout=60
    )
    assert "@example.com" not in done.stdout
    assert json.loads(done.stdout)["quarantine"]["bad_email"]["rows"] == 3


# ---------------------------------------------------------------------------- no personal value anywhere


def test_no_personal_value_reaches_any_output(
    pipeline: Path,
    profile: dict[str, Any],
    contract: dict[str, Any],
    trace: dict[str, Any],
    quality: dict[str, Any],
) -> None:
    facts = FACTS["source-profile"]
    draft = run_in(pipeline, CONTRACT_CHECK, "draft", facts["delivery"], "--doc", facts["vendor_document"])
    raw = run_in(pipeline, SOURCE_FORMAT, facts["delivery"])
    text = json.dumps([profile, contract, trace, quality, draft, raw], ensure_ascii=False)
    with (pipeline / facts["delivery"] / "contacts.csv").open(encoding="utf-8", newline="") as handle:
        contacts = list(csv.DictReader(handle))
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    for row in contacts:
        assert row["phone"] not in text
        assert not row["iban"] or row["iban"] not in text
        assert f"{row['first_name']} {row['last_name']}" not in text
    names = {row["last_name"] for row in contacts}
    assert not [n for n in names if re.search(rf'"{re.escape(n)}"', text)]
