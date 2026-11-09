"""The data-architect scripts, on the acme-data fixture and on small cases of their own."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import ROOT, load, make_repo, run_json
from test_fixture_acme_data import DATA, EDGES, NOT_TABLES, PLANTED

SHARED = ROOT / "shared"
SKILLS = ROOT / "plugins" / "data-architect" / "skills"
PROFILE = SHARED / "data_profile.py"
INVENTORY = SHARED / "sql_inventory.py"
RULES = SKILLS / "data-platform" / "scripts" / "platform_rules.py"
CHECK = SKILLS / "data-model" / "scripts" / "model_check.py"
profile_module = load(PROFILE)
inventory_module = load(INVENTORY)


@pytest.fixture(scope="module")
def profiled(data_repo: Path) -> dict[str, Any]:
    result: dict[str, Any] = run_json(PROFILE, str(data_repo / "data"))
    return result


@pytest.fixture(scope="module")
def inventory(data_repo: Path) -> dict[str, Any]:
    result: dict[str, Any] = run_json(INVENTORY, str(data_repo), "--checks")
    return result


def table(result: dict[str, Any], name: str) -> dict[str, Any]:
    found: dict[str, Any] = next(f for f in result["files"] if f["table"] == name)
    return found


def column(result: dict[str, Any], name: str, col: str) -> dict[str, Any]:
    found: dict[str, Any] = next(c for c in table(result, name)["columns"] if c["name"] == col)
    return found


def short(name: str) -> str:
    return name if name.startswith("erp.") else name.rsplit(".", 1)[-1]


# ---------------------------------------------------------------------------- data_profile


def test_profile_counts_the_rows_and_finds_the_duplicated_key(profiled: dict[str, Any]) -> None:
    customers = table(profiled, "customers")
    assert customers["rows"] == DATA["customers_rows"]
    assert column(profiled, "customers", "customer_id")["distinct"] == DATA["customers_distinct_ids"]
    assert {k["column"] for k in customers["almost_keys"]} == {"customer_id", "national_id"}
    assert customers["almost_keys"][0] == {
        "column": "customer_id",
        "rows": DATA["customers_rows"],
        "distinct": DATA["customers_distinct_ids"],
        "duplicate_rows": DATA["customers_rows"] - DATA["customers_distinct_ids"],
    }
    assert ["order_id", "line_no"] in table(profiled, "order_lines")["candidate_keys"]
    assert table(profiled, "products")["candidate_keys"][0] == ["product_id"]


def test_profile_reports_mixed_formats(profiled: dict[str, Any]) -> None:
    price = column(profiled, "order_lines", "unit_price")
    assert price["type"] == "decimal"
    assert any(f"decimal comma in {DATA['decimal_comma_prices']} values" in i for i in price["issues"])
    date_column = column(profiled, "orders", "order_date")
    assert any(f"date_dmy {DATA['dmy_order_dates']}" in i for i in date_column["issues"])
    assert date_column["min"] < date_column["max"]


def test_profile_measures_orphans_and_multiplying_joins(profiled: dict[str, Any]) -> None:
    pair = {(o["from"], o["to"], o["column"]): o for o in profiled["overlaps"]}
    products = pair["order_lines", "products", "product_id"]
    assert products["orphan_rows"] == DATA["orphan_lines"] and products["to_is_unique"] is True
    promotions = pair["order_lines", "promotions", "product_id"]
    assert promotions["to_is_unique"] is False and promotions["multiplies_by"] > 1
    assert promotions["rows_after_left_join"] > promotions["from_rows"]


def test_profile_finds_personal_columns_and_prints_none_of_their_values(data_repo: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(PROFILE), str(data_repo / "data")], capture_output=True, text=True, check=True, timeout=120
    )
    result = json.loads(done.stdout)
    kinds = {c["name"]: c["personal"]["kind"] for c in table(result, "customers")["columns"] if "personal" in c}
    assert kinds == {
        "first_name": "person name",
        "last_name": "person name",
        "email": "e-mail",
        "phone": "phone",
        "national_id": "national id",
        "birth_date": "birth date",
    }
    assert column(result, "customers", "national_id")["personal"]["found_by"] == "name and value"
    with (data_repo / "data" / "customers.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows[:50]:
        for key in ("email", "phone", "national_id", "first_name", "last_name", "birth_date"):
            assert f'"{row[key]}"' not in done.stdout
    assert "@example.com" not in done.stdout
    assert "min" not in column(result, "customers", "birth_date")


def test_profile_checks_a_grain(data_repo: Path) -> None:
    held = run_json(PROFILE, str(data_repo / "data"), "--grain", "order_lines", "order_id,line_no")["grain"]
    assert held["holds"] is True and held["duplicate_keys"] == 0
    broken = run_json(PROFILE, str(data_repo / "data"), "--grain", "customers", "customer_id")["grain"]
    assert broken["holds"] is False
    assert broken["duplicate_keys"] == DATA["customers_rows"] - DATA["customers_distinct_ids"]


def test_jmbg_check() -> None:
    valid = [digit for digit in "0123456789" if profile_module.is_jmbg(f"010199066000{digit}")]
    assert len(valid) == 1
    assert profile_module.is_jmbg("3206990660006") is False  # no month 06 on day 32
    assert profile_module.is_jmbg("123") is False


def test_iban_check() -> None:
    assert profile_module.is_iban("GB82 WEST 1234 5698 7654 32") is True
    assert profile_module.is_iban("GB82 WEST 1234 5698 7654 33") is False


def test_profile_reads_semicolons_json_lines_and_windows_encoding(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_bytes("id;grad\n1;Niš\n2;Čačak\n".encode("cp1250"))
    (tmp_path / "b.jsonl").write_text('{"id": 1, "x": {"y": 2}}\n{"id": 2}\nnot json\n', encoding="utf-8")
    result = run_json(PROFILE, str(tmp_path))
    first = table(result, "a")
    assert first["delimiter"] == ";" and first["rows"] == 2 and first["notes"] == ["not UTF-8: read as Windows-1250"]
    second = table(result, "b")
    assert [c["name"] for c in second["columns"]] == ["id", "x"] and second["rows"] == 3
    assert "1 row(s)" in second["notes"][0]
    assert column(result, "b", "x")["nulls"] == 1


def test_profile_refuses_what_it_cannot_read(tmp_path: Path) -> None:
    done = subprocess.run([sys.executable, str(PROFILE), str(tmp_path / "no.csv")], capture_output=True, text=True)
    assert done.returncode == 2 and "not a data file" in done.stderr


# ---------------------------------------------------------------------------- sql_inventory


def test_inventory_finds_the_lineage(inventory: dict[str, Any]) -> None:
    found = {(short(e["from"]), short(e["to"])) for e in inventory["edges"]}
    missing = [edge for edge in EDGES if edge not in found]
    assert not missing


def test_inventory_is_not_fooled_by_comments_strings_and_functions(inventory: dict[str, Any]) -> None:
    names = {short(o["name"]) for o in inventory["objects"]}
    for fake in NOT_TABLES:
        assert fake not in names
    assert "order_date" not in names


def test_inventory_lists_dynamic_sql_and_tables_nobody_reads(inventory: dict[str, Any]) -> None:
    assert {(d["file"], d["kind"]) for d in inventory["dynamic"]} == {
        ("warehouse/procs/export_by_region.sql", "EXEC"),
        ("notebooks/stock_snapshot.ipynb", "f-string in spark.sql"),
    }
    assert "mart_old_campaigns" in inventory["unread"]
    assert inventory["cycles"] == []


def test_inventory_reads_ddl_and_dbt_tests(inventory: dict[str, Any]) -> None:
    fact = next(t for t in inventory["ddl"] if t["name"].endswith("fct_daily_sales"))
    types = {c["name"]: c["type"] for c in fact["columns"]}
    assert types["net_amount"] == "FLOAT" and fact["primary_key"]
    assert "unique" in inventory["dbt"]["tests"]["dim_customer"]["columns"]["customer_id"]
    assert inventory["dbt"]["sources"]["erp"][:2] == ["orders", "order_lines"]


FAMILY = {
    1: "fanout_candidate",
    2: "rerun_unsafe",
    3: "layer_skip",
    4: "personal_served",
    5: "float_money",
    6: "overwrite_history",
    7: "no_key_tests",
    8: "dynamic_sql",
}


@pytest.mark.parametrize(("number", "name", "file", "pattern"), PLANTED, ids=[p[1] for p in PLANTED])
def test_checks_point_at_every_planted_problem(
    inventory: dict[str, Any], number: int, name: str, file: str, pattern: str
) -> None:
    hits = [h for h in inventory["checks"] if h["family"] == FAMILY[number]]
    target = "models/marts/fct_sales.sql" if number == 7 else file
    assert any(h["file"] == target for h in hits), (name, hits)


def test_checks_leave_the_usual_dbt_shape_alone(inventory: dict[str, Any]) -> None:
    assert not [h for h in inventory["checks"] if h["family"] == "select_star"]
    assert [h["file"] for h in inventory["checks"] if h["family"] == "layer_skip"] == ["reports/store_performance.sql"]


def edges_of(repo: Path, **files: str) -> dict[str, Any]:
    make_repo(repo, {name.replace("__", "/") + ".sql": text for name, text in files.items()})
    result: dict[str, Any] = run_json(INVENTORY, str(repo), "--checks")
    return result


def pairs(result: dict[str, Any]) -> set[tuple[str, str]]:
    return {(e["from"], e["to"]) for e in result["edges"]}


def test_statements_map_reads_to_their_own_writes(tmp_path: Path) -> None:
    result = edges_of(
        tmp_path / "r",
        load="""INSERT INTO dw.a SELECT * FROM src.one;
                INSERT INTO dw.b SELECT x FROM src.two t JOIN src.three u ON t.k = u.k;""",
    )
    assert pairs(result) == {("src.one", "dw.a"), ("src.two", "dw.b"), ("src.three", "dw.b")}


def test_ctes_and_temp_tables_are_not_tables(tmp_path: Path) -> None:
    result = edges_of(
        tmp_path / "r",
        job="""WITH a AS (SELECT id FROM src.t), b (x) AS (SELECT id FROM a)
               INSERT INTO dw.out SELECT x FROM b;
               SELECT 1 INTO #temp FROM src.u;
               DELETE FROM #temp;""",
    )
    assert pairs(result) == {("src.t", "dw.out")}
    assert not any(o["name"].startswith("#") for o in result["objects"])


