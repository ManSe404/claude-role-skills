#!/usr/bin/env python3
"""Apply the hard rules of the AI pattern ladder to the facts of a brief.

Usage: python3 decide.py FACTS.json      (or - for stdin)
       python3 decide.py --facts          (list the facts it reads, with what each one decides)

The ladder, simplest first: no LLM, one model call, the whole corpus in the prompt, RAG, a
workflow (a fixed chain or a router), agentic RAG, one agent with tools, an orchestrator with
subagents. Each rule below eliminates options that cannot meet a fact of the brief. The script
never chooses: it prints which options are still open, the lowest open rung, and the facts that are
unknown but would eliminate something. Weighing the open options (predictability, cost of an
error, observability, latency, cost) is the architect's job.

A fact that is missing or null decides nothing; it is listed under open_facts instead. Read-only,
standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

OPTIONS = [
    ("no_llm", "No LLM: rules, search or a form"),
    ("single_call", "One model call"),
    ("long_context", "The whole corpus in the prompt"),
    ("rag", "RAG: retrieve, then one call"),
    ("workflow", "Workflow: a fixed chain or a router"),
    ("agentic_rag", "Agentic RAG: the model decides what to retrieve"),
    ("single_agent", "One agent with tools"),
    ("multi_agent", "Orchestrator with subagents"),
]
LLM = [key for key, _ in OPTIONS if key != "no_llm"]
AGENTS = ["agentic_rag", "single_agent", "multi_agent"]
# The fewest model calls in a row each option needs for one request; used by the latency rule.
MIN_CALLS = {
    "no_llm": 0,
    "single_call": 1,
    "long_context": 1,
    "rag": 1,
    "workflow": 2,
    "agentic_rag": 2,
    "single_agent": 2,
    "multi_agent": 3,
}

# fact: (type, what it means)
FACTS: dict[str, tuple[str, str]] = {
    "needs_language": ("bool", "the job needs reading or writing free text, not just fields and rules"),
    "uses_documents": ("bool", "answers draw on a body of documents: manuals, policies, contracts"),
    "corpus_tokens": ("int", "estimated tokens of those documents (corpus_stats.py, or the brief for the full set)"),
    "context_budget_tokens": ("int", "tokens of documents one call may carry: a share of the model's window"),
    "live_state": ("bool", "answers need data that changes faster than an index is rebuilt: order status, stock"),
    "steps_known": ("bool", "the steps for every kind of request can be written down in advance"),
    "distinct_steps": ("int", "how many distinct steps or routes the job has"),
    "independent_subtasks": ("bool", "the work splits into parts that each need their own context and can run apart"),
    "error_cost": ("level", "what a wrong result costs: low, medium or high"),
    "human_review": ("bool", "a person checks the result before it reaches the customer or takes effect"),
    "latency_budget_s": ("number", "the answer must start within this many seconds"),
    "seconds_per_call": ("number", "a typical model call of this size takes this long (measured or from the provider)"),
}
LEVELS = ("low", "medium", "high")


def _rules(f: dict[str, Any]) -> list[tuple[str, list[str], str]]:
    """Every rule that fires, as (name, options it eliminates, why). A rule whose facts are unknown
    does not fire; decide() reports those facts as open."""
    rules: list[tuple[str, list[str], str]] = []

    def known(*names: str) -> bool:
        return all(f.get(n) is not None for n in names)

    if f.get("needs_language") is False:
        rules.append(
            ("no-language", LLM, "Nothing needs free text: rules, a lookup or a form do it without model errors.")
        )
    if f.get("needs_language") is True:
        rules.append(("needs-language", ["no_llm"], "The job reads or writes free text."))
    if f.get("uses_documents") is False:
        rules.append(
            (
                "no-documents",
                ["long_context", "rag", "agentic_rag"],
                "There are no documents to put in the prompt or to retrieve.",
            )
        )
    if f.get("uses_documents") is True:
        rules.append(
            (
                "needs-a-source",
                ["single_call"],
                "A bare call answers from the model's training data, not from the documents.",
            )
        )
    if f.get("live_state") is True:
        rules.append(
            (
                "live-state",
                ["single_call", "long_context", "rag"],
                "Live state needs a call to the system that owns it; an index or a prompt holds a stale copy.",
            )
        )
    fits = known("corpus_tokens", "context_budget_tokens") and f["corpus_tokens"] <= f["context_budget_tokens"]
    if f.get("uses_documents") is True and known("corpus_tokens", "context_budget_tokens") and not fits:
        rules.append(
            (
                "does-not-fit",
                ["long_context"],
                f"{f['corpus_tokens']:,} tokens of documents do not fit a budget of "
                f"{f['context_budget_tokens']:,} per call.",
            )
        )
    if f.get("steps_known") is True:
        rules.append(
            (
                "steps-known",
                AGENTS,
                "The steps are known, so a fixed path does the job: cheaper, faster and testable step by step.",
            )
        )
    if f.get("distinct_steps") == 1:
        rules.append(("one-step", ["workflow", "multi_agent"], "One step: there is nothing to chain, route or split."))
    if f.get("independent_subtasks") is False:
        rules.append(
            (
                "nothing-to-split",
                ["multi_agent"],
                "No parts that need their own context: subagents add hand-offs and cost.",
            )
        )
    if f.get("error_cost") == "high" and f.get("human_review") is False:
        rules.append(
            (
                "unreviewed-autonomy",
                ["single_agent", "multi_agent"],
                "A wrong result is expensive and no person checks it: the model may not choose its own actions.",
            )
        )
    if known("latency_budget_s", "seconds_per_call"):
        slow = [k for k, n in MIN_CALLS.items() if n * f["seconds_per_call"] > f["latency_budget_s"]]
        if slow:
            rules.append(
                (
                    "too-slow",
                    slow,
                    f"At {f['seconds_per_call']} s per call these need more than the {f['latency_budget_s']} s budget.",
                )
            )
    return rules


# fact -> options it could eliminate when known (the open facts the architect should ask about)
WOULD_DECIDE: dict[str, list[str]] = {
    "needs_language": ["no_llm", *LLM],
    "uses_documents": ["single_call", "long_context", "rag", "agentic_rag"],
    "live_state": ["single_call", "long_context", "rag"],
    "corpus_tokens": ["long_context"],
    "context_budget_tokens": ["long_context"],
    "steps_known": AGENTS,
    "distinct_steps": ["workflow", "multi_agent"],
    "independent_subtasks": ["multi_agent"],
    "error_cost": ["single_agent", "multi_agent"],
    "human_review": ["single_agent", "multi_agent"],
    "latency_budget_s": [k for k, n in MIN_CALLS.items() if n > 0],
    "seconds_per_call": [k for k, n in MIN_CALLS.items() if n > 0],
}


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
            "number": isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0,
            "level": value in LEVELS,
        }[kind]
        if not ok:
            errs.append(f"{key}: must be {'one of ' + ', '.join(LEVELS) if kind == 'level' else 'a ' + kind}")
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
        "facts": {k: facts.get(k) for k in FACTS},
        "min_calls": MIN_CALLS,
        "note": "Hard rules only. An open option is not a choice: weigh the open ones by predictability, "
        "cost of an error, observability, latency and cost, and climb above the lowest only for a named reason.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the hard rules of the AI pattern ladder to a brief's facts.")
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
