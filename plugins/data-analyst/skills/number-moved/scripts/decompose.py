#!/usr/bin/env python3
"""Why did this number change? Rule out data problems, then split the change into volume, mix and rate exactly.

Usage: python3 decompose.py DATA --date DATE_COLUMN --a FROM:TO --b FROM:TO --value COLUMN [--volume COLUMN]
                             --by COLUMN [--by COLUMN ...]
                             [--filter column=value ...] [--dedupe KEY[,KEY]] [--loaded-at COLUMN --as-of TIMESTAMP]
                             [--top N] [--ratio] [--places N]

DATA is a CSV or JSON Lines file. Periods are inclusive days (YYYY-MM-DD:YYYY-MM-DD). --value is the amount that
is summed; --volume is the amount it is a rate of (units or orders; omitted, each row counts as 1).

Sum mode (default). With Vi the volume and Ri = Vi x ri the value of segment i, and shares s of the matched segments:
    volume = (V1 - V0) x R0/V0                   the whole business sold more or less, at last period's average
    mix    = sum over i of V1 x (s1i - s0i) x (r0i - R0/V0)   the share of a segment moved
    rate   = sum over i of V1i x (r1i - r0i)     the amount per unit inside a segment moved
A segment in only one period is a new or gone effect of its own. --ratio splits the change of the ratio value/volume
into mix and rate instead. The effects are exact fractions and add up to the change; the script checks that and says
so in `exact_sum_minus_change`.

Drivers are every effect ranked by size: the volume effect once, and each segment's mix, rate, new or gone effect.
`left_unexplained` is what the top drivers do not cover; the rate effect itself says nothing about why a price moved.

With --loaded-at and --as-of it also says what was missing from a report made at that moment, per day and segment.
It prints columns and counts only: a personal column is refused as a segment. Read-only, standard library only, JSON
on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
from statistics import median
from typing import Any

# The other scripts of this pack are copies in the same folder.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure

Rows = list[measure.Row]
Period = tuple[date, date]


def period(text: str) -> Period:
    try:
        left, right = text.split(":", 1)
        return date.fromisoformat(left), date.fromisoformat(right)
    except ValueError:
        raise SystemExit(f"a period is YYYY-MM-DD:YYYY-MM-DD, got {text!r}") from None


def amount(row: measure.Row, column: str | None) -> Fraction:
    if column is None:
        return Fraction(1)
    return measure.number(row[column]) or Fraction(0)


def percent(part: Fraction, whole: Fraction) -> float | None:
    if whole == 0:
        return None
    return round(float(100 * part / whole), 1)


def show_opt(value: Fraction | None, places: int) -> str | None:
    return None if value is None else measure.show(value, places)


class Segment:
    def __init__(self, name: str) -> None:
        self.name = name
        self.value0 = Fraction(0)
        self.value1 = Fraction(0)
        self.volume0 = Fraction(0)
        self.volume1 = Fraction(0)

    @property
    def in_a(self) -> bool:
        return self.volume0 != 0

    @property
    def in_b(self) -> bool:
        return self.volume1 != 0


def collect(a_rows: Rows, b_rows: Rows, keys: list[str], value: str, volume: str | None) -> list[Segment]:
    segments: dict[str, Segment] = {}
    for rows, side in ((a_rows, 0), (b_rows, 1)):
        for row in rows:
            name = measure.label(tuple(row[k] for k in keys))
            seg = segments.setdefault(name, Segment(name))
            if side == 0:
                seg.value0 += amount(row, value)
                seg.volume0 += amount(row, volume)
            else:
                seg.value1 += amount(row, value)
                seg.volume1 += amount(row, volume)
    return [segments[name] for name in sorted(segments)]


def split_sum(segments: list[Segment]) -> dict[str, Any]:
    """Volume, mix, rate, new and gone for a summed metric. Mix and rate are per segment, volume is one effect."""
    matched = [s for s in segments if s.in_a and s.in_b]
    v0 = sum((s.volume0 for s in matched), Fraction(0))
    v1 = sum((s.volume1 for s in matched), Fraction(0))
    r0 = sum((s.value0 for s in matched), Fraction(0))
    average = r0 / v0 if v0 else Fraction(0)
    volume_total = (v1 - v0) * average
    effects: dict[str, dict[str, Fraction]] = {}
    for seg in matched:
        share0 = seg.volume0 / v0
        rate0 = seg.value0 / seg.volume0
        rate1 = seg.value1 / seg.volume1
        effects[seg.name] = {
            "mix": (seg.volume1 - v1 * share0) * (rate0 - average),
            "rate": seg.volume1 * (rate1 - rate0),
            "own_volume": (v1 - v0) * share0 * rate0,
        }
    for seg in segments:
        if seg.in_b and not seg.in_a:
            effects[seg.name] = {"new": seg.value1}
        elif seg.in_a and not seg.in_b:
            effects[seg.name] = {"gone": -seg.value0}
    return {"volume": volume_total, "by_segment": effects}


def split_ratio(segments: list[Segment]) -> dict[str, Any]:
    """Mix and rate for a ratio: a new segment's whole effect is `new`, a gone segment falls out through its mix."""
    v0 = sum((s.volume0 for s in segments), Fraction(0))
    v1 = sum((s.volume1 for s in segments), Fraction(0))
    r0 = sum((s.value0 for s in segments), Fraction(0))
    m0 = r0 / v0 if v0 else Fraction(0)
    effects: dict[str, dict[str, Fraction]] = {}
    for seg in segments:
        s0 = seg.volume0 / v0 if v0 else Fraction(0)
        s1 = seg.volume1 / v1 if v1 else Fraction(0)
        if seg.in_a:
            rate0 = seg.value0 / seg.volume0
            effects[seg.name] = {"mix": (s1 - s0) * (rate0 - m0)}
            if seg.in_b:
                effects[seg.name]["rate"] = s1 * (seg.value1 / seg.volume1 - rate0)
        else:
            effects[seg.name] = {"new": s1 * (seg.value1 / seg.volume1 - m0)}
    return {"volume": Fraction(0), "by_segment": effects}