def test_t_sql_aliases_hints_and_comma_lists(tmp_path: Path) -> None:
    result = edges_of(
        tmp_path / "r",
        job="""UPDATE t SET t.x = s.x FROM [dw].[target] t JOIN [src].[s] s WITH (NOLOCK) ON t.k = s.k;
               INSERT [dw].[other] SELECT a.x FROM src.a a, src.b AS b WHERE a.k = b.k;
               MERGE INTO dw.m USING src.c c ON 1 = 1 WHEN MATCHED THEN UPDATE SET x = 1;""",
    )
    assert pairs(result) >= {
        ("src.s", "dw.target"),
        ("src.a", "dw.other"),
        ("src.b", "dw.other"),
        ("src.c", "dw.m"),
    }


def test_functions_that_use_from_are_not_reads(tmp_path: Path) -> None:
    result = edges_of(
        tmp_path / "r",
        q="SELECT EXTRACT(YEAR FROM d), SUBSTRING(s FROM 1 FOR 2), 'FROM fake' FROM src.real -- FROM commented\n",
    )
    assert {o["name"] for o in result["objects"]} == {"src.real", "q"}


def test_a_cycle_is_reported(tmp_path: Path) -> None:
    result = edges_of(tmp_path / "r", a="INSERT INTO x.a SELECT 1 FROM x.b;", b="INSERT INTO x.b SELECT 1 FROM x.a;")
    assert result["cycles"] == [["x.a", "x.b"]]


