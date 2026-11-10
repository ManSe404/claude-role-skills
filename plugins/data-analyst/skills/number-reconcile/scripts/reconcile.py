#!/usr/bin/env python3
"""Two numbers that should agree do not: find where they part, row by row, and make the whole gap add up.

Usage: python3 reconcile.py A_FILE B_FILE --key COLUMN [--key-b COLUMN]
                             --value-a COLUMN --value-b COLUMN --date-a COLUMN --date-b COLUMN --window FROM:TO
                             [--filter-a column=value ...] [--filter-b column=value ...]
                             [--slice COLUMN[,COLUMN]] [--filter-columns COLUMN[,COLUMN]]
                             [--rounding AMOUNT] [--places N]

Each file is one system's rows. The window applies to each system's own date column (inclusive, YYYY-MM-DD:YYYY-MM-DD).
A key joins one business event between the systems; the gap is A minus B over the window. Every key lands in
exactly one bucket and the buckets add up to the gap, checked in exact fractions:

    only_in_a / only_in_b        the key is nowhere in the other system
    filtered_a / filtered_b      only-in rows whose value in a --filter-columns column never reaches the other system
    duplicates_a / duplicates_b  second and later rows of a key inside the window
    time_zone_a / time_zone_b    the row is in the window on one side only (a: in A's window, b: in B's), and the other
                                 side has it outside the window a whole number of hours away (under 15)
    timing_a / timing_b          the same, but further away than that
    rounding                     the amounts differ by less than the rounding unit (auto-detected or --rounding)
    value_difference             the amounts differ by more than that: the part this script cannot explain

--slice shows the gap per value of a column, to narrow down where it sits. It prints columns and counts only: keys are
never printed and a personal column cannot be a slice. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable
from datetime import date
from fractions import Fraction
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure

Rows = list[measure.Row]
MAX_ZONE_HOURS = 14  # no zone offset is larger; a bigger gap between the two clocks is timing, not a time zone.
ROUNDING_UNITS = (Fraction(1), Fraction(1, 10), Fraction(1, 100))
ROUNDED_SHARE = Fraction(98, 100)  # under this share of round values, a system is not rounding.


def window_of(text: str) -> tuple[date, date]:
    try:
        left, right = text.split(":", 1)
        return date.fromisoformat(left), date.fromisoformat(right)
    except ValueError:
        raise SystemExit(f"a window is YYYY-MM-DD:YYYY-MM-DD, got {text!r}") from None


def amount_of(row: measure.Row, column: str) -> Fraction:
    return measure.number(row[column]) or Fraction(0)


def coarsest_unit(values: list[Fraction]) -> Fraction | None:
    """The coarsest of 1, 0.1 and 0.01 that (almost) every value is a multiple of, or None."""
    if not values:
        return None
    for unit in ROUNDING_UNITS:
        multiples = sum(1 for v in values if (v / unit).denominator == 1)
        if Fraction(multiples, len(values)) >= ROUNDED_SHARE:
            return unit
    return None


def rounding_tolerance(a_values: list[Fraction], b_values: list[Fraction], forced: str | None) -> dict[str, Any]:
    if forced is not None:
        value = measure.number(forced)
        if value is None:
            raise SystemExit(f"--rounding is not a number: {forced!r}")
        return {"tolerance": value, "unit": None, "side": "given on the command line", "detected": False}
    unit_a, unit_b = coarsest_unit(a_values), coarsest_unit(b_values)
    if unit_a is not None and (unit_b is None or unit_a > unit_b):
        return {"tolerance": unit_a / 2, "unit": unit_a, "side": "a rounds its amounts", "detected": True}
    if unit_b is not None and (unit_a is None or unit_b > unit_a):
        return {"tolerance": unit_b / 2, "unit": unit_b, "side": "b rounds its amounts", "detected": True}
    return {"tolerance": Fraction(0), "unit": None, "side": "neither system rounds", "detected": False}


def group(rows: Rows, key: str, date_column: str, frm: date, to: date) -> tuple[dict[str, Rows], dict[str, Rows]]:
    """Rows by key, inside the window and over all time. A row without a key cannot be matched and is listed apart."""
    window: dict[str, Rows] = {}
    every: dict[str, Rows] = {}
    for row in rows:
        token = row[key]
        if token is None:
            continue
        every.setdefault(token, []).append(row)
        if measure.in_window(row[date_column], frm, to):
            window.setdefault(token, []).append(row)
    return window, every


def hours_between(left: str | None, right: str | None) -> float | None:
    one = measure.moment(left)
    two = measure.moment(right)
    if one is None or two is None:
        return None
    return abs((two - one).total_seconds()) / 3600


class Buckets:
    """Signed amounts and row counts per bucket, in exact fractions, plus the slice each key's gap belongs to."""

    def __init__(self) -> None:
        self.amount: dict[str, Fraction] = {}
        self.rows: Counter[str] = Counter()

    def add(self, name: str, value: Fraction, rows: int = 1) -> None:
        self.amount[name] = self.amount.get(name, Fraction(0)) + value
        self.rows[name] += rows