def effect_totals(split: dict[str, Any], *, ratio: bool) -> dict[str, Fraction]:
    totals: dict[str, Fraction] = {"mix": Fraction(0), "rate": Fraction(0), "new": Fraction(0), "gone": Fraction(0)}
    if not ratio:
        totals["volume"] = split["volume"]
    for parts in split["by_segment"].values():
        for key in ("mix", "rate", "new", "gone"):
            if key in parts:
                totals[key] += parts[key]
    return totals


def decompose(a_rows: Rows, b_rows: Rows, key: list[str], args: argparse.Namespace) -> dict[str, Any]:
    places = args.places
    segments = collect(a_rows, b_rows, key, args.value, args.volume)
    value0 = sum((s.value0 for s in segments), Fraction(0))
    value1 = sum((s.value1 for s in segments), Fraction(0))
    volume0 = sum((s.volume0 for s in segments), Fraction(0))
    volume1 = sum((s.volume1 for s in segments), Fraction(0))
    if args.ratio:
        metric0 = value0 / volume0 if volume0 else Fraction(0)
        metric1 = value1 / volume1 if volume1 else Fraction(0)
        split = split_ratio(segments)
    else:
        metric0, metric1 = value0, value1
        split = split_sum(segments)
    change = metric1 - metric0
    totals = effect_totals(split, ratio=args.ratio)
    exact_sum = sum(totals.values(), Fraction(0))
    rows_out = []
    for seg in segments:
        row: dict[str, Any] = {
            "segment": seg.name,
            "a_value": measure.show(seg.value0, places),
            "b_value": measure.show(seg.value1, places),
            "a_volume": measure.show(seg.volume0, places),
            "b_volume": measure.show(seg.volume1, places),
            "a_share_pct": percent(seg.volume0, volume0),
            "b_share_pct": percent(seg.volume1, volume1),
            "a_rate": show_opt(seg.value0 / seg.volume0 if seg.volume0 else None, 4),
            "b_rate": show_opt(seg.value1 / seg.volume1 if seg.volume1 else None, 4),
        }
        for name, val in split["by_segment"].get(seg.name, {}).items():
            row[name if name != "own_volume" else "volume_at_its_own_rate"] = measure.show(val, places)
        rows_out.append(row)
    drivers: list[tuple[str, str, Fraction]] = []
    if not args.ratio and totals["volume"] != 0:
        drivers.append(("volume", "all segments", totals["volume"]))
    for seg_name, parts in split["by_segment"].items():
        for name in ("mix", "rate", "new", "gone"):
            if name in parts and parts[name] != 0:
                drivers.append((name, seg_name, parts[name]))
    drivers.sort(key=lambda d: (-abs(d[2]), d[0], d[1]))
    top = drivers[: args.top]
    top_sum = sum((d[2] for d in top), Fraction(0))
    shown_total = sum(Fraction(measure.show(v, places)) for v in totals.values())
    return {
        "by": key,
        "a": measure.show(metric0, places),
        "b": measure.show(metric1, places),
        "change": measure.show(change, places),
        "change_pct": percent(change, metric0),
        "effects": {name: measure.show(val, places) for name, val in totals.items()},
        "effects_exact": {name: str(val) for name, val in totals.items()},
        "exact_sum_minus_change": str(exact_sum - change),
        "rounding_residual": measure.show(Fraction(measure.show(change, places)) - shown_total, places),
        "adds_up": exact_sum == change,
        "segments": rows_out,
        "drivers": [
            {
                "effect": name,
                "segment": seg,
                "amount": measure.show(val, places),
                "share_of_change_pct": percent(val, change),
            }
            for name, seg, val in drivers
        ],
        "top_drivers": args.top,
        "explained_by_top": measure.show(top_sum, places),
        "explained_by_top_pct_of_change": percent(top_sum, change),
        "left_unexplained": measure.show(change - top_sum, places),
    }