def test_a_safe_load_is_not_flagged(tmp_path: Path) -> None:
    result = edges_of(
        tmp_path / "r",
        safe="DELETE FROM dw.t WHERE d = @d; INSERT INTO dw.t SELECT * FROM x.y WHERE d = @d;",
        guarded="INSERT INTO dw.u SELECT a FROM x.y WHERE NOT EXISTS (SELECT 1 FROM dw.u);",
        unsafe="INSERT INTO dw.v SELECT a FROM x.y;",
    )
    assert [h["file"] for h in result["checks"] if h["family"] == "rerun_unsafe"] == ["unsafe.sql"]


def test_a_masked_column_is_not_flagged(tmp_path: Path) -> None:
    result = edges_of(
        tmp_path / "r",
        reports__a="SELECT SHA2(email) AS email_hash, phone FROM marts.c;",
    )
    assert [h["detail"].split()[0] for h in result["checks"] if h["family"] == "personal_served"] == ["phone"]


def test_a_python_job_is_read(tmp_path: Path) -> None:
    make_repo(
        tmp_path / "r",
        {
            "job.py": (
                'df = spark.table("src.a")\n'
                "df.write.saveAsTable('dw.b')\n"
                'spark.sql("INSERT INTO dw.c SELECT 1 FROM src.d")\n'
                'spark.sql(f"SELECT * FROM {name}")\n'
            )
        },
    )
    result = run_json(INVENTORY, str(tmp_path / "r"))
    assert pairs(result) >= {("src.a", "dw.b"), ("src.d", "dw.c")}
    assert [d["line"] for d in result["dynamic"]] == [4]