def filtered_values(
    side: str, rows_by_key: dict[str, Rows], other_keys: Iterable[str], columns: list[str]
) -> dict[tuple[str, str], int]:
    """The (column, value) pairs that never appear on a row that matched the other system: a filter, not chance."""
    matched = set(other_keys)
    seen: dict[tuple[str, str], list[bool]] = {}
    for token, rows in rows_by_key.items():
        for row in rows[:1]:
            for column in columns:
                if column in row and row[column] is not None:
                    seen.setdefault((column, str(row[column])), []).append(token in matched)
    return {pair: len(flags) for pair, flags in seen.items() if not any(flags)} if side else {}


def split_rows(
    window: dict[str, Rows], every_other: dict[str, Rows], other_window: dict[str, Rows], key_column: str
) -> tuple[list[str], list[str], list[str]]:
    in_both = sorted(k for k in window if k in other_window)
    elsewhere = sorted(k for k in window if k not in other_window and k in every_other)
    nowhere = sorted(k for k in window if k not in other_window and k not in every_other)
    return in_both, elsewhere, nowhere


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Account for the whole gap between two numbers that should agree.")
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    parser.add_argument("--key", required=True, help="the key column in A (and B, unless --key-b)")
    parser.add_argument("--key-b", help="the key column in B, when it has another name")
    parser.add_argument("--value-a", required=True)
    parser.add_argument("--value-b", required=True)
    parser.add_argument("--date-a", required=True)
    parser.add_argument("--date-b", required=True)
    parser.add_argument("--window", required=True, type=window_of, help="YYYY-MM-DD:YYYY-MM-DD, each on its own date")
    parser.add_argument("--filter-a", action="append", default=[], help="filter on A, column=value or column!=value")
    parser.add_argument("--filter-b", action="append", default=[], help="filter on B")
    parser.add_argument("--slice", action="append", default=[], help="columns to narrow the gap by, comma-separated")
    parser.add_argument("--filter-columns", action="append", default=[], help="columns that may hold a filter")
    parser.add_argument("--rounding", help="amounts this close count as rounding; default: auto-detected")
    parser.add_argument("--places", type=int, default=2)
    args = parser.parse_args(argv)
    table_a, table_b = measure.load(args.a), measure.load(args.b)
    key_b = args.key_b or args.key
    measure.check_columns(table_a, [args.key, args.value_a, args.date_a])
    measure.check_columns(table_b, [key_b, args.value_b, args.date_b])
    frm, to = args.window
    slices = [c.strip() for part in args.slice for c in part.split(",") if c.strip()]
    filter_columns = [c.strip() for part in args.filter_columns for c in part.split(",") if c.strip()]
    measure.check_public(table_a, [c for c in slices if c in table_a.header], "a slice")
    measure.check_public(table_b, [c for c in slices if c in table_b.header], "a slice")
    rows_a, report_a = measure.apply_filters(table_a.rows, [measure.parse_filter(f) for f in args.filter_a], table_a)
    rows_b, report_b = measure.apply_filters(table_b.rows, [measure.parse_filter(f) for f in args.filter_b], table_b)
    window_a, every_a = group(rows_a, args.key, args.date_a, frm, to)
    window_b, every_b = group(rows_b, key_b, args.date_b, frm, to)
    no_key_a = sum(1 for r in rows_a if r[args.key] is None and measure.in_window(r[args.date_a], frm, to))
    no_key_b = sum(1 for r in rows_b if r[key_b] is None and measure.in_window(r[args.date_b], frm, to))
    both_keys = [k for k in window_a if k in window_b]
    tolerance = rounding_tolerance(
        [amount_of(window_a[k][0], args.value_a) for k in both_keys],
        [amount_of(window_b[k][0], args.value_b) for k in both_keys],
        args.rounding,
    )
    limit: Fraction = tolerance["tolerance"]
    total_a = sum((amount_of(r, args.value_a) for rows in window_a.values() for r in rows), Fraction(0))
    total_b = sum((amount_of(r, args.value_b) for rows in window_b.values() for r in rows), Fraction(0))
    buckets = Buckets()
    contribution: dict[str, Fraction] = {}
    filtered_a = filtered_values("a", window_a, set(window_b) | set(every_b), filter_columns)
    filtered_b = filtered_values("b", window_b, set(window_a) | set(every_a), filter_columns)
    only_a_rows: dict[str, Rows] = {}

    def place_duplicates(rows: Rows, name: str, sign: int, column: str, token: str) -> None:
        for row in rows[1:]:
            value = amount_of(row, column) * sign
            buckets.add(name, value)
            contribution[token] = contribution.get(token, Fraction(0)) + value

    for token in sorted(set(window_a) | set(window_b)):
        a_side, b_side = window_a.get(token, []), window_b.get(token, [])
        place_duplicates(a_side, "duplicates_a", 1, args.value_a, token)
        place_duplicates(b_side, "duplicates_b", -1, args.value_b, token)
        if a_side and b_side:
            gap = amount_of(a_side[0], args.value_a) - amount_of(b_side[0], args.value_b)
            contribution[token] = contribution.get(token, Fraction(0)) + gap
            if abs(gap) <= limit:
                buckets.add("rounding", gap)
            else:
                buckets.add("value_difference", gap)
            continue
        if a_side:
            value = amount_of(a_side[0], args.value_a)
            contribution[token] = contribution.get(token, Fraction(0)) + value
            if token in every_b:
                hours = hours_between(a_side[0][args.date_a], every_b[token][0][args.date_b])
                near = hours is not None and hours <= MAX_ZONE_HOURS and abs(hours - round(hours)) < 0.02
                buckets.add("time_zone_a" if near else "timing_a", value)
            else:
                only_a_rows[token] = a_side
                reason = next(
                    (
                        f"filtered_a:{column}={a_side[0][column]}"
                        for column in filter_columns
                        if column in a_side[0] and (column, str(a_side[0][column])) in filtered_a
                    ),
                    "only_in_a",
                )
                buckets.add(reason, value)
        else:
            value = amount_of(b_side[0], args.value_b)
            contribution[token] = contribution.get(token, Fraction(0)) - value
            if token in every_a:
                hours = hours_between(every_a[token][0][args.date_a], b_side[0][args.date_b])
                near = hours is not None and hours <= MAX_ZONE_HOURS and abs(hours - round(hours)) < 0.02
                buckets.add("time_zone_b" if near else "timing_b", -value)
            else:
                reason = next(
                    (
                        f"filtered_b:{column}={b_side[0][column]}"
                        for column in filter_columns
                        if column in b_side[0] and (column, str(b_side[0][column])) in filtered_b
                    ),
                    "only_in_b",
                )
                buckets.add(reason, -value)
    gap = total_a - total_b
    exact_sum = sum(buckets.amount.values(), Fraction(0))
    rows_out = []
    notes = {
        "only_in_a": "in A and nowhere in B",
        "only_in_b": "in B and nowhere in A",
        "duplicates_a": "second and later rows of a key in A",
        "duplicates_b": "second and later rows of a key in B",
        "time_zone_a": "counted in A's window, B has it just outside: the two clocks differ by whole hours",
        "time_zone_b": "counted in B's window, A has it just outside: the two clocks differ by whole hours",
        "timing_a": "counted in A's window, B has it outside and days away",
        "timing_b": "counted in B's window, A has it outside and days away",
        "rounding": f"amounts differ by at most {measure.show(limit, 2)} ({tolerance['side']})",
        "value_difference": "same key, amounts differ by more than rounding: nothing here says why",
    }
    for name in sorted(buckets.amount, key=lambda n: (-abs(buckets.amount[n]), n)):
        note = notes.get(name.split(":", 1)[0], "the key is nowhere on the other side; this value never reaches it")
        rows_out.append(
            {
                "bucket": name,
                "amount": measure.show(buckets.amount[name], args.places),
                "exact": str(buckets.amount[name]),
                "rows": buckets.rows[name],
                "share_of_gap_pct": None if gap == 0 else round(float(100 * buckets.amount[name] / gap), 1),
                "note": note,
            }
        )
    slice_out = []
    for column in slices:
        groups: dict[str, Fraction] = {}
        keys_in: Counter[str] = Counter()
        for token, value in contribution.items():
            row = (window_a.get(token) or every_a.get(token) or window_b.get(token) or [{}])[0]
            cell = row.get(column) if column in row else None
            name = "(not on this side)" if column not in row else "(empty)" if cell is None else str(cell)
            groups[name] = groups.get(name, Fraction(0)) + value
            keys_in[name] += 1
        slice_out.append(
            {
                "column": column,
                "values": [
                    {
                        "value": name,
                        "gap": measure.show(val, args.places),
                        "share_of_gap_pct": None if gap == 0 else round(float(100 * val / gap), 1),
                        "keys": keys_in[name],
                    }
                    for name, val in sorted(groups.items(), key=lambda item: (-abs(item[1]), item[0]))
                ],
            }
        )
    result = {
        "window": f"{frm}:{to}",
        "a": {
            "file": table_a.name,
            "rows_in_window": sum(len(v) for v in window_a.values()),
            "keys_in_window": len(window_a),
            "rows_without_a_key": no_key_a,
            "total": measure.show(total_a, args.places),
            "filters": report_a,
        },
        "b": {
            "file": table_b.name,
            "rows_in_window": sum(len(v) for v in window_b.values()),
            "keys_in_window": len(window_b),
            "rows_without_a_key": no_key_b,
            "total": measure.show(total_b, args.places),
            "filters": report_b,
        },
        "gap": measure.show(gap, args.places),
        "gap_exact": str(gap),
        "rounding": {
            "unit": None if tolerance["unit"] is None else str(tolerance["unit"]),
            "tolerance": measure.show(limit, 2),
            "side": tolerance["side"],
            "detected": tolerance["detected"],
        },
        "buckets": rows_out,
        "exact_sum_of_buckets_minus_gap": str(exact_sum - gap),
        "adds_up": exact_sum == gap,
        "unexplained": {
            "amount": measure.show(buckets.amount.get("value_difference", Fraction(0)), args.places),
            "rows": buckets.rows["value_difference"],
        },
        "slices": slice_out,
        "notes": [*table_a.notes, *table_b.notes],
    }
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
