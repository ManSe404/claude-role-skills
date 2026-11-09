#!/usr/bin/env python3
"""Apply the hard rules of the architecture style ladder to the facts of a brief.

Usage: python3 style_rules.py FACTS.json      (or - for stdin)
       python3 style_rules.py --facts          (list the facts it reads, with what each one decides)

The ladder, by moving parts: one deployable, a modular monolith, serverless functions, a few services,
services with an event backbone, microservices. Each rule eliminates options that cannot meet a fact
of the brief, or that nothing in the brief asks for. The script never chooses: it prints which options
are still open, the lowest open one, and the facts that are unknown but would eliminate something.

The thresholds are judgements, named below and printed so the page can show them. A fact that is missing
or null decides nothing. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

OPTIONS = [
    ("monolith", "One deployable"),
    ("modular_monolith", "A modular monolith"),
    ("serverless", "Serverless functions"),
    ("few_services", "A few services"),
    ("event_services", "Services with an event backbone"),
    ("microservices", "Microservices"),
]
THRESHOLDS = {
    "scales_alone_ratio": 10,  # below this, running more copies of everything is cheaper than splitting
    "microservices_min_teams": 3,  # fewer teams cannot own many services
    "microservices_min_platform_engineers": 3,  # people for deployment, tracing and on-call across services
}
ONE_DEPLOYABLE = ["monolith", "modular_monolith"]
SPLIT = ["few_services", "event_services", "microservices"]
FACTS: dict[str, tuple[str, str]] = {
    "teams": ("int", "teams that would ship separately"),
    "domains": ("int", "distinct business areas"),
    "ship_separately": ("bool", "must parts be released on their own schedules?"),
    "scale_ratio": ("number", "how many times more load the busiest part takes than the rest"),
    "runtimes_differ": ("bool", "does a part need a different language or runtime?"),
    "one_transaction_across": ("bool", "must one transaction span several business areas?"),
    "long_running": ("bool", "does work run for more than 15 minutes, or hold a connection or state?"),
    "idle_most_of_the_time": ("bool", "is the system idle most of the time, with spikes?"),
    "many_react_to_events": ("bool", "must several independent consumers react to the same events?"),
    "platform_engineers": ("int", "people who can run deployment, tracing and on-call across services"),
}
WOULD_DECIDE: dict[str, list[str]] = {
    "teams": ["microservices"],
    "domains": ["modular_monolith"],
    "ship_separately": [*ONE_DEPLOYABLE, *SPLIT],
    "scale_ratio": [*ONE_DEPLOYABLE, *SPLIT],
    "runtimes_differ": [*ONE_DEPLOYABLE, *SPLIT],
    "one_transaction_across": SPLIT,
    "long_running": ["serverless"],
    "idle_most_of_the_time": ["serverless"],
    "many_react_to_events": ["event_services"],
    "platform_engineers": ["event_services", "microservices"],
}


def _rules(f: dict[str, Any]) -> list[tuple[str, list[str], str]]:
    """Every rule that fires, as (name, options it eliminates, why)."""
    rules: list[tuple[str, list[str], str]] = []
    ratio = THRESHOLDS["scales_alone_ratio"]
    scales_alone = None if f.get("scale_ratio") is None else f["scale_ratio"] >= ratio
    if f.get("domains") == 1:
        rules.append(("one-domain", ["modular_monolith"], "One business area: there is nothing to separate."))
    if f.get("ship_separately") is True:
        rules.append(("ships-separately", ONE_DEPLOYABLE, "Parts must be released on their own schedules."))
    if scales_alone:
        rules.append(
            (
                "scales-alone",
                ONE_DEPLOYABLE,
                f"One part takes {f['scale_ratio']} times the load of the rest (≥ {ratio}).",
            )
        )
    if f.get("runtimes_differ") is True:
        rules.append(("two-runtimes", ONE_DEPLOYABLE, "A part needs a different language or runtime."))
    reasons = [f.get("ship_separately"), scales_alone, f.get("runtimes_differ")]
    if all(reason is False for reason in reasons):
        rules.append(("no-reason-to-split", SPLIT, "Nothing asks for separate deployment, scaling or runtimes."))
    if f.get("one_transaction_across") is True:
        rules.append(("one-transaction", SPLIT, "One transaction must span areas, which needs one database."))
    if f.get("long_running") is True:
        rules.append(("long-running", ["serverless"], "Work runs long or holds state, past what functions allow."))
    if f.get("idle_most_of_the_time") is False:
        rules.append(("not-idle", ["serverless"], "Load is steady, so paying per call saves nothing."))
    if f.get("many_react_to_events") is False:
        rules.append(("nobody-to-notify", ["event_services"], "No independent consumers need the same events."))
    if f.get("teams") is not None and f["teams"] < THRESHOLDS["microservices_min_teams"]:
        rules.append(
            (
                "too-few-teams",
                ["microservices"],
                f"{f['teams']} team(s): at least {THRESHOLDS['microservices_min_teams']} are needed to own them.",
            )
        )
    engineers = f.get("platform_engineers")
    if engineers == 0:
        rules.append(("nobody-runs-a-broker", ["event_services"], "Nobody can run a broker and trace through it."))
    needed = THRESHOLDS["microservices_min_platform_engineers"]
    if engineers is not None and engineers < needed:
        rules.append(
            (
                "too-few-platform-engineers",
                ["microservices"],
                f"{engineers} platform engineer(s), at least {needed} needed.",
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
        }[kind]
        if not ok:
            errs.append(f"{key}: must be a {kind}")
    return errs


def decide(facts: dict[str, Any]) -> dict[str, Any]:
    by_option: dict[str, list[dict[str, str]]] = {key: [] for key, _ in OPTIONS}
    for name, eliminated, why in _rules(facts):
        for key in eliminated:
            by_option[key].append({"rule": name, "why": why})
    options = [
        {
            "id": key,
            "label": label,
            "rung": rung,
            "status": "eliminated" if by_option[key] else "open",
            "eliminated_by": by_option[key],
        }
        for rung, (key, label) in enumerate(OPTIONS)
    ]
    still_open = [o["id"] for o in options if o["status"] == "open"]
    open_facts = []
    for fact, could in WOULD_DECIDE.items():
        if facts.get(fact) is None:
            affected = [k for k in could if k in still_open]
            if affected:
                open_facts.append({"fact": fact, "means": FACTS[fact][1], "could_eliminate": affected})
    return {
        "options": options,
        "open": still_open,
        "lowest_open": still_open[0] if still_open else None,
        "open_facts": open_facts,
        "thresholds": THRESHOLDS,
        "facts": {k: facts.get(k) for k in FACTS},
        "note": "Hard rules only. An open option is not a choice: weigh the open ones by whether this team can run "
        "it, consistency, change independence, operations and cost, and climb above the lowest for a named reason.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the hard rules of the architecture style ladder.")
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
