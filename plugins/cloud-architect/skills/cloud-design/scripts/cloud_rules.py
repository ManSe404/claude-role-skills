#!/usr/bin/env python3
"""Apply the hard rules of the cloud design ladders to the facts of a brief.

Usage: python3 cloud_rules.py FACTS.json      (or - for stdin)
       python3 cloud_rules.py --facts          (list the facts it reads, with what each one decides)

Five ladders, each neutral and simplest first: compute, data, network, region, availability. A provider file
maps each option to real services; this script knows no provider. Each rule eliminates options that cannot
meet a fact of the brief, or that nothing in the brief asks for. It never chooses: it prints what is open per
ladder, the lowest open option, and the facts that are unknown but would eliminate something.

The thresholds are judgements, named below and printed so a page can show them. A fact that is missing or null
decides nothing. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

LADDERS: dict[str, list[tuple[str, str]]] = {
    "compute": [
        ("managed_app_platform", "A managed app platform"),
        ("serverless_containers", "Serverless containers"),
        ("functions", "Functions"),
        ("kubernetes", "Kubernetes"),
        ("virtual_machines", "Virtual machines"),
    ],
    "data": [
        ("managed_relational", "One managed relational database"),
        ("managed_relational_scaled", "A managed relational database with read replicas"),
        ("managed_document", "A managed document or key-value store"),
        ("self_managed", "A self-managed database"),
    ],
    "network": [
        ("public_restricted", "Public endpoints, restricted"),
        ("private_data", "Private endpoints for the data"),
        ("fully_private", "Everything private behind one entry"),
        ("hub_and_spoke", "Hub and spoke"),
    ],
    "region": [
        ("one_region", "One region"),
        ("two_regions", "Two regions, active and standby"),
    ],
    "availability": [
        ("one_zone", "One availability zone"),
        ("zone_redundant", "Zone redundant"),
        ("multi_region", "Multi-region"),
    ],
}
THRESHOLDS = {
    "app_platform_max_services": 5,  # beyond this, one plan per app is more to run than a container platform
    "kubernetes_min_services": 15,  # below this, nothing asks for a cluster unless the Kubernetes API is needed
    "kubernetes_min_platform_engineers": 2,  # a cluster needs people for upgrades, networking and on-call
    "functions_max_minutes": 10,  # past this, work no longer fits the function model
    "relational_max_gb": 4000,  # the managed single-server ceiling to design against; check the provider's real limit
    "read_replica_min_rps": 1000,  # below this, one well-sized database handles the reads
}
FACTS: dict[str, tuple[str, str]] = {
    "team_size": ("int", "engineers who build and run it"),
    "platform_engineers": ("int", "people who can run a platform: upgrades, networking, on-call"),
    "services": ("int", "how many separately deployed services"),
    "containers": ("bool", "does it already ship as container images, or must it?"),
    "needs_kubernetes_api": ("bool", "does it need the Kubernetes API, an operator or a daemon on every node?"),
    "needs_os_control": ("bool", "does it need control of the operating system or a kernel feature?"),
    "event_driven": ("bool", "does the work arrive as events and is short per event?"),
    "max_job_minutes": ("number", "the longest single unit of work, in minutes"),
    "peak_rps": ("number", "requests per second at peak"),
    "relational": ("bool", "is the data relational (transactions across rows)?"),
    "data_gb": ("number", "the database size in GB"),
    "private_data": ("bool", "must data stores be reachable only on private addresses?"),
    "private_everything": ("bool", "must compute also be unreachable from the internet, except one entry?"),
    "many_networks": ("bool", "must several networks or teams connect through a shared network?"),
    "survive_zone_loss": ("bool", "must it survive the loss of one availability zone?"),
    "survive_region_loss": ("bool", "must it survive the loss of a whole region?"),
    "residency_area": ("str", "the area data must stay in, such as EU"),
}
WOULD_DECIDE: dict[str, list[tuple[str, str]]] = {
    "services": [("compute", "managed_app_platform"), ("compute", "kubernetes")],
    "containers": [("compute", "functions")],
    "needs_kubernetes_api": [("compute", "kubernetes")],
    "needs_os_control": [
        ("compute", "virtual_machines"),
        ("compute", "managed_app_platform"),
        ("compute", "serverless_containers"),
    ],
    "platform_engineers": [("compute", "kubernetes"), ("data", "self_managed")],
    "event_driven": [("compute", "functions")],
    "max_job_minutes": [("compute", "functions")],
    "relational": [("data", "managed_relational"), ("data", "managed_document")],
    "data_gb": [("data", "managed_relational")],
    "peak_rps": [("data", "managed_relational_scaled")],
    "private_data": [("network", "public_restricted")],
    "private_everything": [("network", "public_restricted"), ("network", "private_data")],
    "many_networks": [("network", "hub_and_spoke")],
    "survive_zone_loss": [("availability", "one_zone")],
    "survive_region_loss": [("availability", "one_zone"), ("availability", "zone_redundant"), ("region", "one_region")],
}


def _rules(f: dict[str, Any]) -> list[tuple[str, str, list[str], str]]:
    """Every rule that fires, as (ladder, name, options it eliminates, why)."""
    rules: list[tuple[str, str, list[str], str]] = []
    t = THRESHOLDS

    services = f.get("services")
    if services is not None and services > t["app_platform_max_services"]:
        rules.append(
            (
                "compute",
                "too-many-services",
                ["managed_app_platform"],
                f"{services} services exceed {t['app_platform_max_services']} for one managed app platform.",
            )
        )
    if f.get("needs_os_control") is True:
        rules.append(
            (
                "compute",
                "needs-the-os",
                ["managed_app_platform", "serverless_containers", "functions"],
                "It needs control of the operating system.",
            )
        )
    if f.get("needs_kubernetes_api") is True:
        rules.append(
            (
                "compute",
                "needs-kubernetes-api",
                ["managed_app_platform", "serverless_containers", "functions", "virtual_machines"],
                "It needs the Kubernetes API, an operator or a daemon on every node.",
            )
        )
    if f.get("containers") is True:
        rules.append(
            (
                "compute",
                "ships-as-containers",
                ["functions"],
                "It ships as container images, which is not the functions model.",
            )
        )
    if f.get("event_driven") is False:
        rules.append(("compute", "not-event-driven", ["functions"], "The work is not short, event-driven units."))
    minutes = f.get("max_job_minutes")
    if minutes is not None and minutes > t["functions_max_minutes"]:
        rules.append(
            ("compute", "long-work", ["functions"], f"Work takes {minutes} minutes, past {t['functions_max_minutes']}.")
        )
    if f.get("needs_os_control") is False:
        rules.append(("compute", "no-need-for-vms", ["virtual_machines"], "Nothing needs a machine of its own."))
    engineers = f.get("platform_engineers")
    if engineers is not None and engineers < t["kubernetes_min_platform_engineers"]:
        rules.append(
            (
                "compute",
                "too-few-platform-engineers",
                ["kubernetes"],
                f"{engineers} platform engineer(s), at least {t['kubernetes_min_platform_engineers']} needed.",
            )
        )
    if f.get("needs_kubernetes_api") is False and services is not None and services < t["kubernetes_min_services"]:
        rules.append(
            (
                "compute",
                "nothing-asks-for-kubernetes",
                ["kubernetes"],
                f"No need for the Kubernetes API, and {services} services is under {t['kubernetes_min_services']}.",
            )
        )

    if f.get("relational") is False:
        rules.append(
            (
                "data",
                "not-relational",
                ["managed_relational", "managed_relational_scaled"],
                "The data is not relational.",
            )
        )
    if f.get("relational") is True:
        rules.append(("data", "needs-transactions", ["managed_document"], "The data needs transactions across rows."))
    gb = f.get("data_gb")
    if gb is not None and gb > t["relational_max_gb"]:
        rules.append(
            (
                "data",
                "too-big-for-one-server",
                ["managed_relational"],
                f"{gb} GB is past {t['relational_max_gb']} GB; check the provider's real limit.",
            )
        )
    rps = f.get("peak_rps")
    if rps is not None and rps < t["read_replica_min_rps"]:
        rules.append(
            (
                "data",
                "no-need-for-replicas",
                ["managed_relational_scaled"],
                f"{rps} requests a second is under {t['read_replica_min_rps']}.",
            )
        )
    if engineers is not None and engineers < t["kubernetes_min_platform_engineers"]:
        rules.append(
            (
                "data",
                "nobody-runs-a-database",
                ["self_managed"],
                f"{engineers} platform engineer(s) cannot run their own database.",
            )
        )

    if f.get("private_data") is True:
        rules.append(
            (
                "network",
                "data-must-be-private",
                ["public_restricted"],
                "Data stores must be reachable only on private addresses.",
            )
        )
    if f.get("private_everything") is True:
        rules.append(
            (
                "network",
                "compute-must-be-private",
                ["public_restricted", "private_data"],
                "Compute must not be reachable from the internet, except one entry.",
            )
        )
    if f.get("many_networks") is False:
        rules.append(("network", "one-network", ["hub_and_spoke"], "One network is enough."))

    if f.get("survive_region_loss") is True:
        rules.append(("region", "survive-a-region-loss", ["one_region"], "It must survive the loss of a whole region."))
        rules.append(
            (
                "availability",
                "survive-a-region-loss",
                ["one_zone", "zone_redundant"],
                "It must survive the loss of a whole region.",
            )
        )
    if f.get("survive_region_loss") is False:
        rules.append(("region", "one-region-is-enough", ["two_regions"], "Losing a whole region is an accepted risk."))
        rules.append(
            ("availability", "one-region-is-enough", ["multi_region"], "Losing a whole region is an accepted risk.")
        )
    if f.get("survive_zone_loss") is True:
        rules.append(
            ("availability", "survive-a-zone-loss", ["one_zone"], "It must survive the loss of one availability zone.")
        )
    if f.get("survive_zone_loss") is False:
        rules.append(
            (
                "availability",
                "one-zone-is-enough",
                ["zone_redundant", "multi_region"],
                "An outage of one zone is acceptable.",
            )
        )
    return rules


def check(facts: Any) -> list[str]:
    if not isinstance(facts, dict):
        return ["facts: must be a JSON object"]
    errs = []
    for key, value in facts.items():
        if key not in FACTS:
            errs.append(f"{key}: unknown fact (known: {', '.join(FACTS)})")
            continue
        if value is None:
            continue
        kind = FACTS[key][0]
        ok = {
            "bool": isinstance(value, bool),
            "int": isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            "number": isinstance(value, int | float) and not isinstance(value, bool) and value >= 0,
            "str": isinstance(value, str),
        }[kind]
        if not ok:
            errs.append(f"{key}: must be a {kind}")
    return errs


def decide(facts: dict[str, Any]) -> dict[str, Any]:
    eliminated: dict[str, dict[str, list[dict[str, str]]]] = {
        name: {key: [] for key, _ in ladder} for name, ladder in LADDERS.items()
    }
    for ladder, rule, gone, why in _rules(facts):
        for option in gone:
            eliminated[ladder][option].append({"rule": rule, "why": why})
    ladders: dict[str, Any] = {}
    for name, options in LADDERS.items():
        rows = [
            {
                "id": key,
                "label": label,
                "rung": rung,
                "status": "eliminated" if eliminated[name][key] else "open",
                "eliminated_by": eliminated[name][key],
            }
            for rung, (key, label) in enumerate(options)
        ]
        still_open = [r["id"] for r in rows if r["status"] == "open"]
        ladders[name] = {"options": rows, "open": still_open, "lowest_open": still_open[0] if still_open else None}
    open_facts = []
    for fact, could in WOULD_DECIDE.items():
        if facts.get(fact) is None:
            affected = [f"{ladder}: {option}" for ladder, option in could if option in ladders[ladder]["open"]]
            if affected:
                open_facts.append({"fact": fact, "means": FACTS[fact][1], "could_eliminate": affected})
    return {
        "ladders": ladders,
        "open_facts": open_facts,
        "thresholds": THRESHOLDS,
        "facts": {k: facts.get(k) for k in FACTS},
        "note": "Hard rules only. An open option is not a choice: weigh the open ones by whether this team can run it, "
        "what they need to learn, what it costs, and how it fails, and climb above the lowest for a named reason.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the hard rules of the cloud design ladders.")
    parser.add_argument("facts", nargs="?", help="a JSON file of facts, or - for stdin")
    parser.add_argument("--facts", dest="list_facts", action="store_true", help="list the facts and exit")
    args = parser.parse_args(argv)
    if args.list_facts or not args.facts:
        json.dump({k: {"type": t, "means": m} for k, (t, m) in FACTS.items()}, sys.stdout, indent=1, ensure_ascii=False)
        print()
        return 0
    try:
        raw = sys.stdin.read() if args.facts == "-" else Path(args.facts).read_text(encoding="utf-8")
        facts = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read the facts: {exc}", file=sys.stderr)
        return 2
    errors = check(facts)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    json.dump(decide(facts), sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
