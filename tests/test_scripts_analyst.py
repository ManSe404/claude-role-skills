"""The data-analyst scripts: on the acme-sales fixture and on small cases of their own."""

from __future__ import annotations

import json
import random
import subprocess
import sys
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from conftest import ROOT, load, run_json
from test_fixture_acme_sales import LATE, METRIC, MIX_SPLIT, NET_REVENUE, PLANTED_AT, RECONCILE, REPORT

SHARED = ROOT / "shared"
SKILLS = ROOT / "plugins" / "data-analyst" / "skills"
MEASURE = SHARED / "measure.py"
DECOMPOSE = SKILLS / "number-moved" / "scripts" / "decompose.py"
RECONCILE_PY = SKILLS / "number-reconcile" / "scripts" / "reconcile.py"
COMPARE = SKILLS / "metric-spec" / "scripts" / "metric_compare.py"
CHECK = SKILLS / "report-review" / "scripts" / "report_check.py"
measure = load(MEASURE)
decompose = load(DECOMPOSE)
report_check = load(CHECK)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------- measure


def test_measure_counts_exactly_and_follows_sql_nulls(tmp_path: Path) -> None:
    data = write(
        tmp_path / "t.csv",
        "id,status,amount\n1,a,0.10\n2,a,0.20\n3,,0.30\n3,,0.30\n",
    )
    spec = {
        "measures": [
            {"name": "all", "table": "t", "value": {"sum": "amount"}},
            {
                "name": "not a",
                "table": "t",
                "filters": [{"column": "status", "op": "!=", "value": "a"}],
                "value": {"count": "*"},
            },
            {"name": "one per id", "table": "t", "dedupe": ["id"], "value": {"sum": "amount"}},
        ]
    }
    specfile = write(tmp_path / "spec.json", json.dumps(spec))
    result = run_json(MEASURE, str(data), str(specfile))["measures"]
    assert result[0]["exact"] == "9/10" and result[0]["value"] == "0.90"
    # NULL fails `!=`, so the filter drops the two NULL rows and keeps nothing.
    assert result[1]["value"] == "0.00"
    assert result[1]["filters"][0] == {"filter": "status != a", "rows_dropped": 4, "null_rows_dropped": 2}
    assert result[2]["rows_kept"] == 3 and result[2]["duplicates_removed"] == 1 and result[2]["exact"] == "3/5"


def test_measure_never_groups_on_or_echoes_a_personal_column(tmp_path: Path) -> None:
    data = write(tmp_path / "t.csv", "id,email,amount\n1,ana@example.com,5\n2,vera@example.com,6\n")
    table = measure.load(data)
    assert table.personal == {"email": "e-mail"}
    for spec, message in (
        ({"table": "t", "by": ["email"], "value": {"sum": "amount"}}, "personal"),
        (
            {"table": "t", "filters": [{"column": "email", "op": "=", "value": "x"}], "value": {"count": "*"}},
            "personal",
        ),
    ):
        with pytest.raises(SystemExit, match=message):
            measure.evaluate(spec, {"t": table})
    # Counting is allowed, and only counts come back.
    allowed = measure.evaluate(
        {"table": "t", "filters": [{"column": "email", "op": "not_null"}], "value": {"count_distinct": "email"}},
        {"t": table},
    )
    assert allowed["exact"] == "2"
    assert "example.com" not in json.dumps(allowed)


def test_measure_refuses_a_group_with_too_many_values(tmp_path: Path) -> None:
    rows = "\n".join(f"{i},1" for i in range(300))
    table = measure.load(write(tmp_path / "t.csv", f"id,amount\n{rows}\n"))
    with pytest.raises(SystemExit, match="coarser"):
        measure.evaluate({"table": "t", "by": ["id"], "value": {"sum": "amount"}}, {"t": table})


# ---------------------------------------------------------------------------- decompose


def decompose_fixture(repo: Path, *extra: str) -> dict[str, Any]:
    return run_json(  # type: ignore[no-any-return]
        DECOMPOSE,
        str(repo / "data" / "orders.csv"),
        "--date",
        "order_date",
        "--a",
        "2026-09-01:2026-09-30",
        "--b",
        "2026-10-01:2026-10-31",
        "--value",
        "net_amount",
        "--volume",
        "units",
        "--filter",
        "status=completed",
        "--dedupe",
        "order_id",
        *extra,
    )


