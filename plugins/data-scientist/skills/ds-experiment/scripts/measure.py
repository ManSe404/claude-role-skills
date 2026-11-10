#!/usr/bin/env python3
"""Count one measure on sample data: filters, a time window, one row per key, then a sum, a count or a ratio.

Usage: python3 measure.py TABLE_OR_FOLDER SPEC.json

SPEC.json holds {"measures": [MEASURE, ...]}. A MEASURE is:

    {"name": "net revenue", "table": "orders",
     "filters": [{"column": "status", "op": "=", "value": "completed"}],
     "window": {"column": "order_date", "from": "2026-10-01", "to": "2026-10-31"},
     "dedupe": ["order_id"],
     "value": {"sum": "net_amount"},
     "by": ["product_line"]}

`op` is one of = != < <= > >= in not_in is_null not_null. A filter follows SQL: a NULL cell fails every comparison
except is_null, so `!=` and `not_in` drop NULL rows, and each filter reports how many rows it dropped and how many of
those were NULL. `value` is {"sum": column or [columns]}, {"count": "*"}, {"count_distinct": column}, or a ratio of
two measures, {"ratio": {"numerator": MEASURE, "denominator": MEASURE}}.

Numbers are exact fractions: the same data always gives the same value, to the cent and beyond. The other scripts in
this pack import these functions, and it prints counts only: a personal column can be filtered on only for empty or
not empty, can never be a group, and no value of one is ever echoed. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

# A skill folder holds this script and data_profile.py side by side, so a sibling import works wherever it is run.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_profile

Row = dict[str, str | None]
OPS = ("=", "!=", "<", "<=", ">", ">=", "in", "not_in", "is_null", "not_null")
NUMBER = re.compile(r"^[+-]?(\d[\d ]*)?([.,]\d+)?$")
DAY_OK = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Personal columns are refused where a value of theirs could be echoed back into the output.
NULL_ONLY_OPS = ("is_null", "not_null")
MAX_SEGMENTS = 200
NBSP = chr(0xA0)


@dataclass
class Table:
    name: str
    path: Path
    header: list[str]
    rows: list[Row]
    total: int
    notes: list[str]
    personal: dict[str, str]


def number(value: str | None) -> Fraction | None:
    """The exact value of a cell, or None. Accepts a decimal comma, and a space or a comma as a thousands mark."""
    if value is None:
        return None
    text = value.strip().replace(NBSP, "").replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        last = max(text.rfind(","), text.rfind("."))
        decimal = text[last]
        text = text.replace("," if decimal == "." else ".", "").replace(decimal, ".")
    elif "," in text:
        text = (
            text.replace(",", ".")
            if text.count(",") == 1 and len(text.rsplit(",", 1)[1]) <= 2
            else text.replace(",", "")
        )
    if not NUMBER.match(text) or text in ("", "+", "-", ".", ",", "+.", "-."):
        return None
    try:
        return Fraction(text)
    except ValueError:
        return None


def day(value: str | None) -> date | None:
    """The calendar date of a date or datetime cell, or None when it cannot be read as one."""
    if value is None:
        return None
    return data_profile.parse_date(value, data_profile.kind_of(value.strip()))


def moment(value: str | None) -> datetime | None:
    """The date and time of a cell, ignoring any zone: comparing the clocks is exactly how a zone gap shows up."""
    if value is None:
        return None
    match = re.match(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?", value.strip())
    if not match:
        found = day(value)
        return datetime(found.year, found.month, found.day) if found else None
    second = match.group(4) or "0"
    return datetime.fromisoformat(f"{match.group(1)}T{match.group(2)}:{match.group(3)}:{second.zfill(2)}")


def show(value: Fraction, places: int = 2) -> str:
    """A fraction as a decimal string. Exact when it terminates within `places`, rounded otherwise."""
    scaled = value * 10**places
    rounded = scaled.numerator // scaled.denominator if scaled.denominator == 1 else round(scaled)
    sign = "-" if rounded < 0 else ""
    digits = str(abs(rounded)).zfill(places + 1)
    if places == 0:
        return f"{sign}{digits}"
    return f"{sign}{digits[:-places]}.{digits[-places:]}"


def load(path: Path, max_rows: int = data_profile.MAX_ROWS) -> Table:
    """Read one CSV or JSON Lines file. Cells are cleaned as data_profile cleans them, so NULLs are the same."""
    if path.suffix.lower() not in data_profile.FORMATS:
        raise SystemExit(f"not a data file: {path}")
    raw = data_profile.read_table(path, max_rows)
    header: list[str] = raw["header"]
    rows: list[Row] = [{name: data_profile.clean(row[i]) for i, name in enumerate(header)} for row in raw["rows"]]
    personal: dict[str, str] = {}
    for name in header:
        values = [row[name] for row in rows if row[name] is not None]
        found = data_profile.personal_of(name, [v for v in values if v is not None])
        if found:
            personal[name] = str(found["kind"])
    return Table(path.stem, path, header, rows, raw["total"], list(raw["notes"]), personal)


def tables(path: Path, max_rows: int = data_profile.MAX_ROWS) -> dict[str, Table]:
    """Every data file of a folder, or the one file given, by its stem."""
    if path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in data_profile.FORMATS)
    else:
        files = [path]
    if not files or not all(f.is_file() for f in files):
        raise SystemExit(f"no data files at {path}")
    return {f.stem: load(f, max_rows) for f in files}


def check_public(table: Table, columns: list[str], role: str) -> None:
    """Personal data may be counted, but never grouped on or echoed; a personal column here would print its values."""
    for column in columns:
        if column not in table.header:
            raise SystemExit(f"{table.name} has no column {column!r}; it has: {', '.join(table.header)}")
        if column in table.personal:
            raise SystemExit(
                f"{table.name}.{column} holds personal data ({table.personal[column]}): it cannot be used as {role}"
            )


def check_columns(table: Table, columns: list[str]) -> None:
    for column in columns:
        if column not in table.header:
            raise SystemExit(f"{table.name} has no column {column!r}; it has: {', '.join(table.header)}")


def passes(cell: str | None, op: str, target: Any) -> bool:
    """One SQL comparison. NULL fails everything but is_null; numbers compare as numbers, the rest as text."""
    if op == "is_null":
        return cell is None
    if op == "not_null":
        return cell is not None
    if cell is None:
        return False
    if op in ("in", "not_in"):
        values = [str(v) for v in target]
        hit = cell in values or any(number(cell) is not None and number(cell) == number(v) for v in values)
        return hit if op == "in" else not hit
    left = number(cell)
    right = number(str(target))
    if left is not None and right is not None:
        compare: Callable[[Any, Any], bool] = {
            "=": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
        }[op]
        return compare(left, right)
    text = str(target)
    return {
        "=": cell == text,
        "!=": cell != text,
        "<": cell < text,
        "<=": cell <= text,
        ">": cell > text,
        ">=": cell >= text,
    }[op]


def parse_filter(text: str) -> dict[str, Any]:
    """`status=completed`, `channel!=staff` or `region<>unknown`, from a command line."""
    match = re.match(r"^([\w.]+)\s*(!=|<>|<=|>=|=|<|>)\s*(.+)$", text)
    if not match:
        raise SystemExit(f"cannot read the filter {text!r}: write column=value, column!=value or column>=value")
    op = "!=" if match.group(2) == "<>" else match.group(2)
    value: Any = match.group(3).strip().strip("'\"")
    if op == "=" and "|" in value:
        return {"column": match.group(1), "op": "in", "value": value.split("|")}
    return {"column": match.group(1), "op": op, "value": value}


def apply_filters(
    rows: list[Row], filters: list[dict[str, Any]], table: Table
) -> tuple[list[Row], list[dict[str, Any]]]:
    """Apply the filters in order, and say what each one dropped. A NULL dropped by `!=` is the silent kind."""
    kept = rows
    report: list[dict[str, Any]] = []
    for spec in filters:
        column = spec["column"]
        op = spec["op"]
        if op not in OPS:
            raise SystemExit(f"unknown filter op {op!r}: use one of {', '.join(OPS)}")
        check_columns(table, [column])
        if column in table.personal and op not in NULL_ONLY_OPS:
            raise SystemExit(
                f"{table.name}.{column} holds personal data ({table.personal[column]}): only is_null and not_null "
                "may be used on it"
            )
        before = len(kept)
        nulls = sum(1 for row in kept if row[column] is None)
        kept = [row for row in kept if passes(row[column], op, spec.get("value"))]
        dropped = before - len(kept)
        null_dropped = nulls if op not in ("is_null",) and not passes(None, op, spec.get("value")) else 0
        report.append(
            {"filter": public_filter(spec, table), "rows_dropped": dropped, "null_rows_dropped": null_dropped}
        )
    return kept, report


def public_filter(spec: dict[str, Any], table: Table) -> str:
    """A filter as text for the output. The value of a filter on a personal column is never echoed."""
    op = spec["op"]
    column = spec["column"]
    if column in table.personal:
        return f"{column} {op}"
    value = spec.get("value")
    if op in ("is_null", "not_null"):
        return f"{column} {op}"
    if op in ("in", "not_in"):
        return f"{column} {op} {', '.join(str(v) for v in (value or []))}"
    return f"{column} {op} {value}"


def in_window(cell: str | None, frm: date, to: date) -> bool:
    found = day(cell)
    return found is not None and frm <= found <= to


def window_of(spec: dict[str, Any]) -> tuple[str, date, date]:
    column = spec["column"]
    for key in ("from", "to"):
        if not DAY_OK.match(str(spec.get(key, ""))):
            raise SystemExit(f"window {key} must be YYYY-MM-DD, got {spec.get(key)!r}")
    return column, date.fromisoformat(spec["from"]), date.fromisoformat(spec["to"])


def select(table: Table, measure: dict[str, Any]) -> tuple[list[Row], dict[str, Any]]:
    """The rows a measure counts, after its window, filters and de-duplication, and what each step did."""
    rows = table.rows
    trace: dict[str, Any] = {"rows_in_table": len(rows)}
    window = measure.get("window")
    if window:
        column, frm, to = window_of(window)
        check_columns(table, [column])
        rows = [row for row in rows if in_window(row[column], frm, to)]
        trace["window"] = f"{column} {frm.isoformat()}..{to.isoformat()}"
        trace["rows_after_window"] = len(rows)
    rows, filters = apply_filters(rows, list(measure.get("filters", [])), table)
    trace["filters"] = filters
    keys = list(measure.get("dedupe", []))
    if keys:
        check_columns(table, keys)
        seen: set[tuple[str | None, ...]] = set()
        unique: list[Row] = []
        for row in rows:
            key = tuple(row[k] for k in keys)
            if key not in seen:
                seen.add(key)
                unique.append(row)
        trace["duplicates_removed"] = len(rows) - len(unique)
        rows = unique
    trace["rows_kept"] = len(rows)
    return rows, trace


def aggregate(rows: list[Row], value: dict[str, Any], table: Table) -> Fraction:
    if "count" in value:
        return Fraction(len(rows))
    if "count_distinct" in value:
        column = value["count_distinct"]
        check_columns(table, [column])
        return Fraction(len({row[column] for row in rows if row[column] is not None}))
    if "sum" in value:
        columns = value["sum"] if isinstance(value["sum"], list) else [value["sum"]]
        check_columns(table, list(columns))
        total = Fraction(0)
        for row in rows:
            for column in columns:
                found = number(row[column])
                if found is not None:
                    total += found
        return total
    raise SystemExit(f"value must be sum, count, count_distinct or ratio, got {sorted(value)}")


def by_keys(measure: dict[str, Any], table: Table) -> list[str]:
    keys = list(measure.get("by", []))
    check_public(table, keys, "a group")
    return keys


def check_cardinality(rows: list[Row], keys: list[str], limit: int = MAX_SEGMENTS) -> None:
    """Grouping on something close to a row id would print ids and tell nothing, so it is refused."""
    distinct = len({tuple(row[k] for k in keys) for row in rows})
    if distinct > limit:
        raise SystemExit(f"{'+'.join(keys)} has {distinct} distinct values: group by something coarser (limit {limit})")


def groups_of(rows: list[Row], keys: list[str]) -> dict[tuple[str | None, ...], list[Row]]:
    found: dict[tuple[str | None, ...], list[Row]] = {}
    for row in rows:
        found.setdefault(tuple(row[k] for k in keys), []).append(row)
    return found


def label(key: tuple[str | None, ...]) -> str:
    return " / ".join("(empty)" if v is None else v for v in key)


def evaluate(measure: dict[str, Any], data: dict[str, Table]) -> dict[str, Any]:
    """Evaluate one measure. The result carries the value as display text and as an exact fraction."""
    value = measure.get("value")
    if value is None:
        raise SystemExit("a measure needs a value: sum, count, count_distinct or ratio")
    if "ratio" in value:
        num = evaluate({**value["ratio"]["numerator"], "name": "numerator"}, data)
        den = evaluate({**value["ratio"]["denominator"], "name": "denominator"}, data)
        top, bottom = Fraction(num["exact"]), Fraction(den["exact"])
        result: dict[str, Any] = {
            "name": measure.get("name"),
            "value": None if bottom == 0 else show(top / bottom, 6),
            "numerator": num,
            "denominator": den,
        }
        result["exact"] = None if bottom == 0 else str(top / bottom)
        result["rows_kept"] = num["rows_kept"]
        return result
    table_name = measure.get("table")
    if table_name not in data:
        raise SystemExit(f"no table {table_name!r}; have: {', '.join(sorted(data))}")
    table = data[table_name]
    rows, trace = select(table, measure)
    keys = by_keys(measure, table)
    check_cardinality(rows, keys)
    amount = aggregate(rows, value, table)
    result = {"name": measure.get("name"), "table": table_name, **trace}
    result["value"] = show(amount, int(measure.get("places", 2)))
    result["exact"] = str(amount)
    if keys:
        result["by"] = [
            {
                "group": label(k),
                "rows": len(g),
                "value": show(aggregate(g, value, table), int(measure.get("places", 2))),
                "exact": str(aggregate(g, value, table)),
            }
            for k, g in sorted(groups_of(rows, keys).items(), key=lambda item: label(item[0]))
        ]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Count measures on sample data, in exact numbers.")
    parser.add_argument("data", type=Path, help="a data file or a folder of them")
    parser.add_argument("spec", type=Path, help="SPEC.json")
    args = parser.parse_args(argv)
    data = tables(args.data)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    results = [evaluate(m, data) for m in spec["measures"]]
    json.dump({"measures": results}, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
