#!/usr/bin/env python3
"""Profile sample data files for a data platform: shape, keys, overlaps between files and personal data.

Usage: python3 data_profile.py PATH [PATH ...] [--max-rows N]
       python3 data_profile.py PATH [PATH ...] --grain TABLE K1,K2

PATH is a file or a folder of .csv, .tsv, .jsonl or .ndjson files; a file's stem is its table name.
It reports rows, types, nulls, distinct values, ranges, candidate keys, keys that are almost unique, how
columns of the same name overlap between files (orphans and rows a join would multiply), and personal
data by column name and by value checks (e-mail, IBAN, JMBG).

It prints counts, never values of a personal column and never sample rows. Read-only, standard library
only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import re
import sys
from collections import Counter
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

FORMATS = {".csv": "csv", ".tsv": "csv", ".jsonl": "jsonl", ".ndjson": "jsonl"}
MAX_ROWS = 200_000
NULLS = {"", "null", "none", "n/a", "na", "\\n", "nan"}
KEY_NAME = re.compile(r"(^|_)(id|key|code|no|num|number|line|seq|sku|date)$", re.I)
JOIN_NAME = re.compile(r"(^|_)(id|key|code|no|num|number|sku)$", re.I)
PERSONAL_NAMES = [
    ("e-mail", r"e_?mail"),
    ("phone", r"phone|mobile|(^|_)tel(_|$)|telefon"),
    ("national id", r"jmbg|national_?id|(^|_)oib(_|$)|(^|_)ssn(_|$)|personal_?(id|number)|passport|id_?card"),
    ("bank account", r"iban|bank_?account|account_?number"),
    ("address", r"address|adresa|street|ulica|post_?code|zip_?code"),
    ("birth date", r"birth|(^|_)dob(_|$)|rodjenj"),
    ("person name", r"(first|last|full|given|family|customer|contact|person)_?name|surname|(^|_)(ime|prezime)(_|$)"),
    ("ip address", r"(^|_)ip(_?address)?(_|$)"),
]
KINDS = [
    ("code", re.compile(r"^0\d+$")),
    ("integer", re.compile(r"^[+-]?\d+$")),
    ("decimal", re.compile(r"^[+-]?\d+\.\d+$")),
    ("decimal_comma", re.compile(r"^[+-]?\d+,\d+$")),
    ("date_iso", re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    ("datetime", re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")),
    ("date_dmy", re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}\.?$")),
    ("date_slash", re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")),
    ("boolean", re.compile(r"^(true|false)$", re.I)),
]
TYPE_OF = {
    "code": "code",
    "integer": "integer",
    "decimal": "decimal",
    "decimal_comma": "decimal",
    "date_iso": "date",
    "date_dmy": "date",
    "date_slash": "date",
    "datetime": "datetime",
    "boolean": "boolean",
    "text": "text",
}


def is_email(value: str) -> bool:
    return re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value) is not None


def is_jmbg(value: str) -> bool:
    """A Yugoslav national number: thirteen digits, a day and a month, and a valid check digit."""
    if not re.fullmatch(r"\d{13}", value) or not (1 <= int(value[:2]) <= 31 and 1 <= int(value[2:4]) <= 12):
        return False
    d = [int(c) for c in value]
    m = 11 - (sum((7 - i) * (d[i] + d[i + 6]) for i in range(6)) % 11)
    return (0 if m > 9 else m) == d[12]


def is_iban(value: str) -> bool:
    text = value.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", text):
        return False
    return int("".join(str(int(c, 36)) for c in text[4:] + text[:4])) % 97 == 1


VALUE_CHECKS: list[tuple[str, Callable[[str], bool]]] = [
    ("e-mail", is_email),
    ("national id", is_jmbg),
    ("bank account", is_iban),
]


def kind_of(value: str) -> str:
    for name, pattern in KINDS:
        if pattern.match(value):
            return name
    return "text"


def parse_date(value: str, kind: str) -> date | None:
    try:
        if kind == "date_iso":
            return date.fromisoformat(value)
        if kind == "datetime":
            return date.fromisoformat(value[:10])
        if kind in ("date_dmy", "date_slash"):
            day, month, year = re.split(r"[./]", value.rstrip("."))
            return date(int(year), int(month), int(day))
    except ValueError:
        return None
    return None


def read_text(path: Path) -> tuple[str, str | None]:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        return raw.decode("cp1250", errors="replace"), "not UTF-8: read as Windows-1250"


def read_table(path: Path, max_rows: int) -> dict[str, Any]:
    """The header and rows of one file, each row as a list of strings or None."""
    text, note = read_text(path)
    notes = [note] if note else []
    header: list[str] = []
    rows: list[list[str | None]] = []
    total = 0
    bad = 0
    delimiter = None
    if FORMATS[path.suffix.lower()] == "csv":
        first = text.split("\n", 1)[0]
        delimiter = "\t" if path.suffix.lower() == ".tsv" else max(",;\t|", key=first.count)
        reader = csv.reader(text.splitlines(), delimiter=delimiter)
        header = next(reader, [])
        for row in reader:
            if not row:
                continue
            total += 1
            if len(row) != len(header):
                bad += 1
            if len(rows) < max_rows:
                rows.append([*row[: len(header)], *([None] * (len(header) - len(row)))])
    else:
        records: list[dict[str, Any]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            total += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if isinstance(record, dict) and len(records) < max_rows:
                records.append(record)
        header = list(dict.fromkeys(k for record in records for k in record))
        rows = [
            [
                None
                if record.get(k) is None
                else (record[k] if isinstance(record[k], str) else json.dumps(record[k], ensure_ascii=False))
                for k in header
            ]
            for record in records
        ]
    if bad:
        notes.append(f"{bad} row(s) do not have the same number of fields as the header")
    return {"header": header, "rows": rows, "total": total, "delimiter": delimiter, "notes": notes}


def clean(value: str | None) -> str | None:
    if value is None or value.strip().lower() in NULLS:
        return None
    return value.strip()


def personal_of(name: str, values: list[str]) -> dict[str, Any] | None:
    by_name = next((kind for kind, pattern in PERSONAL_NAMES if re.search(pattern, name, re.I)), None)
    sample = values[:2000]
    by_value = None
    hits = 0
    for kind, test in VALUE_CHECKS:
        count = sum(1 for v in sample if test(v))
        if sample and count / len(sample) >= 0.5:
            by_value, hits = kind, count
            break
    if not by_name and not by_value:
        return None
    return {
        "kind": by_value or by_name,
        "found_by": "name and value" if by_name and by_value else "value" if by_value else "name",
        "values_checked": len(sample),
        "values_passing": hits,
    }


def profile_column(name: str, raw: list[str | None]) -> tuple[dict[str, Any], list[str | None]]:
    values = [clean(v) for v in raw]
    present = [v for v in values if v is not None]
    kinds = Counter(kind_of(v) for v in present)
    types = Counter(TYPE_OF[k] for k, n in kinds.items() for _ in range(n))
    dominant = "text"
    if types:
        dominant = types.most_common(1)[0][0]
        if dominant == "integer" and types.get("decimal"):
            dominant = "decimal"
    personal = personal_of(name, present)
    column: dict[str, Any] = {
        "name": name,
        "type": dominant,
        "nulls": len(values) - len(present),
        "null_pct": round(100 * (len(values) - len(present)) / len(values), 1) if values else 0.0,
        "distinct": len(set(present)),
        "max_length": max((len(v) for v in present), default=0),
    }
    issues = []
    if kinds.get("decimal_comma"):
        dotted = kinds.get("decimal", 0)
        issues.append(f"decimal comma in {kinds['decimal_comma']} values, decimal point in {dotted}")
    formats = {k: n for k, n in kinds.items() if k in ("date_iso", "date_dmy", "date_slash")}
    if len(formats) > 1:
        issues.append("mixed date formats: " + ", ".join(f"{k} {n}" for k, n in sorted(formats.items())))
    other = sum(n for t, n in types.items() if t != dominant and not {t, dominant} <= {"integer", "decimal", "code"})
    if other:
        issues.append(f"{other} values do not look like {dominant}")
    if issues:
        column["issues"] = issues
    if personal:
        column["personal"] = personal
    else:
        if dominant in ("integer", "decimal"):
            numbers = [float(v.replace(",", ".")) for v in present if kind_of(v) in TYPE_OF and _numeric(v)]
            if numbers:
                column["min"], column["max"] = min(numbers), max(numbers)
        elif dominant in ("date", "datetime"):
            dates = [d for d in (parse_date(v, kind_of(v)) for v in present) if d]
            if dates:
                column["min"], column["max"] = min(dates).isoformat(), max(dates).isoformat()
    return column, values


def _numeric(value: str) -> bool:
    return kind_of(value) in ("integer", "decimal", "decimal_comma", "code")


def keys_of(names: list[str], columns: dict[str, list[str | None]], rows: int) -> list[list[str]]:
    """Single columns, then pairs and triples of key-like columns, that are unique and never empty."""
    if not rows:
        return []

    def unique(combo: tuple[str, ...]) -> bool:
        seen: set[tuple[str | None, ...]] = set()
        for row in zip(*(columns[c] for c in combo), strict=True):
            if None in row or row in seen:
                return False
            seen.add(row)
        return True

    found = [[n] for n in names if unique((n,))]
    single = {key[0] for key in found}
    keyish = [n for n in names if KEY_NAME.search(n) and n not in single][:8]
    for size in (2, 3):
        if size == 3 and any(len(key) == 2 for key in found):
            break
        found += [list(c) for c in itertools.combinations(keyish, size) if unique(c)]
    return found[:8]


def profile_file(path: Path, max_rows: int) -> tuple[dict[str, Any], dict[str, list[str | None]]]:
    table = read_table(path, max_rows)
    header: list[str] = table["header"]
    rows: list[list[str | None]] = table["rows"]
    profiles = []
    cleaned: dict[str, list[str | None]] = {}
    for i, name in enumerate(header):
        column, values = profile_column(name, [row[i] for row in rows])
        profiles.append(column)
        cleaned[name] = values
    almost = [
        {"column": c["name"], "rows": len(rows), "distinct": c["distinct"], "duplicate_rows": len(rows) - c["distinct"]}
        for c in profiles
        if JOIN_NAME.search(c["name"]) and rows and c["nulls"] == 0 and 0.95 <= c["distinct"] / len(rows) < 1
    ]
    return {
        "table": path.stem,
        "path": str(path),
        "bytes": path.stat().st_size,
        "rows": table["total"],
        "rows_read": len(rows),
        "sampled": len(rows) < table["total"],
        "delimiter": table["delimiter"],
        "columns": profiles,
        "candidate_keys": keys_of(header, cleaned, len(rows)),
        "almost_keys": almost,
        "notes": table["notes"],
    }, cleaned


def overlaps(files: list[dict[str, Any]], data: dict[str, dict[str, list[str | None]]]) -> list[dict[str, Any]]:
    """For columns of the same key-like name in two files: orphans, and how many rows a left join would give."""
    found = []
    for left, right in itertools.combinations(files, 2):
        for name in sorted(set(data[left["table"]]) & set(data[right["table"]])):
            if not JOIN_NAME.search(name):
                continue
            ratio = {
                f["table"]: (len({v for v in data[f["table"]][name] if v is not None}) / f["rows_read"])
                for f in (left, right)
                if f["rows_read"]
            }
            if len(ratio) < 2:
                continue
            source, target = (left, right) if ratio[left["table"]] <= ratio[right["table"]] else (right, left)
            values = [v for v in data[source["table"]][name] if v is not None]
            counts = Counter(v for v in data[target["table"]][name] if v is not None)
            distinct = set(values)
            orphans = sum(1 for v in values if v not in counts)
            after = sum(max(1, counts.get(v, 0)) for v in values)
            found.append(
                {
                    "column": name,
                    "from": source["table"],
                    "to": target["table"],
                    "from_rows": len(values),
                    "from_distinct": len(distinct),
                    "matched_distinct": len(distinct & set(counts)),
                    "orphan_rows": orphans,
                    "to_is_unique": max(counts.values(), default=0) <= 1,
                    "max_matches": max(counts.values(), default=0),
                    "rows_after_left_join": after,
                    "multiplies_by": round(after / len(values), 2) if values else 1.0,
                }
            )
    return found


def grain(table: str, columns: list[str], data: dict[str, dict[str, list[str | None]]]) -> dict[str, Any]:
    if table not in data:
        raise SystemExit(f"--grain: no table {table!r} among {', '.join(sorted(data))}")
    missing = [c for c in columns if c not in data[table]]
    if missing:
        raise SystemExit(f"--grain: {table} has no column {', '.join(missing)}")
    rows = list(zip(*(data[table][c] for c in columns), strict=True))
    empty = sum(1 for row in rows if None in row)
    counts = Counter(row for row in rows if None not in row)
    return {
        "table": table,
        "columns": columns,
        "rows": len(rows),
        "rows_with_an_empty_key": empty,
        "distinct_keys": len(counts),
        "duplicate_keys": sum(1 for n in counts.values() if n > 1),
        "rows_in_duplicates": sum(n for n in counts.values() if n > 1),
        "holds": empty == 0 and all(n == 1 for n in counts.values()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile sample data files for a data platform.")
    parser.add_argument("paths", nargs="+", type=Path, help="files or folders")
    parser.add_argument("--max-rows", type=int, default=MAX_ROWS, help="rows profiled per file; all are counted")
    parser.add_argument("--grain", nargs=2, metavar=("TABLE", "COLUMNS"), help="check a grain: table and k1,k2")
    args = parser.parse_args(argv)
    targets: list[Path] = []
    for path in args.paths:
        if path.is_dir():
            targets += sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in FORMATS)
        elif path.is_file() and path.suffix.lower() in FORMATS:
            targets.append(path)
        else:
            print(f"not a data file or folder: {path}", file=sys.stderr)
            return 2
    files = []
    data: dict[str, dict[str, list[str | None]]] = {}
    for path in targets:
        profile, cleaned = profile_file(path, args.max_rows)
        files.append(profile)
        data[profile["table"]] = cleaned
    result: dict[str, Any] = {
        "totals": {"files": len(files), "bytes": sum(f["bytes"] for f in files), "rows": sum(f["rows"] for f in files)},
        "files": files,
        "overlaps": overlaps(files, data),
    }
    if args.grain:
        result["grain"] = grain(args.grain[0], [c.strip() for c in args.grain[1].split(",")], data)
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