def test_dbt_yaml_is_read_by_indentation() -> None:
    text = """
version: 2
sources:
  - name: erp
    tables:
      - name: orders
      - name: customers
models:
  - name: fct
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [a, b]
    columns:
      - name: a
        tests:
          - not_null
      - name: b
  - name: dim
    columns:
      - name: k
        data_tests:
          - unique
"""
    sources, models = inventory_module.parse_dbt_yaml(text)
    assert sources == {"erp": ["orders", "customers"]}
    assert models["fct"]["tests"] == ["dbt_utils.unique_combination_of_columns"]
    assert models["fct"]["columns"] == {"a": ["not_null"], "b": []}
    assert models["dim"]["columns"] == {"k": ["unique"]}


# ---------------------------------------------------------------------------- platform_rules

REPORTS = {
    "data_gb": 3,
    "growth_gb_per_month": 0.04,
    "joins_across_sources": True,
    "files_or_images": False,
    "ml_on_raw": False,
    "freshness_minutes": 1440,
    "data_engineers": 0,
    "domain_teams": 0,
}
PLATFORM = {
    "data_gb": 35000,
    "growth_gb_per_month": 1000,
    "joins_across_sources": True,
    "files_or_images": True,
    "ml_on_raw": True,
    "freshness_minutes": 2,
    "data_engineers": 6,
    "domain_teams": 1,
}


