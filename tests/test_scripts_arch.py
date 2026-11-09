"""The software-architect scripts, on the acme-logistics fixture and on small cases of their own."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import ROOT, make_repo, run_json
from test_fixture_acme_logistics import (
    BILLING_AUTHOR,
    COCHANGE,
    COCHANGE_COMMITS,
    COMPOSE_SERVICES,
    HOT_FILE,
    HOT_FILE_COMMITS,
    MODULE_EDGES,
)

GRAPH = ROOT / "shared" / "code_graph.py"
CONTAINERS = ROOT / "shared" / "containers.py"
SKILLS = ROOT / "plugins" / "software-architect" / "skills"
RULES = SKILLS / "arch-style" / "scripts" / "style_rules.py"
CHECK = SKILLS / "arch-c4" / "scripts" / "c4_check.py"


@pytest.fixture(scope="module")
def graph(logistics_repo: Path) -> dict[str, Any]:
    result: dict[str, Any] = run_json(GRAPH, str(logistics_repo), "--git")
    return result


@pytest.fixture(scope="module")
def running(logistics_repo: Path) -> dict[str, Any]:
    result: dict[str, Any] = run_json(CONTAINERS, str(logistics_repo))
    return result


# ---------------------------------------------------------------------------- code_graph


def test_the_module_graph_is_found(graph: dict[str, Any]) -> None:
    found = {(e["from"], e["to"]) for e in graph["edges"]}
    assert [edge for edge in MODULE_EDGES if edge not in found] == []
    where = next(e for e in graph["edges"] if e["to"] == "Acme.Logistics.Billing")["where"][0]
    assert where["file"].endswith(".cs") and where["line"] > 0


def test_the_cycle_is_found_with_its_evidence(graph: dict[str, Any]) -> None:
    cycle = next(c for c in graph["cycles"] if "Acme.Logistics.Billing" in c["modules"])
    assert "Acme.Logistics.Shipments" in cycle["modules"]
    assert any(e["where"][0]["file"].endswith("ShipmentService.cs") for e in cycle["edges"])


def test_the_layer_break_is_found(graph: dict[str, Any]) -> None:
    broken = [b for b in graph["layer_breaks"] if b["from"] == "Acme.Logistics.Domain"]
    assert [b["to"] for b in broken] == ["Acme.Logistics.Infrastructure"]
    assert broken[0]["where"][0]["file"] == "src/Acme.Logistics/Domain/Parcel.cs"
    # Infrastructure depending on the domain points inward, which is allowed.
    assert not [b for b in graph["layer_breaks"] if b["from"] == "Acme.Logistics.Infrastructure"]


def test_the_dumping_ground_has_the_highest_fan_in(graph: dict[str, Any]) -> None:
    helpers = next(m for m in graph["modules"] if m["name"] == "Acme.Logistics.Common")
    assert helpers["fan_in"] >= 4 and helpers["fan_out"] == 0 and helpers["instability"] == 0.0
    assert helpers["fan_in"] == max(m["fan_in"] for m in graph["modules"])


def test_hidden_coupling_is_found(graph: dict[str, Any]) -> None:
    hidden = graph["git"]["hidden_coupling"]
    pair = next(h for h in hidden if {h["a"], h["b"]} == set(COCHANGE))
    assert pair["together"] == COCHANGE_COMMITS and pair["import_link"] is False


def test_the_hot_spot_comes_first(graph: dict[str, Any]) -> None:
    top = graph["git"]["hot_spots"][0]
    assert top["file"] == HOT_FILE and top["commits"] == HOT_FILE_COMMITS


def test_one_person_is_named_only_as_where_knowledge_sits(graph: dict[str, Any]) -> None:
    billing = graph["git"]["owners"]["Acme.Logistics.Billing"]
    assert billing["one_person"] is True and billing["top_author"] == BILLING_AUTHOR
    assert not graph["git"]["owners"]["Acme.Logistics.Shipments"]["one_person"]


def modules(repo: Path, *args: str, **files: str) -> dict[str, Any]:
    make_repo(repo, {name.replace("__", "/").replace("_DOT_", "."): text for name, text in files.items()})
    result: dict[str, Any] = run_json(GRAPH, str(repo), *args)
    return result


def pairs(result: dict[str, Any]) -> set[tuple[str, str]]:
    return {(e["from"], e["to"]) for e in result["edges"]}


def test_python_imports_are_read_exactly(tmp_path: Path) -> None:
    result = modules(
        tmp_path / "r",
        src__shop__orders_DOT_py="from shop import billing\n",
        src__shop__billing_DOT_py="import shop.orders\nimport requests\n",
        src__shop____init___DOT_py="",
    )
    assert pairs(result) == {("shop.orders", "shop.billing"), ("shop.billing", "shop.orders")}
    assert [c["modules"] for c in result["cycles"]] == [["shop.billing", "shop.orders"]]


def test_typescript_relative_imports_are_read(tmp_path: Path) -> None:
    result = modules(
        tmp_path / "r",
        web__src__a__x_DOT_ts="import { y } from '../b/y';\nimport { z } from 'lodash';\n",
        web__src__b__y_DOT_ts="export const y = 1;\n",
    )
    assert pairs(result) == {("web/a", "web/b")}


def test_java_and_go_are_read(tmp_path: Path) -> None:
    result = modules(
        tmp_path / "r",
        src__a__A_DOT_java="package com.acme.a;\nimport com.acme.b.B;\nimport java.util.List;\n",
        src__b__B_DOT_java="package com.acme.b;\n",
        go__go_DOT_mod="module example.com/app\n",
        go__x__x_DOT_go='package x\nimport "example.com/app/y"\nimport "fmt"\n',
        go__y__y_DOT_go="package y\n",
    )
    assert pairs(result) >= {("com.acme.a", "com.acme.b"), ("go/x", "go/y")}
    assert not any("fmt" in pair[1] or "java" in pair[1] for pair in pairs(result))


def test_csharp_usings_of_other_libraries_are_ignored(tmp_path: Path) -> None:
    result = modules(
        tmp_path / "r",
        A_DOT_cs="using System;\nusing Acme.B;\nnamespace Acme.A;\n",
        B_DOT_cs="namespace Acme.B { }\n",
    )
    assert pairs(result) == {("Acme.A", "Acme.B")}


def test_depth_groups_modules_and_other_languages_are_counted(tmp_path: Path) -> None:
    result = modules(
        tmp_path / "r",
        "--depth",
        "2",
        A_DOT_cs="using Acme.B.Deep;\nnamespace Acme.A.Deep;\n",
        B_DOT_cs="namespace Acme.B.Deep;\n",
        tool_DOT_rb="puts 1\n",
    )
    assert pairs(result) == {("Acme.A", "Acme.B")}
    assert result["not_covered"] == {"Ruby": 1}


def test_tests_are_left_out_unless_asked(tmp_path: Path) -> None:
    files = {
        "src__shop__a_DOT_py": "import shop.b\n",
        "src__shop__b_DOT_py": "",
        "tests__test_a_DOT_py": "import shop.a\n",
    }
    assert modules(tmp_path / "r", **files)["counts"]["files"] == 2
    assert run_json(GRAPH, str(tmp_path / "r"), "--tests")["counts"]["files"] == 3


def test_layers_can_be_named(tmp_path: Path) -> None:
    result = modules(
        tmp_path / "r",
        "--layers",
        "core,shell",
        A_DOT_cs="using Acme.Shell;\nnamespace Acme.Core;\n",
        B_DOT_cs="namespace Acme.Shell;\n",
    )
    assert [(b["from"], b["to"]) for b in result["layer_breaks"]] == [("Acme.Core", "Acme.Shell")]


def test_a_missing_folder_is_refused() -> None:
    done = subprocess.run([sys.executable, str(GRAPH), "/no/such/folder"], capture_output=True, text=True)
    assert done.returncode == 2


# ---------------------------------------------------------------------------- containers


def test_what_runs_is_found(running: dict[str, Any]) -> None:
    kinds = {d["name"]: d["kind"] for d in running["deployables"]}
    assert sorted(kinds) == sorted(COMPOSE_SERVICES)
    assert kinds["db"] == "database" and kinds["queue"] == "broker" and kinds["api"] == "built here"
    api = next(d for d in running["deployables"] if d["name"] == "api")
    assert set(api["depends_on"]) >= {"db", "queue"}
    web = next(p for p in running["projects"] if p["path"].endswith("Acme.Api.csproj"))
    assert web["kind"] == "web" and web["references"] == ["src/Acme.Logistics/Acme.Logistics.csproj"]


def test_the_synchronous_loop_is_found(running: dict[str, Any]) -> None:
    calls = {(c["from"], c["to"]) for c in running["calls_between_services"]}
    assert {("api", "worker"), ("worker", "api")} <= calls
    assert ["api", "worker"] in running["loops"]


def test_the_shared_table_is_found(running: dict[str, Any]) -> None:
    shared = next(t for t in running["tables_shared"] if t["table"] == "shipments")
    assert set(shared["deployables"]) == {"api", "worker"}
    assert any(p["file"].endswith("db.py") for p in shared["deployables"]["worker"])


def test_settings_are_named_and_never_valued(tmp_path: Path) -> None:
    make_repo(
        tmp_path / "r",
        {
            "docker-compose.yml": (
                "services:\n  api:\n    build: ./api\n    environment:\n      - API_KEY=super-secret-value\n"
                "    depends_on: [db]\n  db:\n    image: postgres:16\n"
            ),
            "api/app.py": 'import os\nkey = os.environ["API_KEY"]\nurl = os.getenv("DB_URL")\n',
        },
    )
    done = subprocess.run(
        [sys.executable, str(CONTAINERS), str(tmp_path / "r")], capture_output=True, text=True, check=True
    )
    result = json.loads(done.stdout)
    assert "super-secret-value" not in done.stdout
    assert result["deployables"][0]["settings"] == ["API_KEY"] and result["deployables"][0]["depends_on"] == ["db"]
    assert sorted(result["settings_read"]) == ["API_KEY", "DB_URL"]


def test_compose_maps_and_build_contexts_are_read() -> None:
    from conftest import load

    services = load(CONTAINERS).read_compose(
        """
