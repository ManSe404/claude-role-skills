#!/usr/bin/env python3
"""Apply the hard rules of the modelling ladder to the facts of a brief, before anything is trained.

Usage: python3 frame_rules.py FACTS.json      (or - for stdin)
       python3 frame_rules.py --facts          (list the facts it reads, with what each one decides)

The ladder, simplest first: a lookup or business rule, a simple score, a linear or logistic model, gradient-boosted
trees, deep learning. Each rule eliminates options that cannot meet a fact of the brief. The script never chooses: it
prints which options are still open, the lowest open rung, the baseline that must be beaten, what the two trivial
policies cost, and the facts that are unknown but would eliminate something. If the job is really reading or writing
free text, every rung goes and the answer is the `ai-pattern` skill.

A fact that is missing or null decides nothing; it is listed under open_facts instead. Read-only, standard library
only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

OPTIONS = [
    ("lookup_rule", "A lookup or a business rule"),
    ("simple_score", "A simple score: a few weighted signals"),
    ("linear", "A linear or logistic model"),
    ("gbt", "Gradient-boosted trees"),
    ("deep", "Deep learning"),
]
ALL = [key for key, _ in OPTIONS]
LEARNED = ["linear", "gbt", "deep"]
ABOVE_RULE = ["simple_score", *LEARNED]
# Below 10 positive cases per feature a logistic fit is unstable (Peduzzi et al., 1996).
EVENTS_PER_FEATURE = 10
# Rules of thumb, stated so a reader can argue with them: boosted trees need a few hundred positive cases to split on.
MIN_MINORITY_FOR_TREES = 500
MIN_ROWS_FOR_DEEP = 1000

TASKS = ("classification", "regression", "ranking", "forecast")
INPUTS = ("tabular", "unstructured")
FACTS: dict[str, tuple[str, str]] = {
    "decision_named": ("bool", "a named decision changes depending on the prediction"),
    "is_language_task": ("bool", "the job reads or writes free text or conversation, so it is an LLM question"),
    "task": ("task", "classification, regression, ranking or forecast"),
    "label_exists": ("bool", "history holds the outcome for past cases"),
    "label_delay_days": ("int", "days between the prediction and the moment its label is known"),
    "feedback_budget_days": ("int", "the longest the team can wait for an outcome to still act on it or retrain"),
    "signals_known_at_decision": ("bool", "every input the model would use is known at the moment of the decision"),
    "rule_meets_bar": ("bool", "measured on history, a simple rule already meets the acceptance bar"),
    "input_kind": ("input", "tabular (fields in rows) or unstructured (images, audio, raw signals)"),
    "labelled_rows": ("int", "rows in history with a usable label"),
    "minority_rows": ("int", "rows of the rarer class in history"),
    "candidate_features": ("int", "how many features the model would need"),
    "must_recompute_by_hand": ("bool", "a regulator or customer must be able to recompute a decision by hand"),
    "serving_can_call_model": ("bool", "production can call a trained model at decision time, not only a SQL formula"),
    "decisions_per_year": ("int", "how many cases are decided in a year"),
    "base_rate": ("rate", "share of cases that are positive"),
    "cost_false_positive": ("number", "what it costs to act when nothing would have happened"),
    "cost_false_negative": ("number", "what it costs not to act when it would have happened"),
    "learned_model_cost_per_year": ("number", "building, serving, monitoring and retraining a learned model, per year"),
}
KINDS = {"task": TASKS, "input": INPUTS}


def _rules(f: dict[str, Any]) -> list[tuple[str, list[str], str]]:
    """Every rule that fires, as (name, options it eliminates, why). A rule whose facts are unknown does not fire."""
    rules: list[tuple[str, list[str], str]] = []

    def known(*names: str) -> bool:
        return all(f.get(n) is not None for n in names)

    if f.get("decision_named") is False:
        rules.append(("no-decision", ALL, "No decision changes with the prediction: that is a report, not a model."))
    if f.get("is_language_task") is True:
        rules.append(("language-task", ALL, "The job reads or writes free text: use ai-pattern, not this ladder."))
    if f.get("signals_known_at_decision") is False:
        rules.append(
            ("signals-not-known", ALL, "The inputs are not known when the decision is made, whatever the method.")
        )
    if f.get("label_exists") is False:
        rules.append(("no-label", LEARNED, "No outcome in history: a learned model has nothing to learn from."))
    if known("label_delay_days", "feedback_budget_days") and f["label_delay_days"] > f["feedback_budget_days"]:
        rules.append(
            (
                "label-too-late",
                LEARNED,
                f"The label takes {f['label_delay_days']} days, longer than the {f['feedback_budget_days']} "
                "days the team can wait.",
            )
        )
    if f.get("rule_meets_bar") is True:
        rules.append(("rule-meets-bar", ABOVE_RULE, "A simple rule already meets the bar on history."))
    if f.get("rule_meets_bar") is False:
        rules.append(("rule-misses-bar", ["lookup_rule"], "Measured on history, a simple rule does not reach the bar."))
    if f.get("input_kind") == "unstructured":
        rules.append(
            (
                "unstructured-input",
                ["lookup_rule", "simple_score", "linear"],
                "Images, audio or raw signals carry no fields a rule or a linear model could use directly.",
            )
        )
    if f.get("input_kind") == "tabular":
        rules.append(("tabular-input", ["deep"], "On fields in rows, trees match or beat deep networks for less."))
    if (
        known("minority_rows", "candidate_features")
        and f["minority_rows"] < EVENTS_PER_FEATURE * f["candidate_features"]
    ):
        rules.append(
            (
                "too-few-events-for-linear",
                ["linear"],
                f"{f['minority_rows']} positive cases for {f['candidate_features']} features is under "
                f"{EVENTS_PER_FEATURE} per feature: cut features or stay simpler.",
            )
        )
    if known("minority_rows") and f["minority_rows"] < MIN_MINORITY_FOR_TREES:
        rules.append(
            (
                "too-few-events-for-trees",
                ["gbt"],
                f"{f['minority_rows']} positive cases is under {MIN_MINORITY_FOR_TREES}: boosted trees would overfit.",
            )
        )
    if known("labelled_rows") and f["labelled_rows"] < MIN_ROWS_FOR_DEEP:
        rules.append(
            ("too-few-rows-for-deep", ["deep"], f"{f['labelled_rows']} labelled rows cannot train a deep network.")
        )
    if f.get("must_recompute_by_hand") is True:
        rules.append(
            ("recompute-by-hand", ["gbt", "deep"], "A person must recompute each decision: trees do not allow it.")
        )
    if f.get("serving_can_call_model") is False:
        rules.append(
            (
                "no-model-serving",
                ["gbt", "deep"],
                "Production only evaluates a formula: a rule, a score or a linear model fits, tree ensembles do not.",
            )
        )
    ceiling = _ceiling(f)
    if ceiling is not None and known("learned_model_cost_per_year") and ceiling < f["learned_model_cost_per_year"]:
        rules.append(
            (
                "ceiling-below-cost",
                LEARNED,
                f"A perfect model would save at most {ceiling:,.0f} a year, less than the "
                f"{f['learned_model_cost_per_year']:,.0f} a learned model costs.",
            )
        )
    return rules


# fact -> options it could eliminate when known (the open facts the frame should settle)
WOULD_DECIDE: dict[str, list[str]] = {
    "decision_named": ALL,
    "is_language_task": ALL,
    "signals_known_at_decision": ALL,
    "label_exists": LEARNED,
    "label_delay_days": LEARNED,
    "feedback_budget_days": LEARNED,
    "rule_meets_bar": ["lookup_rule", *ABOVE_RULE],
    "input_kind": ["lookup_rule", "simple_score", "linear", "deep"],
    "minority_rows": ["linear", "gbt"],
    "candidate_features": ["linear"],
    "labelled_rows": ["deep"],
    "must_recompute_by_hand": ["gbt", "deep"],
    "serving_can_call_model": ["gbt", "deep"],
    "decisions_per_year": LEARNED,
    "base_rate": LEARNED,
    "cost_false_positive": LEARNED,
    "cost_false_negative": LEARNED,
    "learned_model_cost_per_year": LEARNED,
}


def _ceiling(f: dict[str, Any]) -> float | None:
    """The most a perfect model could save in a year over the cheaper of the two trivial policies."""
    names = ("decisions_per_year", "base_rate", "cost_false_positive", "cost_false_negative")
    if any(f.get(n) is None for n in names):
        return None
    return float(
        f["decisions_per_year"]
        * min(f["base_rate"] * f["cost_false_negative"], (1 - f["base_rate"]) * f["cost_false_positive"])
    )


def economics(f: dict[str, Any]) -> dict[str, Any] | None:
    """What the two trivial policies cost per case, the break-even probability and the ceiling of a perfect model."""
    names = ("base_rate", "cost_false_positive", "cost_false_negative")
    if any(f.get(n) is None for n in names):
        return None
    rate, fp, fn = f["base_rate"], f["cost_false_positive"], f["cost_false_negative"]
    nobody = rate * fn
    everyone = (1 - rate) * fp
    result: dict[str, Any] = {
        "cost_per_case_act_on_nobody": round(nobody, 4),
        "cost_per_case_act_on_everyone": round(everyone, 4),
        "cheapest_trivial_policy": "act on nobody" if nobody <= everyone else "act on everyone",
        "cheapest_trivial_cost_per_case": round(min(nobody, everyone), 4),
        "break_even_probability": round(fp / (fp + fn), 6),
    }
    ceiling = _ceiling(f)
    if ceiling is not None:
        result["ceiling_per_year"] = round(ceiling, 2)
    return result


def baseline(f: dict[str, Any]) -> str:
    """The cheapest honest thing a model has to beat, by the kind of task."""
    task = f.get("task")
    if task == "regression":
        return "the training mean (or median) of the target, for every row"
    if task == "forecast":
        return "the last value, or the same period last year if the series is seasonal"
    if task == "ranking":
        return "sorting by the single strongest signal"
    return "the base rate as a score, and the cheaper of acting on everyone or on nobody"


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
            "number": isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0,
            "rate": isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1,
            "task": value in TASKS,
            "input": value in INPUTS,
        }[kind]
        if not ok:
            allowed = f"one of {', '.join(KINDS[kind])}" if kind in KINDS else f"a {kind}"
            errs.append(f"{key}: must be {allowed}")
    return errs


def decide(facts: dict[str, Any]) -> dict[str, Any]:
    by_option: dict[str, list[dict[str, str]]] = {key: [] for key, _ in OPTIONS}
    fired = _rules(facts)
    for name, eliminated, why in fired:
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
    use_instead = None
    if facts.get("is_language_task") is True:
        use_instead = {"skill": "ai-pattern", "why": "The job reads or writes free text, so it is an LLM question."}
    return {
        "options": options,
        "open": still_open,
        "lowest_open": still_open[0] if still_open else None,
        "use_instead": use_instead,
        "baseline_to_beat": baseline(facts),
        "economics": economics(facts),
        "open_facts": open_facts,
        "facts": {k: facts.get(k) for k in FACTS},
        "note": "Hard rules only. An open option is not a choice: the lowest open rung is the default, and climbing "
        "above it takes a reason named from the brief. Thresholds in the rules are rules of thumb, stated so they "
        "can be argued with.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the hard rules of the modelling ladder to a brief's facts.")
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