def days_in(frm: date, to: date) -> list[date]:
    return [frm + timedelta(days=i) for i in range((to - frm).days + 1)]


def check_days(rows: Rows, column: str, frm: date, to: date) -> dict[str, Any]:
    """Days with no rows at all, and days with far fewer rows than the period's typical day."""
    counts: Counter[date] = Counter(d for d in (measure.day(row[column]) for row in rows) if d is not None)
    days = days_in(frm, to)
    missing = [d.isoformat() for d in days if counts[d] == 0]
    typical = median([counts[d] for d in days]) if days else 0
    thin = [
        {"day": d.isoformat(), "rows": counts[d], "typical_rows": typical}
        for d in days
        if counts[d] and typical >= 4 and counts[d] < typical / 2
    ]
    return {"days": len(days), "days_with_rows": len(days) - len(missing), "missing_days": missing, "thin_days": thin}


def late_check(a_rows: Rows, b_rows: Rows, args: argparse.Namespace) -> dict[str, Any]:
    """Which rows a report made at --as-of could not have seen, and how much of the change that fakes."""
    cutoff = measure.moment(args.as_of)
    if cutoff is None:
        raise SystemExit(f"--as-of is not a timestamp: {args.as_of!r}")
    by_day: dict[str, dict[str, Any]] = {}
    by_segment: dict[str, Fraction] = {}
    key = args.by[0] if args.by else []
    late_value = {"a": Fraction(0), "b": Fraction(0)}
    for rows, side in ((a_rows, "a"), (b_rows, "b")):
        for row in rows:
            loaded = measure.moment(row[args.loaded_at])
            if loaded is None or loaded <= cutoff:
                continue
            found_day = measure.day(row[args.date])
            name = found_day.isoformat() if found_day else "(no date)"
            slot = by_day.setdefault(name, {"period": side, "late_rows": 0, "late_value": Fraction(0)})
            slot["late_rows"] += 1
            value = amount(row, args.value)
            slot["late_value"] += value
            late_value[side] += value
            if key:
                seg = measure.label(tuple(row[k] for k in key))
                by_segment[seg] = by_segment.get(seg, Fraction(0)) + value
    rows_per_day: Counter[str] = Counter(
        d.isoformat() for rows in (a_rows, b_rows) for d in (measure.day(row[args.date]) for row in rows) if d
    )
    final_change = sum((amount(r, args.value) for r in b_rows), Fraction(0)) - sum(
        (amount(r, args.value) for r in a_rows), Fraction(0)
    )
    as_of_a = sum((amount(r, args.value) for r in a_rows), Fraction(0)) - late_value["a"]
    as_of_b = sum((amount(r, args.value) for r in b_rows), Fraction(0)) - late_value["b"]
    as_of_change = as_of_b - as_of_a
    fake = as_of_change - final_change
    return {
        "as_of": args.as_of,
        "late_rows_a": sum(s["late_rows"] for s in by_day.values() if s["period"] == "a"),
        "late_rows_b": sum(s["late_rows"] for s in by_day.values() if s["period"] == "b"),
        "late_value_a": measure.show(late_value["a"], args.places),
        "late_value_b": measure.show(late_value["b"], args.places),
        "number_as_of_a": measure.show(as_of_a, args.places),
        "number_as_of_b": measure.show(as_of_b, args.places),
        "change_as_of": measure.show(as_of_change, args.places),
        "change_final": measure.show(final_change, args.places),
        "change_faked_by_late_rows": measure.show(fake, args.places),
        "share_of_reported_change_pct": percent(fake, as_of_change),
        "by_day": [
            {
                "day": d,
                "period": s["period"],
                "rows_final": rows_per_day[d],
                "late_rows": s["late_rows"],
                "late_share_of_rows_pct": round(100 * s["late_rows"] / rows_per_day[d], 1),
                "late_value": measure.show(s["late_value"], args.places),
            }
            for d, s in sorted(by_day.items())
        ],
        "by_segment": {seg: measure.show(v, args.places) for seg, v in sorted(by_segment.items())},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Why did this number change? Exact mix and rate decomposition.")
    parser.add_argument("data", type=Path)
    parser.add_argument("--date", required=True, help="the date column that puts a row in a period")
    parser.add_argument("--a", required=True, type=period, help="first period, YYYY-MM-DD:YYYY-MM-DD")
    parser.add_argument("--b", required=True, type=period, help="second period")
    parser.add_argument("--value", required=True, help="the column that is summed")
    parser.add_argument("--volume", help="the column the value is a rate of; default: each row counts as 1")
    parser.add_argument("--by", action="append", default=[], help="segment column(s), comma-separated; repeatable")
    parser.add_argument("--filter", action="append", default=[], help="column=value, column!=value or column>=value")
    parser.add_argument("--dedupe", help="key columns, comma-separated: keep the first row per key")
    parser.add_argument("--loaded-at", help="column with the time a row arrived")
    parser.add_argument("--as-of", help="the moment the reported number was made")
    parser.add_argument("--top", type=int, default=5, help="how many drivers count as named")
    parser.add_argument("--ratio", action="store_true", help="decompose value/volume instead of the sum")
    parser.add_argument("--places", type=int, default=2)
    args = parser.parse_args(argv)
    if bool(args.loaded_at) != bool(args.as_of):
        parser.error("--loaded-at and --as-of go together")
    if args.ratio and not args.volume:
        parser.error("--ratio needs --volume")
    args.by = [[k.strip() for k in part.split(",") if k.strip()] for part in args.by]
    table = measure.load(args.data)
    for key in args.by:
        measure.check_public(table, key, "a segment")
    needed = (
        [args.date, args.value] + ([args.volume] if args.volume else []) + ([args.loaded_at] if args.loaded_at else [])
    )
    measure.check_columns(table, needed)
    filters = [measure.parse_filter(f) for f in args.filter]
    dedupe = [k.strip() for k in args.dedupe.split(",")] if args.dedupe else []
    rows, filter_report = measure.apply_filters(table.rows, filters, table)
    duplicates = 0
    if dedupe:
        measure.check_columns(table, dedupe)
        counts = Counter(tuple(row[k] for k in dedupe) for row in rows)
        duplicates = sum(n - 1 for n in counts.values())
        seen: set[tuple[str | None, ...]] = set()
        kept: Rows = []
        for row in rows:
            token = tuple(row[k] for k in dedupe)
            if token not in seen:
                seen.add(token)
                kept.append(row)
        rows = kept
    dated = [row for row in rows if measure.day(row[args.date]) is not None]
    undated = len(rows) - len(dated)
    a_rows = [row for row in dated if args.a[0] <= (measure.day(row[args.date]) or date.min) <= args.a[1]]
    b_rows = [row for row in dated if args.b[0] <= (measure.day(row[args.date]) or date.min) <= args.b[1]]
    if not a_rows or not b_rows:
        raise SystemExit(f"period a has {len(a_rows)} rows and period b has {len(b_rows)} rows after the filters")
    for key in args.by:
        measure.check_cardinality(a_rows + b_rows, key)
    length_a = (args.a[1] - args.a[0]).days + 1
    length_b = (args.b[1] - args.b[0]).days + 1
    checks: dict[str, Any] = {
        "rows": {
            "a": len(a_rows),
            "b": len(b_rows),
            "duplicates_removed": duplicates,
            "rows_without_a_date": undated,
            "filters": filter_report,
        },
        "periods": {"a_days": length_a, "b_days": length_b, "equal_length": length_a == length_b},
        "days_a": check_days(a_rows, args.date, *args.a),
        "days_b": check_days(b_rows, args.date, *args.b),
    }
    if args.loaded_at:
        checks["late"] = late_check(a_rows, b_rows, args)
    result: dict[str, Any] = {
        "metric": {"value": args.value, "volume": args.volume, "mode": "ratio" if args.ratio else "sum"},
        "periods": {"a": f"{args.a[0]}:{args.a[1]}", "b": f"{args.b[0]}:{args.b[1]}"},
        "checks": checks,
        "decompositions": [decompose(a_rows, b_rows, key, args) for key in args.by],
        "notes": table.notes,
    }
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
