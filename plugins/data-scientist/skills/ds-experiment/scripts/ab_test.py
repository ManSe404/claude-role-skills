#!/usr/bin/env python3
"""Plan an A/B test, and read one so that a broken split stops the read-out and a win survives correction.

Usage: python3 ab_test.py plan --baseline 0.12 --mde 0.02 [--relative] [--kind proportion|mean] [--sd S]
                               [--alpha A] [--power P] [--metrics K] [--ratio R] [--daily-units N]
       python3 ab_test.py plan --baseline 0.12 --n-per-arm 4000 ...         (the smallest effect that sample can detect)
       python3 ab_test.py read FILE --variant COLUMN --control A --treatment B --unit COLUMN
                               --primary METRIC [--metrics METRIC,METRIC] [--guardrail METRIC:MARGIN ...]
                               [--lower-is-better METRIC,METRIC] [--expected-share 0.5] [--alpha 0.05]
                               [--srm-alpha 0.001] [--min-effect X] [--looks K] [--planned-n N] [--time COLUMN]

`read` takes CSV or JSON Lines with one row per randomised unit. A metric column of 0/1 (or true/false) is read as a
proportion, anything else as a mean. Everything else is in the read's order:

1. Sample ratio mismatch: a chi-square test of the arm counts against --expected-share. A p-value under --srm-alpha
   (the usual 0.001) means the split is broken, so the read-out stops: no metric is printed, the call is inconclusive.
   Units in both arms or repeated rows stop it too, because a unit is the thing that was randomised.
2. Metrics: per arm a Wilson or normal interval; treatment minus control, its interval and p-value (pooled
   two-proportion test or Welch). All of --metrics plus the primary form one family under Holm's correction: the
   family is every metric a ship could rest on. A list of one is not corrected.
3. Guardrails: METRIC:MARGIN, the most harm you accept in the metric's own units. Held means the whole interval of the
   harm lies under the margin; breached means it lies above; unclear otherwise. Harm uses the direction set by
   --lower-is-better.
4. Peeking: --looks says how often the result was read, and the true false-positive rate of that many reads; --time
   recomputes the primary metric per day from the start.
5. The call: ship, do not ship or inconclusive, from the corrected primary, the guardrails and --min-effect.

It prints columns, arm names and counts, never a unit or a row. A personal column is refused as a variant, a metric or a
time column. Read-only, standard library only, JSON on stdout. Numbers are the large-sample normal approximation,
fine at A/B test sizes; a metric under 100 units per arm is flagged.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# The other scripts of this pack are copies in the same folder.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_profile
import measure
import model_stats as ms

SMALL_ARM = 100
BOTH_ARMS_STOP = 0.01


def add_plan(sub: Any) -> None:
    plan = sub.add_parser("plan", help="sample size or minimum detectable effect")
    plan.add_argument("--kind", choices=("proportion", "mean"), default="proportion")
    plan.add_argument("--baseline", type=float, help="the control rate, or the control mean")
    plan.add_argument("--sd", type=float, help="standard deviation of a mean metric")
    plan.add_argument("--mde", type=float, help="the absolute difference to detect (or a share of the baseline)")
    plan.add_argument("--relative", action="store_true", help="--mde is a share of the baseline")
    plan.add_argument("--n-per-arm", type=int, help="instead of --mde: the sample available in the control arm")
    plan.add_argument("--alpha", type=float, default=0.05)
    plan.add_argument("--power", type=float, default=0.8)
    plan.add_argument("--metrics", type=int, default=1, help="how many metrics the ship can rest on")
    plan.add_argument("--ratio", type=float, default=1.0, help="treatment units per control unit")
    plan.add_argument("--daily-units", type=float, help="units entering the test per day")


def add_read(sub: Any) -> None:
    read = sub.add_parser("read", help="read out a finished test")
    read.add_argument("file", type=Path)
    read.add_argument("--variant", required=True)
    read.add_argument("--control", required=True)
    read.add_argument("--treatment", required=True)
    read.add_argument("--unit", required=True)
    read.add_argument("--primary", required=True)
    read.add_argument("--metrics", default="", help="more metrics a ship could rest on, comma separated")
    read.add_argument("--guardrail", action="append", default=[], help="METRIC:MARGIN, repeated")
    read.add_argument("--lower-is-better", default="", help="metrics where a fall is good, comma separated")
    read.add_argument("--expected-share", type=float, default=0.5, help="treatment's share of the units by design")
    read.add_argument("--alpha", type=float, default=0.05)
    read.add_argument("--srm-alpha", type=float, default=0.001)
    read.add_argument("--min-effect", type=float, help="smallest improvement of the primary worth shipping")
    read.add_argument("--looks", type=int, help="how many times the result was read before the end")
    read.add_argument("--planned-n", type=int, help="planned units per arm")
    read.add_argument("--time", help="date or time of the unit's entry, for the running view of the primary")
    read.add_argument("--max-rows", type=int, default=data_profile.MAX_ROWS)


def read_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan or read out an A/B test.")
    sub = parser.add_subparsers(dest="mode", required=True)
    add_plan(sub)
    add_read(sub)
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------- plan


def plan(args: argparse.Namespace) -> dict[str, Any]:
    if args.baseline is None:
        raise SystemExit("--baseline is required")
    if args.kind == "mean" and args.sd is None:
        raise SystemExit("--kind mean needs --sd")
    if args.kind == "proportion" and not 0 < args.baseline < 1:
        raise SystemExit("--baseline must be between 0 and 1 for a proportion")
    if (args.mde is None) == (args.n_per_arm is None):
        raise SystemExit("give either --mde or --n-per-arm")
    alpha = args.alpha / args.metrics
    result: dict[str, Any] = {
        "kind": args.kind,
        "baseline": args.baseline,
        "alpha": args.alpha,
        "alpha_per_metric": round(alpha, 6),
        "power": args.power,
        "metrics": args.metrics,
        "ratio_treatment_to_control": args.ratio,
    }
    if args.n_per_arm is not None:
        n = args.n_per_arm
        if args.kind == "proportion":
            mde = ms.mde_proportions(args.baseline, n, alpha, args.power, args.ratio)
        else:
            mde = ms.mde_means(args.sd, n, alpha, args.power, args.ratio)
        result["mde"] = {
            "absolute": None if mde is None else round(mde, 6),
            "relative": None if mde is None or args.baseline == 0 else round(mde / args.baseline, 6),
            "n_control": n,
            "n_treatment": int(n * args.ratio),
        }
    else:
        delta = args.mde * args.baseline if args.relative else args.mde
        if delta <= 0:
            raise SystemExit("--mde must be above zero")
        if args.kind == "proportion":
            if args.baseline + delta >= 1:
                raise SystemExit("baseline + mde must stay below 1")
            n_c, n_t = ms.sample_size_proportions(args.baseline, args.baseline + delta, alpha, args.power, args.ratio)
        else:
            n_c, n_t = ms.sample_size_means(args.sd, delta, alpha, args.power, args.ratio)
        result["sample"] = {
            "absolute_difference": round(delta, 6),
            "relative_difference": None if args.baseline == 0 else round(delta / args.baseline, 6),
            "n_control": n_c,
            "n_treatment": n_t,
            "n_total": n_c + n_t,
        }
    sample = result.get("sample")
    if args.daily_units and sample:
        result["days_at_daily_units"] = round(sample["n_total"] / args.daily_units, 1)
    result["note"] = (
        "Normal approximation. With several metrics the plan splits alpha between them. Decide the number of looks "
        "before launch: reading a running test and stopping on the first significant look inflates false positives."
    )
    return result


# ---------------------------------------------------------------------------- read


def parse_metric(cell: str | None) -> float | None:
    """1 or 0 for a boolean cell, a number otherwise, None when empty."""
    if cell is None:
        return None
    binary = ms.parse_binary(cell)
    return (1.0 if binary else 0.0) if binary is not None else ms.to_float(cell)


def srm_check(counts: dict[str, int], expected: dict[str, float], alpha: float) -> dict[str, Any]:
    total = sum(counts.values())
    statistic = sum((counts[arm] - total * share) ** 2 / (total * share) for arm, share in expected.items())
    p = ms.chi_square_sf(statistic, len(expected) - 1)
    return {
        "observed": counts,
        "expected_share": expected,
        "chi_square": round(statistic, 6),
        "df": len(expected) - 1,
        "p_value": round(p, 8),
        "threshold": alpha,
        "mismatch": p < alpha,
    }


def stats_of(values: list[float], binary: bool, confidence: float) -> dict[str, Any]:
    n = len(values)
    mean = sum(values) / n if n else 0.0
    if binary:
        successes = int(sum(values))
        low, high = ms.wilson(successes, n, confidence)
        return {"n": n, "successes": successes, "rate": round(mean, 6), "low": round(low, 6), "high": round(high, 6)}
    var = ms.variance(values)
    margin = ms.z_for(confidence) * (var / n) ** 0.5 if n else 0.0
    return {
        "n": n,
        "mean": round(mean, 6),
        "sd": round(var**0.5, 6),
        "low": round(mean - margin, 6),
        "high": round(mean + margin, 6),
    }


def compare_metric(
    name: str,
    role: str,
    direction: str,
    arms: dict[str, list[float]],
    control: str,
    treatment: str,
    confidence: float,
) -> dict[str, Any]:
    control_values, treatment_values = arms[control], arms[treatment]
    binary = all(v in (0.0, 1.0) for v in control_values + treatment_values)
    n_c, n_t = len(control_values), len(treatment_values)
    if binary:
        comparison = ms.two_proportions(int(sum(control_values)), n_c, int(sum(treatment_values)), n_t, confidence)
    else:
        comparison = ms.welch(
            sum(control_values) / n_c,
            ms.variance(control_values),
            n_c,
            sum(treatment_values) / n_t,
            ms.variance(treatment_values),
            n_t,
            confidence,
        )
    return {
        "se": round(comparison.se, 8),
        "metric": name,
        "role": role,
        "kind": "proportion" if binary else "mean",
        "direction": direction,
        "control": stats_of(control_values, binary, confidence),
        "treatment": stats_of(treatment_values, binary, confidence),
        "difference": round(comparison.difference, 6),
        "low": round(comparison.low, 6),
        "high": round(comparison.high, 6),
        "z": round(comparison.z, 4),
        "p_value": round(comparison.p_value, 6),
        "small_sample": n_c < SMALL_ARM or n_t < SMALL_ARM,
    }


def improvement_interval(metric: dict[str, Any], low: float, high: float) -> tuple[float, float]:
    """Interval of the improvement, positive being good."""
    return (low, high) if metric["direction"] == "higher" else (-high, -low)


def apply_correction(metrics: list[dict[str, Any]], alpha: float) -> None:
    """Holm over the family, plus the Bonferroni interval for the same family, for an interval that matches the test."""
    m = len(metrics)
    adjusted = ms.holm([row["p_value"] for row in metrics])
    z = ms.z_for(1 - alpha / m)
    for row, adj in zip(metrics, adjusted, strict=True):
        margin = z * row["se"]
        row["adjusted_p"] = round(adj, 6)
        row["significant_uncorrected"] = row["p_value"] < alpha
        row["significant_corrected"] = adj < alpha
        row["corrected_low"] = round(row["difference"] - margin, 6)
        row["corrected_high"] = round(row["difference"] + margin, 6)
        row["correction"] = f"Holm over {m} metric(s)"


def guardrail_status(metric: dict[str, Any], margin: float) -> dict[str, Any]:
    """Harm is the difference in the bad direction; the margin is the largest harm you accept."""
    sign = 1.0 if metric["direction"] == "lower" else -1.0
    harm = sign * metric["difference"]
    harm_low, harm_high = sorted((sign * metric["low"], sign * metric["high"]))
    status = "unclear"
    if harm_high < margin:
        status = "held"
    elif harm_low > margin:
        status = "breached"
    return {
        **metric,
        "margin": margin,
        "harm": round(harm, 6),
        "harm_low": round(harm_low, 6),
        "harm_high": round(harm_high, 6),
        "status": status,
    }


def decide(
    primary: dict[str, Any],
    guardrails: list[dict[str, Any]],
    min_effect: float | None,
) -> dict[str, Any]:
    """The call from the corrected primary, the guardrails and the smallest effect worth shipping."""
    because: list[str] = []
    _, high = improvement_interval(primary, primary["corrected_low"], primary["corrected_high"])
    effect = primary["difference"] if primary["direction"] == "higher" else -primary["difference"]
    breached = [g["metric"] for g in guardrails if g["status"] == "breached"]
    unclear = [g["metric"] for g in guardrails if g["status"] == "unclear"]
    significant = primary["significant_corrected"]
    if breached:
        because.append(f"guardrail breached: {', '.join(breached)}")
        return {"call": "do not ship", "because": because}
    if significant and effect < 0:
        because.append(f"{primary['metric']} is significantly worse after correction")
        return {"call": "do not ship", "because": because}
    if significant:
        if min_effect is not None and high < min_effect:
            because.append(f"the whole corrected interval of {primary['metric']} is under the minimum effect")
            return {"call": "do not ship", "because": because}
        if unclear:
            because.append(f"guardrail not settled: {', '.join(unclear)}")
            return {"call": "inconclusive", "because": because}
        if min_effect is not None and effect < min_effect:
            because.append(f"{primary['metric']} improved, but the estimate is under the minimum effect")
            return {"call": "inconclusive", "because": because}
        because.append(f"{primary['metric']} improved and every guardrail held")
        return {"call": "ship", "because": because}
    if min_effect is not None and high < min_effect:
        because.append(f"the corrected interval of {primary['metric']} excludes the minimum effect")
        return {"call": "do not ship", "because": because}
    because.append(f"{primary['metric']} is not significant after correction")
    return {"call": "inconclusive", "because": because}


def running_view(
    rows: list[measure.Row],
    variant: str,
    control: str,
    treatment: str,
    time_column: str,
    metric: str,
    alpha: float,
) -> dict[str, Any]:
    """The primary metric recomputed per calendar day from the start, the way a dashboard would have shown it."""
    days: dict[str, list[tuple[str, float]]] = {}
    for row in rows:
        moment = measure.day(row[time_column])
        value = parse_metric(row[metric])
        if moment is None or value is None or row[variant] not in (control, treatment):
            continue
        days.setdefault(moment.isoformat(), []).append((row[variant] or "", value))
    control_values: list[float] = []
    treatment_values: list[float] = []
    points = []
    for name in sorted(days):
        for arm, value in days[name]:
            (control_values if arm == control else treatment_values).append(value)
        if not control_values or not treatment_values:
            continue
        binary = all(v in (0.0, 1.0) for v in control_values + treatment_values)
        if binary:
            comparison = ms.two_proportions(
                int(sum(control_values)), len(control_values), int(sum(treatment_values)), len(treatment_values)
            )
        else:
            comparison = ms.welch(
                sum(control_values) / len(control_values),
                ms.variance(control_values),
                len(control_values),
                sum(treatment_values) / len(treatment_values),
                ms.variance(treatment_values),
                len(treatment_values),
            )
        points.append(
            {
                "day": name,
                "units": len(control_values) + len(treatment_values),
                "difference": round(comparison.difference, 6),
                "p_value": round(comparison.p_value, 6),
                "significant": comparison.p_value < alpha,
            }
        )
    significant = [p["day"] for p in points if p["significant"]]
    return {
        "metric": metric,
        "days": points,
        "days_significant": len(significant),
        "first_significant_day": significant[0] if significant else None,
        "significant_on_the_last_day": bool(points and points[-1]["significant"]),
    }


def read_out(args: argparse.Namespace) -> dict[str, Any]:
    table = measure.load(args.file, args.max_rows)
    secondary = [m.strip() for m in args.metrics.split(",") if m.strip() and m.strip() != args.primary]
    guardrail_specs: list[tuple[str, float]] = []
    for spec in args.guardrail:
        name, _, margin = spec.partition(":")
        if not margin:
            raise SystemExit(f"--guardrail {spec}: give METRIC:MARGIN, the largest harm you accept")
        guardrail_specs.append((name.strip(), float(margin)))
    if args.time:
        measure.check_public(table, [args.time], "the time column")
    measure.check_public(table, [args.variant], "the variant column")
    measure.check_columns(table, [args.unit])
    family = [args.primary, *secondary]
    all_metrics = family + [name for name, _ in guardrail_specs]
    for metric in all_metrics:
        measure.check_public(table, [metric], "a metric")
    lower_better = {m.strip() for m in args.lower_is_better.split(",") if m.strip()}
    counts = Counter(row[args.variant] for row in table.rows)
    arms = sorted(arm for arm in counts if arm is not None)
    for arm in (args.control, args.treatment):
        if arm not in counts:
            raise SystemExit(f"no rows with {args.variant} = {arm}")
    expected = {args.control: 1 - args.expected_share, args.treatment: args.expected_share}
    observed = {args.control: counts[args.control], args.treatment: counts[args.treatment]}
    rows_in_test = [row for row in table.rows if row[args.variant] in (args.control, args.treatment)]
    unit_counts = Counter(row[args.unit] for row in rows_in_test)
    repeated_units = sum(1 for c in unit_counts.values() if c > 1)
    arms_of_unit: dict[str | None, set[str | None]] = {}
    for row in rows_in_test:
        arms_of_unit.setdefault(row[args.unit], set()).add(row[args.variant])
    both = sum(1 for seen in arms_of_unit.values() if len(seen) > 1)
    srm = srm_check(observed, expected, args.srm_alpha)
    checks: dict[str, Any] = {
        "rows_read": len(table.rows),
        "rows_outside_the_two_arms": len(table.rows) - len(rows_in_test),
        "other_arms_seen": [a for a in arms if a not in (args.control, args.treatment)],
        "repeated_units": repeated_units,
        "units_in_both_arms": both,
        "personal_columns_in_file": sorted(table.personal),
    }
    result: dict[str, Any] = {
        "control": args.control,
        "treatment": args.treatment,
        "sample_ratio": srm,
        "checks": checks,
        "stopped": None,
        "metrics": None,
        "guardrails": None,
        "peeking": None,
        "decision": None,
    }
    stop_reasons = []
    if srm["mismatch"]:
        stop_reasons.append(
            f"sample ratio mismatch: observed {observed[args.control]} vs {observed[args.treatment]}, chi-square "
            f"{srm['chi_square']}, p {srm['p_value']}, under {args.srm_alpha}"
        )
    if repeated_units:
        stop_reasons.append(
            f"{repeated_units} units have more than one row: the file is not one row per randomised unit"
        )
    if both / max(1, len(arms_of_unit)) > BOTH_ARMS_STOP:
        stop_reasons.append(f"{both} units appear in both arms: the assignment was not honoured")
    if stop_reasons:
        result["stopped"] = "; ".join(stop_reasons)
        result["decision"] = {
            "call": "inconclusive",
            "because": stop_reasons,
            "note": "No metric is printed for a broken split. Find the cause and re-run, or restrict to a clean "
            "period and re-check the split there. Reading the effects anyway would read a biased comparison.",
        }
        return result
    if both:
        checks["warning"] = f"{both} units appear in both arms (under {BOTH_ARMS_STOP:.0%}): the effect is diluted."
    arms_data: dict[str, dict[str, list[float]]] = {m: {args.control: [], args.treatment: []} for m in all_metrics}
    missing = {m: {args.control: 0, args.treatment: 0} for m in all_metrics}
    for row in rows_in_test:
        arm = row[args.variant] or ""
        for metric in all_metrics:
            value = parse_metric(row[metric])
            if value is None:
                missing[metric][arm] += 1
            else:
                arms_data[metric][arm].append(value)
    empty = [m for m in all_metrics if not arms_data[m][args.control] or not arms_data[m][args.treatment]]
    if empty:
        raise SystemExit(f"metric with no values in an arm: {', '.join(empty)}")
    confidence = 1 - args.alpha

    def direction(metric: str) -> str:
        return "lower" if metric in lower_better else "higher"

    metrics = [
        compare_metric(
            m,
            "primary" if m == args.primary else "secondary",
            direction(m),
            arms_data[m],
            args.control,
            args.treatment,
            confidence,
        )
        for m in family
    ]
    apply_correction(metrics, args.alpha)
    for entry in metrics:
        entry["missing"] = missing[entry["metric"]]
    guardrails = [
        guardrail_status(
            compare_metric(
                name, "guardrail", direction(name), arms_data[name], args.control, args.treatment, confidence
            ),
            margin,
        )
        for name, margin in guardrail_specs
    ]
    primary = next(m for m in metrics if m["metric"] == args.primary)
    peeking: dict[str, Any] = {"looks": args.looks}
    if args.looks is not None:
        peeking["true_false_positive_rate_at_nominal_5_percent"] = round(ms.peeking_false_positive(args.looks), 3)
    if args.planned_n is not None:
        n = min(primary["control"]["n"], primary["treatment"]["n"])
        peeking["planned_n_per_arm"] = args.planned_n
        peeking["n_per_arm"] = n
        peeking["reached_plan"] = n >= args.planned_n
    if args.time:
        peeking["running_view"] = running_view(
            rows_in_test, args.variant, args.control, args.treatment, args.time, args.primary, args.alpha
        )
    peeking["note"] = (
        "A p-value below alpha on some day of a running test is expected by chance far more often than alpha. "
        "Only a test read at its planned size, or with a sequential design, supports a claim of significance."
    )
    achieved = (
        ms.mde_proportions(
            primary["control"].get("rate", 0.0),
            primary["control"]["n"],
            args.alpha / len(metrics),
            ratio=primary["treatment"]["n"] / primary["control"]["n"],
        )
        if primary["kind"] == "proportion"
        else ms.mde_means(
            primary["control"]["sd"],
            primary["control"]["n"],
            args.alpha / len(metrics),
            ratio=primary["treatment"]["n"] / primary["control"]["n"],
        )
    )
    result["metrics"] = metrics
    result["guardrails"] = guardrails
    result["peeking"] = peeking
    result["achieved_mde"] = None if achieved is None else round(achieved, 6)
    result["decision"] = decide(primary, guardrails, args.min_effect)
    small = [m["metric"] for m in metrics + guardrails if m["small_sample"]]
    if small:
        result["notes"] = [
            f"Under {SMALL_ARM} units in an arm: the normal approximation is not safe for {', '.join(small)}."
        ]
    return result


def main(argv: list[str] | None = None) -> int:
    args = read_args(argv)
    result = plan(args) if args.mode == "plan" else read_out(args)
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