def test_decompose_finds_the_planted_mix_split_exactly(sales_repo: Path) -> None:
    result = decompose_fixture(sales_repo, "--by", "product_line")["decompositions"][0]
    effects = {k: Decimal(v) for k, v in result["effects"].items()}
    assert effects["volume"] == MIX_SPLIT["volume"]
    assert effects["mix"] == MIX_SPLIT["mix"]
    assert effects["rate"] == MIX_SPLIT["rate"]
    assert effects["new"] == effects["gone"] == 0
    assert Decimal(result["change"]) == NET_REVENUE["change_final"]
    assert result["adds_up"] is True and result["exact_sum_minus_change"] == "0"
    # Proof at the exact level, and the displayed cents add up to the displayed change.
    assert sum(Fraction(v) for v in result["effects_exact"].values()) == Fraction(result["change"])
    assert sum(Decimal(v) for v in result["effects"].values()) == Decimal(result["change"])
    by_segment = {s["segment"]: s for s in result["segments"]}
    assert Decimal(by_segment["premium"]["mix"]) == MIX_SPLIT["mix_premium"]
    assert Decimal(by_segment["standard"]["rate"]) == MIX_SPLIT["rate_standard"]
    assert Decimal(by_segment["value"]["mix"]) == MIX_SPLIT["mix_value"]
    first = result["drivers"][0]
    assert (first["effect"], first["segment"]) == ("mix", "premium")
    assert Decimal(result["explained_by_top"]) + Decimal(result["left_unexplained"]) == Decimal(result["change"])


def test_decompose_rules_out_the_late_day_first(sales_repo: Path) -> None:
    checks = decompose_fixture(
        sales_repo, "--by", "product_line", "--loaded-at", "loaded_at", "--as-of", LATE["as_of"]
    )["checks"]
    late = checks["late"]
    assert late["late_rows_b"] == LATE["rows"] and late["late_rows_a"] == 0
    assert Decimal(late["late_value_b"]) == LATE["amount"]
    assert Decimal(late["number_as_of_b"]) == NET_REVENUE["october_reported"]
    assert Decimal(late["change_as_of"]) == NET_REVENUE["change_reported"]
    assert Decimal(late["change_faked_by_late_rows"]) == -LATE["amount"]
    assert late["by_day"][0]["day"] == LATE["day"]
    assert {k: Decimal(v) for k, v in late["by_segment"].items()} == LATE["by_line"]
    assert checks["days_b"]["missing_days"] == []
    assert checks["periods"]["equal_length"] is False


def test_decompose_reports_missing_and_thin_days(tmp_path: Path) -> None:
    rows = ["day,seg,amount"]
    for day in range(1, 11):
        if day == 4:
            continue  # no row at all
        rows += [f"2026-01-{day:02d},a,10"] * (2 if day == 7 else 10)
    data = write(tmp_path / "t.csv", "\n".join(rows) + "\n")
    result = run_json(
        DECOMPOSE, str(data), "--date", "day", "--a", "2026-01-01:2026-01-05", "--b", "2026-01-06:2026-01-10",
        "--value", "amount", "--by", "seg",
    )  # fmt: skip
    assert result["checks"]["days_a"]["missing_days"] == ["2026-01-04"]
    assert result["checks"]["days_b"]["thin_days"][0]["day"] == "2026-01-07"
    assert result["decompositions"][0]["adds_up"] is True


def random_rows(rng: random.Random) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    for period in ("a", "b"):
        for seg in ("x", "y", "z", "w"):
            if rng.random() < 0.15:  # a segment that exists in only one period
                continue
            for _ in range(int(rng.random() * 12) + 1):
                units = str(1 + int(rng.random() * 5))
                value = f"{rng.random() * 90 + 1:.2f}"
                rows.append({"period": period, "seg": seg, "units": units, "value": value})
    return rows


@pytest.mark.parametrize("seed", range(40))
def test_the_sum_of_the_effects_is_the_change_exactly(seed: int) -> None:
    """A property test: on random segments, including ones new or gone, volume+mix+rate+new+gone is the change."""
    rng = random.Random(seed)
    rows = random_rows(rng)
    a_rows = [r for r in rows if r["period"] == "a"]
    b_rows = [r for r in rows if r["period"] == "b"]
    assert a_rows and b_rows
    args = decompose.argparse.Namespace(value="value", volume="units", ratio=False, places=2, top=3)
    result = decompose.decompose(a_rows, b_rows, ["seg"], args)
    assert result["adds_up"] is True
    change = sum((Fraction(r["value"]) for r in b_rows), Fraction(0)) - sum(
        (Fraction(r["value"]) for r in a_rows), Fraction(0)
    )
    assert sum(Fraction(v) for v in result["effects_exact"].values()) == change
    # Ratio mode decomposes value/volume into mix and rate, also exactly.
    ratio_args = decompose.argparse.Namespace(value="value", volume="units", ratio=True, places=2, top=3)
    ratio = decompose.decompose(a_rows, b_rows, ["seg"], ratio_args)
    assert ratio["adds_up"] is True
    assert "volume" not in ratio["effects"]


