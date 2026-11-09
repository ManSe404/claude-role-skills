#!/usr/bin/env python3
"""Cost and latency of an AI design at its real volume, from a price table that carries its date.

Usage: python3 cost_model.py DESIGN.json --prices PRICES.json [--today 2026-11-08] [--max-age-days 90]

DESIGN.json describes one or more variants of the same design:

    {"requests_per_day": 3000, "days_per_month": 30,
     "fx": {"currency": "EUR", "per_price_unit": 0.86, "as_of": "2026-11-07", "source": "..."},   (optional)
     "variants": [{"id": "azure", "label": "Azure",
        "steps": [{"name": "route", "model": "small", "calls": 1, "input_tokens": 600, "output_tokens": 20,
                   "cached_share": 0.8, "share": 1.0, "latency_s": 0.6, "group": "a"}],
        "paths": [{"name": "how-to", "steps": ["route", "answer"]}],
        "fixed_monthly": [{"name": "vector store", "amount": 120, "source": "...", "as_of": "..."}]}]}

`share` is the fraction of requests that run the step (a router sends some requests one way),
`calls` how often the step runs for one of them. A step without a model (an API call, a search)
adds latency and no token cost. Steps with the same `group` in a path run in
parallel. The cost of one call is input tokens at the input price, the cached share at the
cached-input price, and output tokens at the output price.

PRICES.json is the price table: {"currency", "as_of", "source", "models": {name: {"input_per_mtok",
"output_per_mtok", "cached_input_per_mtok"}}}; a model may carry its own as_of and source. Prices
are never built in: a model missing from the table is an error, and a table older than
--max-age-days is flagged. A table marked "example": true is flagged on every number.
Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

PER = 1_000_000


def _num(obj: dict[str, Any], key: str, where: str, errs: list[str], *, default: float | None = None) -> float:
    value = obj.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        errs.append(f"{where}.{key}: must be a number >= 0")
        return 0.0
    return float(value)


def _date(value: Any, where: str, errs: list[str]) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        errs.append(f"{where}: must be a date, YYYY-MM-DD")
        return None


def check_prices(prices: Any) -> list[str]:
    if not isinstance(prices, dict) or not isinstance(prices.get("models"), dict):
        return ["prices: must be an object with a models table"]
    errs: list[str] = []
    for key in ("currency", "source"):
        if not isinstance(prices.get(key), str) or not prices[key]:
            errs.append(f"prices.{key}: missing; every price needs its currency and where it came from")
    _date(prices.get("as_of"), "prices.as_of", errs)
    for name, entry in prices["models"].items():
        where = f"prices.models.{name}"
        if not isinstance(entry, dict):
            errs.append(f"{where}: must be an object")
            continue
        for key in ("input_per_mtok", "output_per_mtok"):
            _num(entry, key, where, errs)
        if "cached_input_per_mtok" in entry:
            _num(entry, "cached_input_per_mtok", where, errs)
        if "as_of" in entry:
            _date(entry["as_of"], f"{where}.as_of", errs)
    return errs


def check_design(design: Any, prices: dict[str, Any]) -> list[str]:
    if not isinstance(design, dict):
        return ["design: must be a JSON object"]
    errs: list[str] = []
    _num(design, "requests_per_day", "design", errs)
    _num(design, "days_per_month", "design", errs, default=30)
    fx = design.get("fx")
    if fx is not None:
        if not isinstance(fx, dict) or not isinstance(fx.get("currency"), str) or not fx.get("source"):
            errs.append("design.fx: needs currency, per_price_unit, as_of and source")
        else:
            _num(fx, "per_price_unit", "design.fx", errs)
            _date(fx.get("as_of"), "design.fx.as_of", errs)
    variants = design.get("variants")
    if not isinstance(variants, list) or not variants:
        return [*errs, "design.variants: at least one variant"]
    for i, var in enumerate(variants):
        vpath = f"design.variants[{i}]"
        if not isinstance(var, dict) or not isinstance(var.get("id"), str):
            errs.append(f"{vpath}: must be an object with an id")
            continue
        names = set()
        for j, step in enumerate(var.get("steps", [])):
            spath = f"{vpath}.steps[{j}]"
            if not isinstance(step, dict) or not isinstance(step.get("name"), str):
                errs.append(f"{spath}: must be an object with a name")
                continue
            names.add(step["name"])
            if step.get("model") is not None and step["model"] not in prices["models"]:
                errs.append(f"{spath}.model: {step['model']!r} is not in the price table")
            needed = (
                None if step.get("model") is not None else 0
            )  # a step without a model (an API call) costs no tokens
            for key, default in (("calls", 1), ("input_tokens", needed), ("output_tokens", needed), ("latency_s", 0)):
                _num(step, key, spath, errs, default=default)
            for key, default in (("cached_share", 0), ("share", 1)):
                if not 0 <= _num(step, key, spath, errs, default=default) <= 1:
                    errs.append(f"{spath}.{key}: must be between 0 and 1")
        for j, path in enumerate(var.get("paths", [])):
            for name in path.get("steps", []) if isinstance(path, dict) else []:
                if name not in names:
                    errs.append(f"{vpath}.paths[{j}]: unknown step {name!r}")
        for j, item in enumerate(var.get("fixed_monthly", [])):
            fpath = f"{vpath}.fixed_monthly[{j}]"
            if not isinstance(item, dict) or not item.get("name") or not item.get("source"):
                errs.append(f"{fpath}: needs name, amount and source")
            else:
                _num(item, "amount", fpath, errs)
    return errs


def _call_cost(step: dict[str, Any], price: dict[str, Any]) -> float:
    inp = float(step["input_tokens"])
    cached = inp * float(step.get("cached_share", 0))
    cached_price = float(price.get("cached_input_per_mtok", price["input_per_mtok"]))
    return (
        (inp - cached) * float(price["input_per_mtok"])
        + cached * cached_price
        + float(step["output_tokens"]) * float(price["output_per_mtok"])
    ) / PER


def _latency(steps: list[dict[str, Any]]) -> float:
    """Steps in order; consecutive steps that share a group run in parallel, so the group takes its slowest."""
    total, group, slowest = 0.0, None, 0.0
    for step in steps:
        seconds = float(step.get("latency_s", 0)) * float(step.get("calls", 1))
        if step.get("group") is not None and step.get("group") == group:
            slowest = max(slowest, seconds)
            continue
        total += slowest
        group, slowest = step.get("group"), seconds
    return round(total + slowest, 3)


def model(design: dict[str, Any], prices: dict[str, Any], today: date, max_age_days: int) -> dict[str, Any]:
    per_day = float(design["requests_per_day"])
    days = float(design.get("days_per_month", 30))
    fx = design.get("fx")
    warnings: list[str] = []
    if prices.get("example"):
        warnings.append("EXAMPLE PRICES: the table is marked as an example; replace it before quoting any number.")
    used: dict[str, dict[str, Any]] = {}
    variants = []
    for var in design["variants"]:
        steps = []
        per_request = 0.0
        for step in var.get("steps", []):
            one = 0.0
            if step.get("model") is not None:
                price = prices["models"][step["model"]]
                one = _call_cost(step, price)
                as_of = price.get("as_of", prices["as_of"])
                used[step["model"]] = {"as_of": as_of, "source": price.get("source", prices["source"])}
            cost = one * float(step.get("calls", 1)) * float(step.get("share", 1))
            per_request += cost
            steps.append(
                {
                    "name": step["name"],
                    "model": step.get("model"),
                    "cost_per_call": round(one, 6),
                    "cost_per_request": round(cost, 6),
                    "cost_per_month": round(cost * per_day * days, 2),
                    "tokens_per_month": round(
                        (float(step.get("input_tokens", 0)) + float(step.get("output_tokens", 0)))
                        * float(step.get("calls", 1))
                        * float(step.get("share", 1))
                        * per_day
                        * days
                    ),
                }
            )
        fixed = [
            {"name": f["name"], "amount": float(f["amount"]), "source": f["source"], "as_of": f.get("as_of")}
            for f in var.get("fixed_monthly", [])
        ]
        model_month = per_request * per_day * days
        total = model_month + sum(f["amount"] for f in fixed)
        for step in steps:
            step["share_of_total"] = round(step["cost_per_month"] / total, 3) if total else 0.0
        by_name = {s["name"]: s for s in var.get("steps", [])}
        paths = var.get("paths") or [{"name": "all steps", "steps": list(by_name)}]
        result = {
            "id": var["id"],
            "label": var.get("label", var["id"]),
            "steps": steps,
            "fixed_monthly": fixed,
            "per_request": round(per_request, 6),
            "models_per_month": round(model_month, 2),
            "total_per_month": round(total, 2),
            "latency_s": [{"path": p["name"], "seconds": _latency([by_name[n] for n in p["steps"]])} for p in paths],
        }
        if fx:
            rate = float(fx["per_price_unit"])
            result["total_per_month_" + fx["currency"].lower()] = round(total * rate, 2)
        variants.append(result)
    for name, info in used.items():
        age = (today - date.fromisoformat(info["as_of"])).days
        info["age_days"] = age
        if age > max_age_days:
            warnings.append(f"{name}: the price is {age} days old (as of {info['as_of']}); check it before quoting.")
    for var in design["variants"]:
        for f in var.get("fixed_monthly", []):
            if not f.get("as_of"):
                warnings.append(f"{var['id']}: fixed cost {f['name']!r} has no as_of date.")
    return {
        "currency": prices["currency"],
        "requests_per_day": per_day,
        "days_per_month": days,
        "fx": fx,
        "variants": variants,
        "prices_used": used,
        "warnings": warnings,
        "note": "Token counts and latencies are the design's assumptions; prices are the table's. Say which is which.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cost and latency of an AI design from a dated price table.")
    parser.add_argument("design", type=Path)
    parser.add_argument("--prices", type=Path, required=True, help="the price table, with as_of and source")
    parser.add_argument("--today", default=date.today().isoformat(), help="the date to age the prices against")
    parser.add_argument("--max-age-days", type=int, default=90)
    args = parser.parse_args(argv)
    try:
        prices = json.loads(args.prices.read_text(encoding="utf-8"))
        design = json.loads(args.design.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read the input: {exc}", file=sys.stderr)
        return 2
    errors = check_prices(prices)
    if not errors:
        errors = check_design(design, prices)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    result = model(design, prices, date.fromisoformat(args.today), args.max_age_days)
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
