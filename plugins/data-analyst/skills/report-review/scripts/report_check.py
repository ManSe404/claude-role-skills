#!/usr/bin/env python3
"""Check a report before it goes out: places to read in its SQL or notebook, and its numbers recounted.

Usage: python3 report_check.py sql REPORT_DIR [--data DATA_DIR]
       python3 report_check.py data SPEC.json DATA_DIR

sql reads every .sql, .hql, .py and .ipynb file, with comments and strings blanked first, and lists places to read:
    null_dropping_filter  <>, != or NOT IN: a NULL fails them, so those rows silently leave
    avg_of_avg            AVG of an alias that is itself an average
    ratio                 a division of aggregates; a CASE or FILTER in the denominator is marked
    fanout_candidate      a JOIN on a key the joined table does not hold once per row (needs --data to know)
    window_mismatch       date windows in one file that do not cover the same length
    partial_period        a window that stops short of a whole month next to one that is a whole month
    truncated_axis        a chart axis that does not start at zero
With --data, a filter's hit counts the NULL rows of its column and a join's hit counts the rows it would multiply.
A hit is a place to read, not a finding.

data runs the checks in SPEC.json against sample data: {"checks": [{"check": NAME, ...}, ...]}. Each check takes
"table", "filters" and "window" as measure.py reads them (a `value` is one column):
    avg_of_averages {"group": "store_id", "value": "net_amount"}     the mean of group means against the true mean
    small_groups    {"group": "store_id", "min_rows": 30}            groups too small to rank, with their rows
    simpson         {"compare": "device", "numerator": "orders", "denominator": "sessions", "within": ["source"]}
                    the rate of each group, overall and per stratum; a reversal when the overall winner loses in every
                    stratum of a `within` column.
    fanout          {"join": "order_promotions", "key": "order_id", "value": "net_amount"}  the sum before and after
    windows         {"date": "order_date", "value": "net_amount", "periods": [{"name": "sep", "from": ..., "to": ...}]}
                    length, rows, sum and sum per day of each period, and the first common number of days of each

Numbers are exact fractions. It prints columns and counts only: a personal column cannot be grouped on. Read-only,
standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure
import sql_inventory

SQL_SUFFIXES = {".sql", ".hql"}
NOT_EQUAL = re.compile(r"(?i)([\w.\"`\[\]]+)\s*(<>|!=)\s*")
NOT_IN = re.compile(r"(?i)([\w.\"`\[\]]+)\s+not\s+(in|like)\b")
AVG_ALIAS = re.compile(r"(?is)\bavg\s*\(.*?\)\s+as\s+(\w+)")
AVG_OF = re.compile(r"(?is)\bavg\s*\(\s*([\w.]+)\s*\)")
DIVISION = re.compile(r"(?is)/\s*(?:nullif\s*\()?\s*(sum|count|avg)\s*\(")
JOIN = re.compile(
    r"(?is)\bjoin\s+([\w.\"`\[\]]+)(\s+as\s+\w+|\s+\w+)?\s+on\b([^;]*?)(?=\bwhere\b|\bjoin\b|\bgroup\b|\border\b|;|$)"
)
BETWEEN = re.compile(r"(?i)\bbetween\s+'(\d{4}-\d{2}-\d{2})'\s+and\s+'(\d{4}-\d{2}-\d{2})'")
RANGE = re.compile(r"(?is)>=?\s*'(\d{4}-\d{2}-\d{2})'.{0,120}?<=?\s*'(\d{4}-\d{2}-\d{2})'")
YLIM = re.compile(r"(?:set_ylim|\.ylim)\(\s*(-?[\d_.]+)")
SQL_NOTEBOOK = re.compile(r"(?i)\bselect\b|\bfrom\b")


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def last_day_of_month(day: date) -> date:
    following = day.replace(day=28) + timedelta(days=4)
    return following.replace(day=1) - timedelta(days=1)


def whole_month(frm: date, to: date) -> bool:
    return frm.day == 1 and to == last_day_of_month(frm)


def snippet(raw: str, line: int) -> str:
    lines = raw.splitlines()
    return lines[line - 1].strip()[:160] if 0 < line <= len(lines) else ""


def sql_files(root: Path) -> list[Path]:
    return [
        p
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.suffix.lower() in SQL_SUFFIXES and not set(p.parts) & sql_inventory.SKIP_DIRS
    ]


def hit(found: list[dict[str, Any]], family: str, rel: str, raw: str, line: int, detail: str, **extra: Any) -> None:
    found.append({"family": family, "file": rel, "line": line, "text": snippet(raw, line), "detail": detail, **extra})


def null_cells(column: str, data: dict[str, measure.Table] | None) -> list[dict[str, Any]]:
    """In which tables this column has NULL rows; the name is often qualified, so only the last part is matched."""
    if not data:
        return []
    name = column.rsplit(".", 1)[-1].strip('"`[]')
    return [
        {"table": t.name, "null_rows": sum(1 for r in t.rows if r[name] is None), "rows": len(t.rows)}
        for t in data.values()
        if name in t.header and name not in t.personal
    ]


def join_counts(table_name: str, column: str, data: dict[str, measure.Table] | None) -> dict[str, Any] | None:
    if not data:
        return None
    table = data.get(table_name.rsplit(".", 1)[-1].strip('"`[]'))
    if table is None or column not in table.header:
        return None
    counts = Counter(row[column] for row in table.rows if row[column] is not None)
    if not counts:
        return None
    extra_rows = sum(n - 1 for n in counts.values() if n > 1)
    return {
        "table": table.name,
        "column": column,
        "max_rows_per_key": max(counts.values()),
        "keys_with_several_rows": sum(1 for n in counts.values() if n > 1),
        "extra_rows_a_join_would_add": extra_rows,
    }


def check_sql_file(path: Path, root: Path, data: dict[str, measure.Table] | None, found: list[dict[str, Any]]) -> None:
    rel = path.relative_to(root).as_posix()
    raw = path.read_text(encoding="utf-8", errors="replace")
    clean, _, _ = sql_inventory.clean_sql(raw)
    for match in NOT_EQUAL.finditer(clean):
        column = match.group(1)
        if column.lower() in ("case", "when", "then"):
            continue
        nulls = null_cells(column, data)
        hit(
            found,
            "null_dropping_filter",
            rel,
            raw,
            line_of(clean, match.start()),
            f"{column} {match.group(2)}",
            nulls=nulls,
        )
    for match in NOT_IN.finditer(clean):
        column = match.group(1)
        hit(
            found,
            "null_dropping_filter",
            rel,
            raw,
            line_of(clean, match.start()),
            f"{column} NOT {match.group(2).upper()}",
            nulls=null_cells(column, data),
        )
    aliases = {m.group(1).lower() for m in AVG_ALIAS.finditer(clean)}
    for match in AVG_OF.finditer(clean):
        column = match.group(1).rsplit(".", 1)[-1].lower()
        if column in aliases:
            hit(found, "avg_of_avg", rel, raw, line_of(clean, match.start()), f"AVG of {column}, itself an average")
    for match in DIVISION.finditer(clean):
        line = line_of(clean, match.start())
        conditional = bool(
            re.search(r"(?i)\bcase\b|\bfilter\s*\(", clean[match.end() : match.end() + 200].split("\n")[0])
        )
        hit(
            found,
            "ratio",
            rel,
            raw,
            line,
            "the denominator is conditional" if conditional else "a ratio of aggregates",
            conditional_denominator=conditional,
        )
    for match in JOIN.finditer(clean):
        table = match.group(1)
        on_text = match.group(3)
        columns = sorted(
            {c.split(".")[-1] for c in re.findall(r"[\w.]*\.[\w]+|\b\w+\b", on_text) if "." in c or c.isidentifier()}
        )
        columns = [c for c in columns if c.lower() not in ("on", "and", "or", "as")]
        counts = next((c for column in columns if (c := join_counts(table, column, data))), None)
        multiplies = bool(counts and counts["keys_with_several_rows"])
        hit(
            found,
            "fanout_candidate",
            rel,
            raw,
            line_of(clean, match.start()),
            f"joins {table} on {', '.join(columns)}",
            counted=counts,
            multiplies=multiplies if counts else None,
        )
    windows: list[tuple[int, date, date]] = []
    for pattern in (BETWEEN, RANGE):
        for match in pattern.finditer(raw):
            if clean[match.start()] == " ":
                continue
            frm, to = date.fromisoformat(match.group(1)), date.fromisoformat(match.group(2))
            windows.append((line_of(raw, match.start()), frm, to))
    spans = {(to - frm).days + 1 for _, frm, to in windows}
    if len(spans) > 1:
        for line, frm, to in windows:
            hit(found, "window_mismatch", rel, raw, line, f"{frm}..{to}: {(to - frm).days + 1} days")
    has_whole = any(whole_month(frm, to) for _, frm, to in windows)
    for line, frm, to in windows:
        if has_whole and not whole_month(frm, to):
            hit(
                found, "partial_period", rel, raw, line, f"{frm}..{to} stops short of a whole month next to one that is"
            )
    for line, frm, to in windows:
        found.append(
            {
                "family": "window",
                "file": rel,
                "line": line,
                "text": snippet(raw, line),
                "detail": f"{frm}..{to}, {(to - frm).days + 1} days",
                "whole_month": whole_month(frm, to),
            }
        )


def check_chart_code(path: Path, root: Path, found: list[dict[str, Any]]) -> None:
    rel = path.relative_to(root).as_posix()
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = raw
    if path.suffix.lower() == ".ipynb":
        try:
            notebook = json.loads(raw)
        except json.JSONDecodeError:
            return
        cells = notebook.get("cells", [])
        text = "\n".join("".join(c.get("source", [])) for c in cells if c.get("cell_type") == "code")
    for match in YLIM.finditer(text):
        low = float(match.group(1).replace("_", ""))
        if low != 0:
            line = line_of(text, match.start())
            where = f"cell code line {line}" if path.suffix.lower() == ".ipynb" else ""
            found.append(
                {
                    "family": "truncated_axis",
                    "file": rel,
                    "line": line,
                    "where": where,
                    "text": text.splitlines()[line - 1].strip()[:160],
                    "detail": f"the value axis starts at {match.group(1)}",
                }
            )


def check_sql(root: Path, data_dir: Path | None) -> dict[str, Any]:
    if not root.is_dir():
        raise SystemExit(f"not a folder: {root}")
    data = measure.tables(data_dir) if data_dir else None
    found: list[dict[str, Any]] = []
    files = sql_files(root)
    for path in files:
        check_sql_file(path, root, data, found)
    notebooks = [
        p
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.suffix.lower() in (".ipynb", ".py") and not set(p.parts) & sql_inventory.SKIP_DIRS
    ]
    for path in notebooks:
        check_chart_code(path, root, found)
    windows = [h for h in found if h["family"] == "window"]
    hits = sorted((h for h in found if h["family"] != "window"), key=lambda h: (h["family"], h["file"], h["line"]))
    return {
        "report": str(root),
        "files_read": [p.relative_to(root).as_posix() for p in [*files, *notebooks]],
        "windows": sorted(windows, key=lambda h: (h["file"], h["line"])),
        "hits": hits,
        "families": dict(Counter(h["family"] for h in hits)),
        "note": "A hit is a place to read. Confirm each one against the code and the data before it becomes a finding.",
    }


def base_rows(
    spec: dict[str, Any], data: dict[str, measure.Table]
) -> tuple[list[measure.Row], measure.Table, dict[str, Any]]:
    table_name = spec.get("table")
    if table_name not in data:
        raise SystemExit(f"no table {table_name!r}; have: {', '.join(sorted(data))}")
    table = data[table_name]
    rows, trace = measure.select(table, spec)
    return rows, table, trace


def total(rows: list[measure.Row], column: str) -> Fraction:
    return sum((measure.number(row[column]) or Fraction(0) for row in rows), Fraction(0))


def check_avg_of_averages(spec: dict[str, Any], data: dict[str, measure.Table]) -> dict[str, Any]:
    rows, table, trace = base_rows(spec, data)
    group, value = spec["group"], spec["value"]
    measure.check_public(table, [group], "a group")
    measure.check_columns(table, [value])
    buckets: dict[str, list[measure.Row]] = {}
    for row in rows:
        buckets.setdefault("(empty)" if row[group] is None else str(row[group]), []).append(row)
    means = {name: total(g, value) / len(g) for name, g in buckets.items()}
    mean_of_means = sum(means.values(), Fraction(0)) / len(means)
    true_mean = total(rows, value) / len(rows)
    return {
        "check": "avg_of_averages",
        "groups": [
            {"group": k, "rows": len(buckets[k]), "average": measure.show(v, 2)}
            for k, v in sorted(means.items(), key=lambda kv: -kv[1])
        ],
        "average_of_averages": measure.show(mean_of_means, 2),
        "true_average": measure.show(true_mean, 2),
        "difference": measure.show(mean_of_means - true_mean, 2),
        "rows": trace["rows_kept"],
    }


def check_small_groups(spec: dict[str, Any], data: dict[str, measure.Table]) -> dict[str, Any]:
    rows, table, _ = base_rows(spec, data)
    group = spec["group"]
    minimum = int(spec.get("min_rows", 30))
    measure.check_public(table, [group], "a group")
    counts: Counter[str] = Counter("(empty)" if row[group] is None else str(row[group]) for row in rows)
    return {
        "check": "small_groups",
        "min_rows": minimum,
        "groups": [
            {"group": k, "rows": n, "small": n < minimum} for k, n in sorted(counts.items(), key=lambda kv: kv[1])
        ],
        "small_groups": sorted(k for k, n in counts.items() if n < minimum),
    }


def _rate(rows: list[measure.Row], numerator: str, denominator: str) -> tuple[Fraction, Fraction]:
    return total(rows, numerator), total(rows, denominator)


def check_simpson(spec: dict[str, Any], data: dict[str, measure.Table]) -> dict[str, Any]:
    rows, table, _ = base_rows(spec, data)
    compare = spec["compare"]
    numerator, denominator = spec["numerator"], spec["denominator"]
    within = list(spec.get("within", []))
    measure.check_public(table, [compare, *within], "a comparison column")
    measure.check_columns(table, [numerator, denominator])
    names = sorted({str(row[compare]) for row in rows if row[compare] is not None})
    if len(names) < 2:
        return {"check": "simpson", "note": f"{compare} has fewer than two groups", "reversal": False}
    overall = {n: _rate([r for r in rows if r[compare] == n], numerator, denominator) for n in names}
    rates = {n: (top / bottom if bottom else Fraction(0)) for n, (top, bottom) in overall.items()}
    ranked = sorted(names, key=lambda n: -rates[n])
    leader, runner = ranked[0], ranked[1]
    columns_out = []
    reversal_in = []
    for stratum_column in within:
        cells: list[dict[str, Any]] = []
        reversed_all = True
        values = sorted({"(empty)" if row[stratum_column] is None else str(row[stratum_column]) for row in rows})
        for value in values:
            members = [r for r in rows if ("(empty)" if r[stratum_column] is None else str(r[stratum_column])) == value]
            cell: dict[str, Any] = {"stratum": value}
            own: dict[str, Fraction | None] = {}
            for name in names:
                top, bottom = _rate([r for r in members if r[compare] == name], numerator, denominator)
                rate = top / bottom if bottom else None
                own[name] = rate
                cell[name] = {
                    "numerator": str(top),
                    "denominator": str(bottom),
                    "rate_pct": None if rate is None else round(float(100 * rate), 2),
                }
            cells.append(cell)
            a_rate, b_rate = own[leader], own[runner]
            if a_rate is None or b_rate is None or not a_rate < b_rate:
                reversed_all = False
        if reversed_all:
            reversal_in.append(stratum_column)
        columns_out.append({"column": stratum_column, "strata": cells, "leader_loses_in_every_stratum": reversed_all})
    return {
        "check": "simpson",
        "compare": compare,
        "overall": {
            n: {
                "numerator": str(overall[n][0]),
                "denominator": str(overall[n][1]),
                "rate_pct": round(float(100 * rates[n]), 2),
            }
            for n in names
        },
        "overall_leader": leader,
        "runner_up": runner,
        "reversal": bool(reversal_in),
        "reversal_in": reversal_in,
        "within": columns_out,
    }


def check_fanout(spec: dict[str, Any], data: dict[str, measure.Table]) -> dict[str, Any]:
    rows, table, _ = base_rows(spec, data)
    join_name, key, value = spec["join"], spec["key"], spec["value"]
    if join_name not in data:
        raise SystemExit(f"no table {join_name!r}; have: {', '.join(sorted(data))}")
    measure.check_columns(table, [key, value])
    measure.check_columns(data[join_name], [key])
    counts = Counter(row[key] for row in data[join_name].rows if row[key] is not None)
    correct = total(rows, value)
    joined = sum(
        ((measure.number(row[value]) or Fraction(0)) * max(1, counts.get(row[key], 0)) for row in rows),
        Fraction(0),
    )
    return {
        "check": "fanout",
        "join": join_name,
        "key": key,
        "keys_with_several_rows": sum(1 for row in rows if counts.get(row[key], 0) > 1),
        "correct_sum": measure.show(correct, 2),
        "sum_after_join": measure.show(joined, 2),
        "double_counted": measure.show(joined - correct, 2),
        "multiplies_by": round(float(joined / correct), 4) if correct else None,
    }


def check_windows(spec: dict[str, Any], data: dict[str, measure.Table]) -> dict[str, Any]:
    table_name = spec.get("table")
    if table_name not in data:
        raise SystemExit(f"no table {table_name!r}; have: {', '.join(sorted(data))}")
    table = data[table_name]
    filters = list(spec.get("filters", []))
    date_column, value = spec["date"], spec["value"]
    measure.check_columns(table, [date_column, value])
    rows, _ = measure.apply_filters(table.rows, filters, table)
    periods = spec["periods"]
    out = []
    length = None
    for item in periods:
        frm, to = date.fromisoformat(item["from"]), date.fromisoformat(item["to"])
        member = [r for r in rows if measure.in_window(r[date_column], frm, to)]
        days = (to - frm).days + 1
        length = days if length is None else min(length, days)
        out.append(
            {
                "period": item.get("name", f"{frm}..{to}"),
                "from": item["from"],
                "to": item["to"],
                "days": days,
                "whole_month": whole_month(frm, to),
                "rows": len(member),
                "sum": measure.show(total(member, value), 2),
                "sum_per_day": measure.show(total(member, value) / days, 2),
            }
        )
    like_for_like = []
    for item in periods:
        frm = date.fromisoformat(item["from"])
        to = frm + timedelta(days=(length or 1) - 1)
        member = [r for r in rows if measure.in_window(r[date_column], frm, to)]
        like_for_like.append(
            {
                "period": item.get("name", item["from"]),
                "first_days": length,
                "sum": measure.show(total(member, value), 2),
            }
        )
    return {
        "check": "windows",
        "periods": out,
        "like_for_like": like_for_like,
        "equal_length": len({p["days"] for p in out}) == 1,
    }


CHECKS = {
    "avg_of_averages": check_avg_of_averages,
    "small_groups": check_small_groups,
    "simpson": check_simpson,
    "fanout": check_fanout,
    "windows": check_windows,
}


def run_checks(spec_path: Path, data_dir: Path) -> dict[str, Any]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    data = measure.tables(data_dir)
    results = []
    for item in spec["checks"]:
        name = item.get("check")
        if name not in CHECKS:
            raise SystemExit(f"unknown check {name!r}; use one of {', '.join(CHECKS)}")
        results.append({"name": item.get("name", name), **CHECKS[name](item, data)})
    return {"checks": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a report's SQL and recount its numbers.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sql_cmd = sub.add_parser("sql", help="list places to read in a report's SQL and notebooks")
    sql_cmd.add_argument("report", type=Path)
    sql_cmd.add_argument("--data", type=Path, help="a folder of sample data, to count the NULLs and repeats")
    data_cmd = sub.add_parser("data", help="run checks against sample data")
    data_cmd.add_argument("spec", type=Path)
    data_cmd.add_argument("data", type=Path)
    args = parser.parse_args(argv)
    result = check_sql(args.report, args.data) if args.cmd == "sql" else run_checks(args.spec, args.data)
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