def rules(facts: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = run_json(RULES, "-", stdin=json.dumps(facts))
    return result


def test_the_small_brief_stops_at_one_database() -> None:
    result = rules(REPORTS)
    assert result["lowest_open"] == "single_db" and result["open"] == ["single_db", "warehouse"]
    assert result["sizing"]["after_2_years_gb"] == 4.0


def test_the_big_brief_needs_a_streaming_lakehouse_and_no_mesh() -> None:
    result = rules(PLATFORM)
    assert result["open"] == ["lakehouse_streaming"]
    by_id = {o["id"]: o for o in result["options"]}
    assert [r["rule"] for r in by_id["mesh"]["eliminated_by"]] == ["too-few-domains"]
    assert result["sizing"]["after_2_years_gb"] == 59000.0


def test_unknown_facts_decide_nothing_and_are_listed() -> None:
    result = rules({})
    assert result["open"] == [key for key, _ in load(RULES).OPTIONS]
    assert {f["fact"] for f in result["open_facts"]} >= {"data_gb", "freshness_minutes", "domain_teams"}
    assert result["thresholds"]["single_db_limit_gb"] == 2000


@pytest.mark.parametrize(
    ("facts", "eliminated"),
    [
        ({"source_keeps_history": False}, "source_reports"),
        ({"source_can_take_load": False}, "source_reports"),
        ({"data_gb": 2500}, "single_db"),
        ({"data_gb": 1000, "growth_gb_per_month": 40}, None),
        ({"data_gb": 1000, "growth_gb_per_month": 50}, "single_db"),
        ({"freshness_minutes": 5}, "lakehouse_streaming"),
    ],
)
def test_single_rules(facts: dict[str, Any], eliminated: str | None) -> None:
    result = rules(facts)
    closed = [o["id"] for o in result["options"] if o["status"] == "eliminated"]
    assert closed == ([eliminated] if eliminated else [])


def test_bad_facts_are_refused() -> None:
    done = subprocess.run(
        [sys.executable, str(RULES), "-"], input='{"data_gb": "big", "colour": 1}', capture_output=True, text=True
    )
    assert done.returncode == 1
    assert "data_gb: must be a number" in done.stderr and "colour: unknown fact" in done.stderr


# ---------------------------------------------------------------------------- model_check


def model(**change: Any) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": "model",
        "tables": [
            {
                "id": "f",
                "kind": "fact",
                "grain": "one row per line",
                "columns": [{"name": "id", "key": "pk"}, {"name": "c", "key": "fk"}],
            },
            {
                "id": "d",
                "kind": "dimension",
                "history": "overwrite",
                "columns": [{"name": "c", "key": "pk"}, {"name": "mail", "personal": True, "mask": "hashed"}],
            },
        ],
        "relations": [{"from": "f", "to": "d", "on": "c"}],
    }
    block.update(change)
    return block


def checked(tmp_path: Path, data: dict[str, Any]) -> dict[str, Any]:
    path = tmp_path / "model.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result: dict[str, Any] = run_json(CHECK, str(path))
    return result


def test_a_complete_model_passes(tmp_path: Path) -> None:
    result = checked(tmp_path, model())
    assert result["ok"] is True and result["errors"] == [] and result["warnings"] == []
    assert result["counts"]["facts"] == 1 and result["counts"]["personal_columns"] == 1


def test_a_page_holding_a_model_is_read(tmp_path: Path) -> None:
    page = {
        "skill": "x",
        "title": "t",
        "sections": [{"title": "s", "blocks": [{"type": "text", "text": "a"}, model()]}],
    }
    assert checked(tmp_path, page)["counts"]["tables"] == 2


def test_the_missing_decisions_are_named(tmp_path: Path) -> None:
    block = model()
    del block["tables"][0]["grain"]
    del block["tables"][1]["history"]
    del block["tables"][1]["columns"][1]["mask"]
    block["relations"] = [{"from": "f", "to": "d", "on": "c=nope", "cardinality": "n:n"}]
    errors = checked(tmp_path, block)["errors"]
    assert errors == [
        "relation f -> d: n:n needs a bridge table",
        "relation f -> d: d has no column nope",
        "f: a fact needs its grain",
        "d: no history decision (set it on the table or on every attribute)",
        "d.mail: personal column without a masking decision",
    ]


def test_warnings_ask_for_a_look(tmp_path: Path) -> None:
    block = model(relations=[])
    block["tables"][0]["columns"][0].pop("key")
    warnings = checked(tmp_path, block)["warnings"]
    assert "f: a fact that joins to nothing" in warnings
    assert "f: no primary key: how is the grain enforced?" in warnings
    assert "f.c: a foreign key no relation uses" in warnings


def test_no_model_block_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    path.write_text('{"sections": []}', encoding="utf-8")
    done = subprocess.run([sys.executable, str(CHECK), str(path)], capture_output=True, text=True)
    assert done.returncode == 2 and "no model block" in done.stderr