def test_a_new_or_gone_segment_is_named_and_the_rest_still_adds_up() -> None:
    rows = [
        {"p": "a", "seg": "old", "v": "10", "u": "1"},
        {"p": "a", "seg": "both", "v": "20", "u": "2"},
        {"p": "b", "seg": "both", "v": "30", "u": "2"},
        {"p": "b", "seg": "fresh", "v": "5", "u": "1"},
    ]
    args = decompose.argparse.Namespace(value="v", volume="u", ratio=False, places=2, top=5)
    result = decompose.decompose([r for r in rows if r["p"] == "a"], [r for r in rows if r["p"] == "b"], ["seg"], args)
    assert result["effects"]["new"] == "5.00"
    assert result["effects"]["gone"] == "-10.00"
    assert result["adds_up"] is True
    names = {(d["effect"], d["segment"]) for d in result["drivers"]}
    assert ("new", "fresh") in names and ("gone", "old") in names


def test_a_personal_column_cannot_be_a_segment(tmp_path: Path, sales_repo: Path) -> None:
    done = subprocess.run(
        [
            sys.executable,
            str(DECOMPOSE),
            str(sales_repo / "data" / "orders.csv"),
            "--date",
            "order_date",
            "--a",
            "2026-09-01:2026-09-30",
            "--b",
            "2026-10-01:2026-10-31",
            "--value",
            "net_amount",
            "--by",
            "customer_email",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode != 0 and "personal" in done.stderr
    assert "example.com" not in done.stdout + done.stderr


def test_no_script_output_shows_a_personal_value(sales_repo: Path) -> None:
    customers = (sales_repo / "data" / "customers.csv").read_text(encoding="utf-8").splitlines()[1:]
    personal = {line.split(",")[2] for line in customers} | {line.split(",")[1] for line in customers}
    outputs = [
        json.dumps(decompose_fixture(sales_repo, "--by", "channel")),
        json.dumps(reconcile_fixture(sales_repo)),
    ]
    for output in outputs:
        assert not any(value in output for value in personal)


# ---------------------------------------------------------------------------- reconcile


def reconcile_fixture(repo: Path, *extra: str) -> dict[str, Any]:
    return run_json(  # type: ignore[no-any-return]
        RECONCILE_PY,
        str(repo / "data" / "orders.csv"),
        str(repo / "data" / "ledger.csv"),
        "--key",
        "order_id",
        "--value-a",
        "net_amount",
        "--value-b",
        "amount",
        "--date-a",
        "order_ts",
        "--date-b",
        "posted_at",
        "--window",
        "2026-10-01:2026-10-31",
        "--filter-a",
        "status=completed",
        "--slice",
        "channel,region,product_line",
        "--filter-columns",
        "channel",
        *extra,
    )


def test_reconcile_accounts_for_the_whole_gap(sales_repo: Path) -> None:
    result = reconcile_fixture(sales_repo)
    assert Decimal(result["gap"]) == RECONCILE["gap"]
    assert Decimal(result["a"]["total"]) == RECONCILE["erp_total"]
    assert Decimal(result["b"]["total"]) == RECONCILE["ledger_total"]
    assert result["adds_up"] is True and result["exact_sum_of_buckets_minus_gap"] == "0"
    buckets = {b["bucket"]: b for b in result["buckets"]}
    amount = lambda name: Decimal(buckets[name]["amount"])  # noqa: E731
    assert (buckets["only_in_a"]["rows"], amount("only_in_a")) == RECONCILE["not_invoiced"]
    assert (buckets["filtered_a:channel=staff"]["rows"], amount("filtered_a:channel=staff")) == RECONCILE[
        "staff_filter"
    ]
    assert (buckets["time_zone_a"]["rows"], amount("time_zone_a")) == RECONCILE["time_zone_october_only_in_erp"]
    assert (buckets["time_zone_b"]["rows"], amount("time_zone_b")) == RECONCILE["time_zone_october_only_in_ledger"]
    assert (buckets["timing_a"]["rows"], amount("timing_a")) == RECONCILE["timing"]
    assert (buckets["duplicates_b"]["rows"], amount("duplicates_b")) == RECONCILE["duplicates_in_ledger"]
    assert (buckets["only_in_b"]["rows"], amount("only_in_b")) == RECONCILE["only_in_ledger"]
    assert (buckets["value_difference"]["rows"], amount("value_difference")) == RECONCILE["unexplained"]
    assert amount("rounding") == RECONCILE["rounding"]
    # The whole gap is the sum of the buckets, exactly.
    assert sum(Fraction(b["exact"]) for b in result["buckets"]) == Fraction(result["gap_exact"])
    assert Decimal(result["unexplained"]["amount"]) == RECONCILE["unexplained"][1]
    assert result["rounding"]["detected"] is True and result["rounding"]["unit"] == "1"


def test_reconcile_slices_show_where_the_gap_sits(sales_repo: Path) -> None:
    result = reconcile_fixture(sales_repo)
    channel = next(s for s in result["slices"] if s["column"] == "channel")
    by_value = {v["value"]: Decimal(v["gap"]) for v in channel["values"]}
    assert by_value["staff"] == RECONCILE["staff_filter"][1]
    # The slices of one column add up to the same gap.
    for slice_ in result["slices"]:
        assert sum(Decimal(v["gap"]) for v in slice_["values"]) == Decimal(result["gap"])


def test_reconcile_never_prints_a_key(sales_repo: Path) -> None:
    text = json.dumps(reconcile_fixture(sales_repo))
    assert "SO-1" not in text and "MAN-0001" not in text


def test_a_personal_column_cannot_be_a_slice(sales_repo: Path) -> None:
    done = subprocess.run(
        [
            sys.executable,
            str(RECONCILE_PY),
            str(sales_repo / "data" / "orders.csv"),
            str(sales_repo / "data" / "ledger.csv"),
            "--key",
            "order_id",
            "--value-a",
            "net_amount",
            "--value-b",
            "amount",
            "--date-a",
            "order_ts",
            "--date-b",
            "posted_at",
            "--window",
            "2026-10-01:2026-10-31",
            "--slice",
            "customer_email",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode != 0 and "personal" in done.stderr


def test_reconcile_on_small_cases(tmp_path: Path) -> None:
    a = write(tmp_path / "a.csv", "id,day,amount\n1,2026-01-01,10.00\n2,2026-01-02,20.25\n3,2026-01-03,30\n")
    b = write(tmp_path / "b.csv", "id,day,amount\n1,2026-01-01,10.00\n2,2026-01-02,20\n4,2026-01-02,7\n")
    result = run_json(
        RECONCILE_PY, str(a), str(b), "--key", "id", "--value-a", "amount", "--value-b", "amount",
        "--date-a", "day", "--date-b", "day", "--window", "2026-01-01:2026-01-31",
    )  # fmt: skip
    buckets = {x["bucket"]: x for x in result["buckets"]}
    assert result["adds_up"] is True
    assert Decimal(buckets["only_in_a"]["amount"]) == 30
    assert Decimal(buckets["only_in_b"]["amount"]) == -7
    assert Decimal(buckets["rounding"]["amount"]) == Decimal("0.25")


# ---------------------------------------------------------------------------- metric_compare


DEFINITIONS = {
    "definitions": [
        {
            "name": "finance",
            "source": METRIC["finance_file"],
            "measure": {
                "table": "orders",
                "window": {"column": "order_date", "from": "2026-10-01", "to": "2026-10-31"},
                "filters": [{"column": "status", "op": "=", "value": "completed"}],
                "value": {"sum": "net_amount"},
            },
        },
        {
            "name": "bi",
            "source": METRIC["bi_file"],
            "measure": {
                "table": "orders",
                "window": {"column": "shipped_date", "from": "2026-10-01", "to": "2026-10-31"},
                "filters": [
                    {"column": "status", "op": "in", "value": ["completed", "returned"]},
                    {"column": "channel", "op": "!=", "value": "staff"},
                ],
                "value": {"sum": ["net_amount", "shipping_fee"]},
            },
        },
    ]
}


def test_metric_find_lists_the_two_definitions_with_their_filters(sales_repo: Path) -> None:
    found = run_json(COMPARE, "find", str(sales_repo), "--name", "net_revenue")
    files = {d["file"]: d for d in found["definitions"]}
    finance = files[METRIC["finance_file"]]
    bi = files[METRIC["bi_file"]]
    assert finance["expression"] == "sum(net_amount) as net_revenue"
    assert finance["where"] == "where status = 'completed'"
    assert finance["from"] == ["from stg_orders"]
    assert bi["expression"] == "sum(net_amount + shipping_fee) as net_revenue"
    assert "channel <> 'staff'" in bi["where"]
    assert any(m["file"] == "models/marts/schema.yml" for m in found["mentions"])
    # A union's second branch reads its own WHERE, not the first branch's.
    branches = [d for d in found["definitions"] if d["file"].endswith("sep_vs_oct.sql")]
    assert "09-24" in branches[0]["where"] and "10-31" in branches[1]["where"]


def test_metric_compare_measures_each_step_and_the_steps_add_up(sales_repo: Path, tmp_path: Path) -> None:
    spec = write(tmp_path / "defs.json", json.dumps(DEFINITIONS))
    result = run_json(COMPARE, "compare", str(spec), str(sales_repo / "data"))
    values = {d["name"]: Decimal(d["value"]) for d in result["definitions"]}
    assert values == {"finance": METRIC["finance"], "bi": METRIC["bi"]}
    walk = result["walks"][0]
    assert Decimal(walk["difference"]) == METRIC["gap"]
    assert walk["adds_up"] is True and walk["steps_sum_minus_difference"] == "0"
    assert sum(Fraction(s["effect_exact"]) for s in walk["steps"]) == Fraction(METRIC["gap"])
    changes = [s["change"] for s in walk["steps"]]
    assert changes[0].startswith("date window: order_date")
    assert any(c.startswith("change filter: status = completed") for c in changes)
    assert any(c.startswith("add filter: channel != staff") for c in changes)
    assert any(c.startswith("value:") for c in changes)


def test_metric_compare_says_when_it_cannot_walk(tmp_path: Path) -> None:
    data = write(tmp_path / "d" / "t.csv", "id,a,b\n1,2,4\n3,4,6\n")
    spec = {
        "definitions": [
            {"name": "x", "measure": {"table": "t", "value": {"sum": "a"}}},
            {
                "name": "y",
                "measure": {
                    "value": {
                        "ratio": {
                            "numerator": {"table": "t", "value": {"sum": "a"}},
                            "denominator": {"table": "t", "value": {"sum": "b"}},
                        }
                    }
                },
            },
        ]
    }
    specfile = write(tmp_path / "spec.json", json.dumps(spec))
    result = run_json(COMPARE, "compare", str(specfile), str(data.parent))
    assert "no step-by-step walk" in result["walks"][0]["note"] or "by value only" in result["walks"][0]["note"]


# ---------------------------------------------------------------------------- report_check


def test_report_check_finds_every_planted_place(sales_repo: Path) -> None:
    result = run_json(CHECK, "sql", str(sales_repo / "reports" / "october_review"), "--data", str(sales_repo / "data"))
    hits = {h["family"]: h for h in result["hits"]}
    expected_rel = {
        "fanout_candidate": PLANTED_AT[1],
        "null_dropping_filter": PLANTED_AT[2],
        "partial_period": PLANTED_AT[3],
        "avg_of_avg": PLANTED_AT[5],
        "truncated_axis": PLANTED_AT[8],
    }
    for family, place in expected_rel.items():
        assert f"reports/october_review/{hits[family]['file']}:{hits[family]['line']}" == place, family
    assert hits["null_dropping_filter"]["nulls"][0]["null_rows"] == REPORT["region_null_rows"]
    assert hits["fanout_candidate"]["counted"]["keys_with_several_rows"] == REPORT["double_counted_orders"]
    ratio_files = {h["file"] for h in result["hits"] if h["family"] == "ratio" and h["conditional_denominator"]}
    assert ratio_files == {"conversion.sql"}
    # The clean query has no hits of its own.
    assert not [h for h in result["hits"] if h["file"] == "orders_by_status.sql"]


def checks_fixture(repo: Path, tmp_path: Path, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    spec = write(tmp_path / "checks.json", json.dumps({"checks": checks}))
    return run_json(CHECK, "data", str(spec), str(repo / "data"))["checks"]  # type: ignore[no-any-return]


OCTOBER_COMPLETED = {
    "filters": [{"column": "status", "op": "=", "value": "completed"}],
    "window": {"column": "order_date", "from": "2026-10-01", "to": "2026-10-31"},
}


def test_report_data_checks_find_the_planted_numbers(sales_repo: Path, tmp_path: Path) -> None:
    results = checks_fixture(
        sales_repo,
        tmp_path,
        [
            {
                "check": "fanout",
                "table": "orders",
                "join": "order_promotions",
                "key": "order_id",
                "value": "net_amount",
                **OCTOBER_COMPLETED,
            },
            {
                "check": "avg_of_averages",
                "table": "orders",
                "group": "store_id",
                "value": "net_amount",
                "filters": [
                    {"column": "channel", "op": "=", "value": "store"},
                    {"column": "status", "op": "=", "value": "completed"},
                ],
                "window": OCTOBER_COMPLETED["window"],
            },
            {
                "check": "small_groups",
                "table": "orders",
                "group": "store_id",
                "filters": [
                    {"column": "channel", "op": "=", "value": "store"},
                    {"column": "status", "op": "=", "value": "completed"},
                ],
                "window": OCTOBER_COMPLETED["window"],
            },
            {
                "check": "simpson",
                "table": "sessions",
                "compare": "device",
                "numerator": "orders",
                "denominator": "sessions",
                "within": ["source"],
            },
            {
                "check": "windows",
                "table": "orders",
                "date": "order_date",
                "value": "net_amount",
                "filters": OCTOBER_COMPLETED["filters"],
                "periods": [
                    {"name": "September", "from": "2026-09-01", "to": "2026-09-24"},
                    {"name": "October", "from": "2026-10-01", "to": "2026-10-31"},
                ],
            },
        ],
    )
    fanout, avg, small, simpson, windows = results
    assert Decimal(fanout["correct_sum"]) == REPORT["revenue_correct"]
    assert Decimal(fanout["sum_after_join"]) == REPORT["revenue_claimed"]
    assert Decimal(fanout["double_counted"]) == REPORT["double_counted"]
    assert Decimal(avg["average_of_averages"]) == REPORT["average_of_averages"]
    assert Decimal(avg["true_average"]) == REPORT["true_store_average"]
    assert REPORT["small_sample_store"] in small["small_groups"]
    assert next(g for g in small["groups"] if g["group"] == "6")["rows"] == REPORT["small_sample_rows"]
    assert simpson["reversal"] is True and simpson["reversal_in"] == ["source"]
    assert simpson["overall_leader"] == "desktop"
    assert all(s["mobile"]["rate_pct"] > s["desktop"]["rate_pct"] for s in simpson["within"][0]["strata"])
    assert Decimal(windows["periods"][0]["sum"]) == REPORT["september_partial"]
    assert windows["equal_length"] is False
    assert Decimal(windows["like_for_like"][1]["sum"]) == REPORT["october_like_for_like"]


def test_simpson_without_a_reversal_says_so(tmp_path: Path) -> None:
    rows = ["group,stratum,num,den"]
    for group, stratum, num, den in (("a", "s1", 2, 4), ("b", "s1", 1, 4), ("a", "s2", 3, 4), ("b", "s2", 2, 4)):
        rows.append(f"{group},{stratum},{num},{den}")
    data = write(tmp_path / "d" / "t.csv", "\n".join(rows) + "\n")
    spec = write(
        tmp_path / "c.json",
        json.dumps(
            {
                "checks": [
                    {
                        "check": "simpson",
                        "table": "t",
                        "compare": "group",
                        "numerator": "num",
                        "denominator": "den",
                        "within": ["stratum"],
                    }
                ]
            }
        ),
    )
    result = run_json(CHECK, "data", str(spec), str(data.parent))["checks"][0]
    assert result["reversal"] is False
    assert result["overall_leader"] == "a"


def test_report_check_refuses_a_personal_group(tmp_path: Path) -> None:
    data = write(tmp_path / "d" / "t.csv", "email,v\nana@example.com,1\nvera@example.com,2\n")
    spec = write(
        tmp_path / "c.json", json.dumps({"checks": [{"check": "small_groups", "table": "t", "group": "email"}]})
    )
    done = subprocess.run(
        [sys.executable, str(CHECK), "data", str(spec), str(data.parent)], capture_output=True, text=True, timeout=60
    )
    assert done.returncode != 0 and "personal" in done.stderr


def test_no_script_imports_anything_outside_the_standard_library_and_its_siblings() -> None:
    for path in [MEASURE, DECOMPOSE, RECONCILE_PY, COMPARE, CHECK]:
        text = path.read_text(encoding="utf-8")
        assert "requests" not in text and "urllib" not in text and "http" not in text.split("Usage")[0]
        assert "import socket" not in text