services:
  web:
    build:
      context: ./web
    depends_on:
      api:
        condition: service_healthy
    ports:
      - "80:80"
  api:
    image: example/api:1
"""
    )
    assert services["web"]["build"] == "./web" and services["web"]["ports"] == ["80:80"]
    assert services["web"]["depends_on"][0] == "api"
    assert services["api"]["image"] == "example/api:1"


# ---------------------------------------------------------------------------- style_rules

SMALL = {
    "teams": 1,
    "domains": 3,
    "ship_separately": False,
    "scale_ratio": 2,
    "runtimes_differ": False,
    "one_transaction_across": True,
    "long_running": False,
    "idle_most_of_the_time": False,
    "many_react_to_events": False,
    "platform_engineers": 0,
}
FLEET = {
    "teams": 4,
    "domains": 5,
    "ship_separately": True,
    "scale_ratio": 200,
    "runtimes_differ": True,
    "one_transaction_across": False,
    "long_running": True,
    "idle_most_of_the_time": False,
    "many_react_to_events": True,
    "platform_engineers": 2,
}


def rules(facts: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = run_json(RULES, "-", stdin=json.dumps(facts))
    return result


def test_the_small_brief_stays_one_deployable() -> None:
    result = rules(SMALL)
    assert result["open"] == ["monolith", "modular_monolith"]


def test_the_big_brief_needs_services_but_not_microservices() -> None:
    result = rules(FLEET)
    assert result["open"] == ["few_services", "event_services"]
    by_id = {o["id"]: o for o in result["options"]}
    assert [r["rule"] for r in by_id["microservices"]["eliminated_by"]] == ["too-few-platform-engineers"]
    assert {r["rule"] for r in by_id["modular_monolith"]["eliminated_by"]} == {
        "ships-separately",
        "scales-alone",
        "two-runtimes",
    }


def test_unknown_facts_decide_nothing() -> None:
    result = rules({})
    assert len(result["open"]) == 6 and result["thresholds"]["scales_alone_ratio"] == 10
    assert {f["fact"] for f in result["open_facts"]} >= {"teams", "ship_separately"}


@pytest.mark.parametrize(
    ("facts", "closed"),
    [
        ({"domains": 1}, ["modular_monolith"]),
        ({"scale_ratio": 9}, []),
        ({"scale_ratio": 10}, ["monolith", "modular_monolith"]),
        ({"long_running": True}, ["serverless"]),
        ({"idle_most_of_the_time": False}, ["serverless"]),
        ({"many_react_to_events": False}, ["event_services"]),
        ({"teams": 2}, ["microservices"]),
        ({"one_transaction_across": True}, ["few_services", "event_services", "microservices"]),
        ({"platform_engineers": 0}, ["event_services", "microservices"]),
    ],
)
def test_single_rules(facts: dict[str, Any], closed: list[str]) -> None:
    assert [o["id"] for o in rules(facts)["options"] if o["status"] == "eliminated"] == closed


def test_bad_facts_are_refused() -> None:
    done = subprocess.run(
        [sys.executable, str(RULES), "-"], input='{"teams": "many", "colour": 1}', capture_output=True, text=True
    )
    assert done.returncode == 1 and "teams: must be a int" in done.stderr and "colour: unknown fact" in done.stderr


# ---------------------------------------------------------------------------- c4_check


def good() -> dict[str, Any]:
    return {
        "type": "nested",
        "levels": [
            {"id": "context", "label": "Context", "open": []},
            {"id": "containers", "label": "Containers", "open": ["sys"]},
        ],
        "boxes": [
            {"id": "user", "label": "Clerk", "kind": "user"},
            {"id": "sys", "label": "System"},
            {"id": "api", "label": "API", "parent": "sys", "tech": ".NET"},
            {"id": "mail", "label": "Mail", "kind": "system"},
        ],
        "links": [{"from": "user", "to": "api", "label": "uses"}, {"from": "api", "to": "mail", "label": "sends"}],
    }


def checked(tmp_path: Path, data: dict[str, Any]) -> dict[str, Any]:
    path = tmp_path / "c4.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result: dict[str, Any] = run_json(CHECK, str(path))
    return result


def test_a_sound_drawing_passes(tmp_path: Path) -> None:
    result = checked(tmp_path, good())
    assert result["ok"] is True and result["warnings"] == [] and result["counts"]["boxes"] == 4


def test_misleading_drawings_are_named(tmp_path: Path) -> None:
    block = good()
    block["boxes"][0]["parent"] = "sys"
    block["boxes"][3]["parent"] = "sys"
    del block["boxes"][2]["tech"]
    block["links"][0].pop("label")
    block["levels"][1]["open"].append("api")
    errors = checked(tmp_path, block)["errors"]
    assert "user: a person cannot be inside sys" in errors
    assert "mail: an outside system cannot be inside sys" in errors
    assert "api: a container needs its technology" in errors
    assert "link user -> api: no label" in errors
    assert "level containers: opens api, which has nothing inside" in errors


def test_warnings_ask_for_a_look(tmp_path: Path) -> None:
    block = good()
    block["levels"][0]["open"] = ["sys"]
    block["boxes"].append({"id": "lonely", "label": "L", "kind": "system"})
    warnings = checked(tmp_path, block)["warnings"]
    assert "no context level: add one with nothing open" in warnings
    assert "lonely: nothing links to it" in warnings
