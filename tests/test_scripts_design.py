"""design_inventory.py of arch-review, on the acme-design fixture and on small Markdown cases of its own.

The tests run the script from its place in the software-architect plugin. The environment variable DESIGN_INVENTORY,
when set, points them at another copy of it instead, such as one staged outside the plugin.

The inventory lists places to look, not findings. Where a flaw is an absence (no timeout on the calls to the
carriers, no mechanism behind a promise) the tests check only that the place to look is listed: judging what is
missing there is the model's job.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import build_fixture
import pytest
from conftest import ROOT, load, run_json
from test_fixture_acme_design import (
    ADR_BROKER,
    ADR_STATUSES,
    ADR_TRACKING,
    BOOKING_GOAL,
    CARRIER_QUOTE,
    DECOYS_AT,
    GOALS,
    LAYOUT,
    PARTS,
    PLANTED_AT,
    PROPOSAL,
    SERVICES,
)

FINAL = ROOT / "plugins" / "software-architect" / "skills" / "arch-review" / "scripts" / "design_inventory.py"
SCRIPT = Path(os.environ.get("DESIGN_INVENTORY") or FINAL)
LISTS = ("documents", "adrs", "parts", "links", "data_writes", "promises", "quality_goals", "latencies", "open")


@pytest.fixture(scope="module")
def design_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-design fixture, built once for this module. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-design"
    build_fixture.build("acme-design", target)
    return target


@pytest.fixture(scope="module")
def inventory(design_repo: Path) -> dict[str, Any]:
    result: dict[str, Any] = run_json(SCRIPT, str(design_repo))
    return result


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return load(SCRIPT)


def at(entry: dict[str, Any]) -> str:
    return f"{entry['file']}:{entry['line']}"


def entry_at(entries: list[dict[str, Any]], where: str) -> dict[str, Any]:
    found = [e for e in entries if at(e) == where]
    assert len(found) == 1, f"{len(found)} entries at {where}"
    return found[0]


def links(result: dict[str, Any], source: str | None = None) -> set[tuple[str, str, str]]:
    return {(k["from"], k["to"], k["style"]) for k in result["links"] if source in (None, k["source"])}


def scan(script: ModuleType, text: str, name: str = "doc.md") -> dict[str, Any]:
    result: dict[str, Any] = script.scan({name: text})
    return result


# ---------------------------------------------------------------------------- on the fixture


def test_every_document_and_adr_is_listed(inventory: dict[str, Any]) -> None:
    assert [d["file"] for d in inventory["documents"]] == sorted(LAYOUT)
    proposal = next(d for d in inventory["documents"] if d["file"] == PROPOSAL)
    assert proposal["title"] == "Parcel booking v2" and proposal["line"] == 1 and proposal["words"] > 2000
    assert {"line": 142, "level": 3, "text": "Data Service"} in proposal["headings"]
    adrs = {a["number"]: a for a in inventory["adrs"]}
    assert {n: a["status"] for n, a in adrs.items()} == ADR_STATUSES
    assert [adrs[n]["date"] for n in (1, 2, 3, 4)] == ["2026-10-13", "2026-10-14", "2026-10-14", "2026-10-22"]
    assert adrs[3]["title"] == "Tracking reads booking changes by polling"
    assert adrs[1]["title"] == "Split parcel booking into services" and adrs[1]["status_line"] == 7
    assert all(a["supersedes"] == [] and a["superseded_by"] == [] for a in adrs.values())
    assert inventory["counts"]["documents"] == 7 and inventory["counts"]["adrs"] == 4


def test_every_part_is_found_with_its_mentions(inventory: dict[str, Any]) -> None:
    parts = {p["name"]: p for p in inventory["parts"]}
    assert set(PARTS) <= set(parts)
    assert all(parts[name]["mentions"] >= 3 for name in PARTS)
    assert set(parts["Data Service"]["sources"]) == {"diagram", "table", "heading"}
    assert parts["Carrier APIs"]["sources"] == ["diagram", "list"]


def test_every_entry_points_at_a_real_line(design_repo: Path, inventory: dict[str, Any]) -> None:
    lengths = {rel: len((design_repo / rel).read_text(encoding="utf-8").splitlines()) for rel in LAYOUT}
    for key in LISTS:
        assert inventory[key], key
        for entry in inventory[key]:
            assert entry["file"] in lengths and 1 <= entry["line"] <= lengths[entry["file"]], (key, entry)
    for key in ("links", "data_writes", "promises", "quality_goals", "latencies", "open"):
        assert inventory["counts"][key] == len(inventory[key]), key


def test_d1_both_latencies_the_p95_goal_and_the_synchronous_chain(inventory: dict[str, Any]) -> None:
    goal_at, carrier_at, booking_calls_at, pricing_calls_at = PLANTED_AT["D1"]
    goal = entry_at(inventory["quality_goals"], goal_at)
    assert goal["has_number"] is True and goal["numbers"] == [BOOKING_GOAL, "p95"]
    assert entry_at(inventory["latencies"], goal_at)["value"] == BOOKING_GOAL
    carrier = entry_at(inventory["latencies"], carrier_at)
    assert carrier["value"] == CARRIER_QUOTE and "Carrier APIs" in carrier["parts"]
    assert entry_at(inventory["quality_goals"], carrier_at)["numbers"] == [CARRIER_QUOTE]
    chain = [("Booking service", "Pricing service", "sync"), ("Pricing service", "Carrier Gateway", "sync")]
    assert set(chain) <= links(inventory, "diagram")
    by_line = {at(k): (k["from"], k["to"], k["style"]) for k in inventory["links"] if k["source"] == "text"}
    assert [by_line[booking_calls_at], by_line[pricing_calls_at]] == chain


def test_d2_shipments_status_has_two_writers_and_is_the_only_shared_write(inventory: dict[str, Any]) -> None:
    shared = [w for w in inventory["data_writes"] if w["shared_write"]]
    assert [w["entity"] for w in shared] == ["shipments.status"]
    status = shared[0]
    assert status["writers"] == 2 and status["written_by"] == ["Tracking service", "Billing service"]
    assert set(PLANTED_AT["D2"]) <= {at(w) for w in status["where"]}
    assert f"{ADR_TRACKING}:21" in {at(w) for w in status["where"]}


def test_d3_the_promise_is_listed(inventory: dict[str, Any]) -> None:
    promise = entry_at(inventory["promises"], PLANTED_AT["D3"][0])
    assert promise["words"] == ["never"] and "charged twice" in promise["text"]
    assert entry_at(inventory["latencies"], PLANTED_AT["D3"][1])["value"] == "2 seconds"


def test_d4_the_availability_goal_has_no_number(inventory: dict[str, Any]) -> None:
    goal = entry_at(inventory["quality_goals"], PLANTED_AT["D4"][0])
    assert goal["has_number"] is False and goal["numbers"] == []
    assert "highly available" in goal["text"]


def test_d5_the_calls_to_the_carriers_are_listed(inventory: dict[str, Any]) -> None:
    # Only the place to look: that nothing handles a slow or failed carrier is for the model to judge.
    outside = ("Carrier Gateway", "Carrier APIs", "sync")
    assert outside in links(inventory, "diagram")
    assert entry_at([k for k in inventory["links"] if k["source"] == "text"], PLANTED_AT["D5"][0])["verb"] == "calls"
    assert outside in links(inventory, "text")


def test_d6_events_in_the_proposal_and_polling_in_the_adr(inventory: dict[str, Any]) -> None:
    events_at, status_at, polls_at = PLANTED_AT["D6"]
    text = [k for k in inventory["links"] if k["source"] == "text"]
    events = entry_at(text, events_at)
    polls = entry_at(text, polls_at)
    assert (events["from"], events["to"], events["style"]) == ("Tracking service", "Message broker", "async")
    assert (polls["from"], polls["to"], polls["style"], polls["verb"]) == (
        "Tracking service",
        "Booking service",
        "sync",
        "polls",
    )
    adr = next(a for a in inventory["adrs"] if a["number"] == 3)
    assert adr["status"] == "Accepted" and f"{adr['file']}:{adr['status_line']}" == status_at
    assert ("Message broker", "Tracking service", "async") in links(inventory, "diagram")


def test_d7_every_service_links_to_the_data_service(inventory: dict[str, Any]) -> None:
    into = {k["from"] for k in inventory["links"] if k["to"] == "Data Service"}
    assert set(SERVICES) <= into
    assert all((service, "Data Service", "sync") in links(inventory, "diagram") for service in SERVICES)
    top = [p["name"] for p in inventory["parts"][:3]]
    assert "Data Service" in top


def test_d8_the_broker_adr_is_proposed_and_listed_as_open(inventory: dict[str, Any]) -> None:
    adr = next(a for a in inventory["adrs"] if a["number"] == 4)
    assert adr["status"] == "Proposed" and adr["title"] == "Message broker"
    open_at = {at(o): o for o in inventory["open"]}
    assert open_at[PLANTED_AT["D8"][2]]["kind"] == "adr"
    assert open_at[PLANTED_AT["D8"][1]]["marks"] == ["to be decided"]
    assert open_at[f"{ADR_BROKER}:21"]["kind"] == "marker"
    assert {o["kind"] for o in inventory["open"]} == {"adr", "marker", "heading", "question"}


def test_the_decoys_raise_no_flag(inventory: dict[str, Any]) -> None:
    tariffs = next(w for w in inventory["data_writes"] if w["entity"] == "tariffs")
    assert tariffs["written_by"] == ["Pricing service"] and tariffs["shared_write"] is False
    cache = entry_at(inventory["latencies"], DECOYS_AT["OK1"][0])
    assert cache["value"] == "15 minutes" and cache["parts"] == ["Pricing service"]
    consistency = next(g for g in inventory["quality_goals"] if g["file"] == GOALS and "consistent" in g["text"])
    assert consistency["has_number"] is True and consistency["numbers"] == ["15 minutes"]
    assert ("Pricing service", "Pricing database", "unknown") in links(inventory, "diagram")
    budget = entry_at(inventory["latencies"], DECOYS_AT["OK3"][0])
    assert budget["value"] == "50 ms" and budget["parts"] == ["Booking service", "Address Validator"]
    call = entry_at([k for k in inventory["links"] if k["source"] == "text"], DECOYS_AT["OK3"][0])
    assert (call["from"], call["to"], call["style"]) == ("Booking service", "Address Validator", "sync")


# ---------------------------------------------------------------------------- small cases


def test_documents_take_title_headings_and_words_outside_code(script: ModuleType) -> None:
    text = "---\ntitle: ignored\n---\n# Title\n\nSome words here.\n\n## Part two\n\n```python\nnot counted\n```\n"
    doc = scan(script, text)["documents"][0]
    assert doc["title"] == "Title" and doc["line"] == 4 and doc["words"] == 6
    assert doc["headings"] == [{"line": 4, "level": 1, "text": "Title"}, {"line": 8, "level": 2, "text": "Part two"}]
    assert scan(script, "no heading at all\n", "notes/plain.txt")["documents"][0]["title"] == "plain"


def test_adr_fields_from_nygard_madr_and_front_matter(script: ModuleType) -> None:
    result = script.scan(
        {
            "adr/0007-use-postgres.md": (
                "# 7. Use Postgres\n\nDate: 2026-01-05\n\n## Status\n\n"
                "Superseded by [ADR-0009](0009-use-sqlite.md)\n\n## Context\n\nText.\n"
            ),
            "adr/0009-use-sqlite.md": (
                "# ADR-0009: Use SQLite\n\n* Status: accepted\n* Date: 2026-02-01\n\nSupersedes ADR-0007.\n"
            ),
            "notes/cache.md": "---\nstatus: proposed\ndate: 2026-03-03\n---\n# Cache tariffs\n\nSome text.\n",
            "notes/plain.md": "# Not an ADR\n\nNo status here.\n",
        }
    )
    adrs = {a["file"]: a for a in result["adrs"]}
    assert set(adrs) == {"adr/0007-use-postgres.md", "adr/0009-use-sqlite.md", "notes/cache.md"}
    old = adrs["adr/0007-use-postgres.md"]
    assert (old["number"], old["title"], old["status"], old["status_line"], old["date"]) == (
        7,
        "Use Postgres",
        "Superseded",
        7,
        "2026-01-05",
    )
    assert old["superseded_by"] == [9] and old["supersedes"] == []
    new = adrs["adr/0009-use-sqlite.md"]
    assert (new["number"], new["title"], new["status"], new["supersedes"]) == (9, "Use SQLite", "Accepted", [7])
    cache = adrs["notes/cache.md"]
    assert (cache["number"], cache["status"], cache["date"], cache["status_line"]) == (
        None,
        "Proposed",
        "2026-03-03",
        2,
    )
    assert [(o["file"], o["kind"]) for o in result["open"]] == [("notes/cache.md", "adr")]


def test_mermaid_nodes_and_edges(script: ModuleType) -> None:
    text = (
        "# Map\n\n```mermaid\nflowchart TD\n"
        "    A[Order service] -->|REST| B(Stock service)\n"
        "    B -.-> C{{Event bus}}\n"
        "    C -->|order events| D[(Orders DB)]\n"
        "    A -- gRPC --> E{Fraud check}\n"
        "    A & B --> F[Audit log] --> G[Archive store]\n"
        "    %% X --> Y is a comment\n"
        "    subgraph P [Platform services]\n    end\n"
        "```\n\n```mermaid\nsequenceDiagram\n    A->>B: not read\n```\n"
    )
    result = scan(script, text)
    names = {p["name"] for p in result["parts"]}
    assert names == {"Order service", "Stock service", "Event bus", "Orders DB", "Fraud check", "Audit log"} | {
        "Archive store"
    }
    found = {(k["from"], k["to"], k["style"], k["label"], k["arrow"]) for k in result["links"]}
    assert found == {
        ("Order service", "Stock service", "sync", "REST", "-->"),
        ("Stock service", "Event bus", "unknown", "", "-.->"),
        ("Event bus", "Orders DB", "async", "order events", "-->"),
        ("Order service", "Fraud check", "sync", "gRPC", "-->"),
        ("Order service", "Audit log", "unknown", "", "-->"),
        ("Stock service", "Audit log", "unknown", "", "-->"),
        ("Audit log", "Archive store", "unknown", "", "-->"),
    }
    assert {k["line"] for k in result["links"]} == {5, 6, 7, 8, 9}


def test_component_tables_bold_leads_and_headings_name_parts(script: ModuleType) -> None:
    text = (
        "# Parts\n\n| Service | Owner |\n|---|---|\n| Ledger service | finance |\n\n"
        "- **Rate limiter**: guards the API.\n- a plain item\n\n"
        "## Notification worker\n\nSends mail.\n\n## Background\n\nThe Ledger service calls the Notification worker.\n"
    )
    parts = {p["name"]: p for p in scan(script, text)["parts"]}
    assert set(parts) == {"Ledger service", "Rate limiter", "Notification worker"}
    assert parts["Ledger service"]["sources"] == ["table"] and parts["Ledger service"]["mentions"] == 2
    assert parts["Ledger service"]["line"] == 5
    assert parts["Rate limiter"]["sources"] == ["list"] and parts["Notification worker"]["sources"] == ["heading"]


COMPONENTS = (
    "| Component |\n|---|\n| Web app |\n| Mobile app |\n| Order service |\n| Stock service |\n| Event bus |\n"
    "| Report job |\n| Mail relay |\n| Pricing service |\n| Tax service |\n\n"
)


def test_sentence_links_and_their_style(script: ModuleType) -> None:
    text = COMPONENTS + (
        "The Web app and the Mobile app call the Order service over REST.\n"
        "The Order service publishes an event to the Event bus.\n"
        "The Report job reads from the Order service, and the Stock service polls the Order service.\n"
        "The Order service sends a note to the Mail relay.\n"
        "The Order service calls the Pricing service, which calls the Tax service.\n"
        "The Order service receives stock events from the Event bus.\n"
        "After the Mail relay answers, the Stock service is done.\n"
    )
    found = {(k["from"], k["to"], k["style"], k["verb"], k["line"]) for k in scan(script, text)["links"]}
    assert found == {
        ("Web app", "Order service", "sync", "call", 13),
        ("Mobile app", "Order service", "sync", "call", 13),
        ("Order service", "Event bus", "async", "publishes", 14),
        ("Report job", "Order service", "unknown", "reads from", 15),
        ("Stock service", "Order service", "sync", "polls", 15),
        ("Order service", "Mail relay", "unknown", "sends", 16),
        ("Order service", "Pricing service", "sync", "calls", 17),
        ("Pricing service", "Tax service", "sync", "calls", 17),
        ("Order service", "Event bus", "async", "receives", 18),
    }


def test_data_writes_from_sentences_passive_forms_and_tables(script: ModuleType) -> None:
    text = COMPONENTS + (
        "The Order service writes `orders` and `order_lines`.\n"
        "The Stock service updates `orders.state` to shipped.\n"
        "`orders.state` is also written by the Report job.\n"
        "The Order service calls the Stock service and sets `stock`.\n"
        "The Order service sets `refunds` to `pending` on a refund.\n"
        "When the Mail relay answers, the Order service updates `outbox`.\n"
        "The Stock service caches `orders` for a minute.\n\n"
        "| Table | Owner |\n|---|---|\n| `stock` | Stock service |\n| `audit` | Report job |\n"
    )
    writes = {w["entity"]: w for w in scan(script, text)["data_writes"]}
    assert {e: w["written_by"] for e, w in writes.items()} == {
        "orders": ["Order service"],
        "order_lines": ["Order service"],
        "orders.state": ["Stock service", "Report job"],
        "stock": ["Order service", "Stock service"],
        "refunds": ["Order service"],
        "outbox": ["Order service"],
        "audit": ["Report job"],
    }
    assert {e for e, w in writes.items() if w["shared_write"]} == {"orders.state", "stock"}
    assert writes["orders.state"]["writers"] == 2 and writes["orders.state"]["line"] == 14
    assert {(p["part"], p["verb"]) for p in writes["stock"]["where"]} == {
        ("Order service", "sets"),
        ("Stock service", "owner"),
    }


def test_promises_name_their_words(script: ModuleType) -> None:
    text = (
        "Every order is charged exactly once.\nPayments are idempotent.\nThere is no data loss on failover.\n"
        "Writes are at-least once and atomic.\nNothing special here.\n"
    )
    found = [(p["line"], p["words"]) for p in scan(script, text)["promises"]]
    assert found == [
        (1, ["every", "exactly once"]),
        (2, ["idempotent"]),
        (3, ["no data loss"]),
        (4, ["at least", "atomic"]),
    ]


def test_quality_goals_say_whether_they_have_a_number(script: ModuleType) -> None:
    text = (
        "The API must answer in 200 ms at p99.\nAvailability is 99.9 % per month.\n"
        "The system handles 1,200 requests per second at peak.\nThe platform must scale.\n"
        "RTO is 4 hours and RPO is 15 minutes.\nWe value consistency.\nThe sky is blue.\n"
    )
    found = [(g["line"], g["has_number"], g["numbers"]) for g in scan(script, text)["quality_goals"]]
    assert found == [
        (1, True, ["200 ms", "p99"]),
        (2, True, ["99.9 %"]),
        (3, True, ["1,200 requests per second"]),
        (4, False, []),
        (5, True, ["4 hours", "15 minutes"]),
        (6, False, []),
    ]


def test_latencies_are_every_stated_duration_with_its_parts(script: ModuleType) -> None:
    text = COMPONENTS + (
        "The Tax service answers in 400\u2013800 ms.\nRetries wait 2 s, then 10 seconds.\n"
        "Tariffs may be 15-minute old.\nOn 2026-10-29 ADR-0004 and v2 say nothing about time.\n"
    )
    found = [(k["line"], k["value"], k["parts"]) for k in scan(script, text)["latencies"]]
    assert found == [
        (13, "400\u2013800 ms", ["Tax service"]),
        (14, "2 s", []),
        (14, "10 seconds", []),
        (15, "15-minute", []),
    ]


def test_open_items_are_markers_questions_and_headings(script: ModuleType) -> None:
    text = (
        "# Plan\n\nTBD: pick a queue.\nThe format is to be decided later.\nWe will decide later.\n\n"
        "## Open questions\n\n- Who runs it?\n- A plain item.\n\nIs this a question in a paragraph?\n"
    )
    found = [(o["line"], o["kind"]) for o in scan(script, text)["open"]]
    assert found == [(3, "marker"), (4, "marker"), (5, "marker"), (7, "heading"), (9, "question")]


def test_env_files_are_never_opened(tmp_path: Path) -> None:
    folder = tmp_path / "docs"
    (folder / "sub").mkdir(parents=True)
    (folder / "design.md").write_text("# Design\n\nThe Order service calls the Stock service.\n", encoding="utf-8")
    (folder / ".env.local").write_text("API_KEY=super-secret-value\n", encoding="utf-8")
    (folder / "sub" / ".env.md").write_text("# Secret\n\nsuper-secret-value\n", encoding="utf-8")
    if hasattr(os, "mkfifo"):
        os.mkfifo(folder / ".env")  # opening a pipe with no writer hangs, so a run that opens it times out
    else:
        (folder / ".env").write_text("API_KEY=super-secret-value\n", encoding="utf-8")
    for args in ([str(folder)], [str(folder / "design.md"), str(folder / ".env"), str(folder / ".env.local")]):
        done = subprocess.run(
            [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=True, timeout=30
        )
        assert "super-secret-value" not in done.stdout
    result = run_json(SCRIPT, str(folder))
    assert [d["file"] for d in result["documents"]] == ["design.md"]
    assert result["skipped"] == [".env", ".env.local", "sub/.env.md"]


def test_paths_are_relative_to_the_folder_the_arguments_share(tmp_path: Path) -> None:
    for rel in ("a/x.md", "b/y.markdown", "b/z.adoc", "b/code.py"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("= Title\n\nText.\n", encoding="utf-8")
    result = run_json(SCRIPT, str(tmp_path / "a" / "x.md"), str(tmp_path / "b"), str(tmp_path / "b" / "code.py"))
    assert [d["file"] for d in result["documents"]] == ["a/x.md", "b/y.markdown", "b/z.adoc"]
    assert next(d for d in result["documents"] if d["file"] == "b/z.adoc")["title"] == "Title"
    assert result["skipped"] == ["b/code.py"]


def test_a_missing_path_is_refused() -> None:
    done = subprocess.run([sys.executable, str(SCRIPT), "/no/such/folder"], capture_output=True, text=True)
    assert done.returncode == 2 and "not found" in done.stderr
