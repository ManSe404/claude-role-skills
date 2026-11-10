#!/usr/bin/env python3
"""Read how a new source writes its files, and where that differs from its vendor's document and earlier deliveries.

Usage: python3 source_format.py DELIVERY [DELIVERY ...] [--doc VENDOR.md] [--max-rows N]

DELIVERY is a folder of one delivery (or one file) of .csv, .tsv, .txt, .jsonl or .ndjson files. Give several oldest
first: the last is the delivery read in full, the earlier ones are compared with it.

Per file: encoding, byte order mark, line endings, delimiter, quoted fields, rows whose field count differs from the
header. Per column: the decimal separator and thousands separators of numbers, the date formats, the tokens written
for "no value" (empty, NULL, N/A, -), placeholder values such as 9999-12-31 or 1900-01-01, delete markers, and the
values of short code columns. Per file with an id in its first column: duplicated keys and which columns differ
between the copies; ids that point to another file of the delivery and find nothing there (orphans); weekdays with no
rows in a date column that spans a few weeks.
Against earlier deliveries: columns added, removed or moved, rows, keys gone from a full extract, and weekdays with no
delivery folder when the folder names are dates.
With --doc (the vendor's Markdown document): the columns it lists per file against the delivered ones, and its claims
about delimiter, decimal separator, date format, encoding and empty values, codes and lists of values, each compared
with the data and put under conflicts or consistent.

It prints column names, counts, null tokens and placeholders, never a value of a personal column and never a row.
Key examples and code values only come from files and columns without personal data. Read-only, standard library
only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_profile

SUFFIXES = {".csv": "csv", ".tsv": "csv", ".txt": "csv", ".jsonl": "jsonl", ".ndjson": "jsonl"}
NULL_TOKENS = {
    "", "null", "none", "nil", "n/a", "na", "n.a.", "-", "--", "?", "\\n", "nan", "#n/a", "(null)", "undefined",
    "unknown", "tbd", "missing",
}  # fmt: skip
JSON_NULL = "null (JSON)"
KEY_NAME = re.compile(r"(^|_)(id|key|code|no|number)$", re.I)
LINE_NAME = re.compile(r"(^|_)(line|line_no|line_number|seq|pos|position|item)$", re.I)
DATE_NAME = re.compile(r"date|(^|_)(on|at|day|dt)$", re.I)
DELETE_NAME = re.compile(
    r"^(is_)?deleted(_at|_flag)?$|^(_)?op(_type)?$|^(cdc_)?operation$|^change_type$|^action$", re.I
)
DELETE_VALUES = {"d", "del", "delete", "deleted", "true", "1", "y", "yes"}
NUMBER_SHAPES = [
    ("integer", re.compile(r"^[+-]?\d+$")),
    ("decimal_point", re.compile(r"^[+-]?\d+\.\d+$")),
    ("decimal_comma", re.compile(r"^[+-]?\d+,\d+$")),
    ("thousands_point_decimal_comma", re.compile(r"^[+-]?\d{1,3}(\.\d{3})+,\d+$")),
    ("thousands_comma_decimal_point", re.compile(r"^[+-]?\d{1,3}(,\d{3})+\.\d+$")),
    ("thousands_space", re.compile(r"^[+-]?\d{1,3}( \d{3})+([.,]\d+)?$")),
]
DATE_SHAPES = [
    ("YYYY-MM-DD", re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), "ymd"),
    ("YYYY-MM-DDThh:mm", re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ]\d{2}:\d{2}"), "ymd"),
    ("DD.MM.YYYY", re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})\.?$"), "dmy"),
    ("DD-MM-YYYY", re.compile(r"^(\d{2})-(\d{2})-(\d{4})$"), "dmy"),
    ("YYYY/MM/DD", re.compile(r"^(\d{4})/(\d{2})/(\d{2})$"), "ymd"),
    ("NN/NN/YYYY", re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$"), "slash"),
    ("YYYYMMDD", re.compile(r"^(\d{4})(\d{2})(\d{2})$"), "ymd"),
]
PLACEHOLDER_DATES = {"1970-01-01", "0001-01-01", "0000-00-00", "1899-12-30", "1899-12-31"}
DOC_DATE = re.compile(r"\b(YYYY-MM-DD|DD\.MM\.YYYY|MM/DD/YYYY|DD/MM/YYYY|YYYYMMDD|DD-MM-YYYY)\b")
DOC_ENCODING = re.compile(r"\b(UTF-?8|UTF-?16|Windows-125\d|cp125\d|ISO-8859-\d+|latin-?1)\b", re.I)
DOC_DELIMITERS = {"comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|"}
SHORT = 12


@dataclass
class Table:
    name: str
    path: Path
    kind: str
    header: list[str] = field(default_factory=list)
    rows: list[list[str | None]] = field(default_factory=list)
    total: int = 0
    encoding: str = "utf-8"
    bom: bool = False
    line_endings: str = "none"
    delimiter: str | None = None
    quoted_fields: int = 0
    ragged_rows: int = 0
    notes: list[str] = field(default_factory=list)
    personal: dict[str, str] = field(default_factory=dict)

    def column(self, name: str) -> list[str | None]:
        i = self.header.index(name)
        return [row[i] for row in self.rows]


# ---------------------------------------------------------------------------- reading


def decode(raw: bytes) -> tuple[str, str, bool]:
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace"), "utf-16", True
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        return raw.decode("utf-8-sig"), "utf-8", bom
    except UnicodeDecodeError:
        return raw.decode("cp1250", errors="replace"), "not utf-8 (read as windows-1250)", bom


def read(path: Path, max_rows: int) -> Table:
    raw = path.read_bytes()
    text, encoding, bom = decode(raw)
    crlf, lf = raw.count(b"\r\n"), raw.count(b"\n")
    endings = "CRLF" if crlf and crlf == lf else "mixed" if crlf else "LF" if lf else "none"
    table = Table(path.stem, path, SUFFIXES[path.suffix.lower()], encoding=encoding, bom=bom, line_endings=endings)
    if table.kind == "csv":
        first = text.split("\n", 1)[0]
        delimiter = "\t" if path.suffix.lower() == ".tsv" else max(",;\t|", key=first.count)
        table.delimiter = delimiter
        table.quoted_fields = len(re.findall(rf'(?:^|{re.escape(delimiter)})"', text, re.M))
        reader = csv.reader(text.splitlines(), delimiter=delimiter)
        table.header = [h.strip() for h in next(reader, [])]
        for row in reader:
            if not row:
                continue
            table.total += 1
            if len(row) != len(table.header):
                table.ragged_rows += 1
            if len(table.rows) < max_rows:
                table.rows.append([*row[: len(table.header)], *([None] * (len(table.header) - len(row)))])
    else:
        records: list[dict[str, Any]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            table.total += 1
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                table.ragged_rows += 1
                continue
            if isinstance(record, dict) and len(records) < max_rows:
                records.append(record)
        table.header = list(dict.fromkeys(k for r in records for k in r))
        table.rows = [[json_cell(r, k) for k in table.header] for r in records]
    if table.ragged_rows:
        table.notes.append(f"{table.ragged_rows} row(s) do not have as many fields as the header")
    for name in table.header:
        present = [v.strip() for v in table.column(name) if v is not None and v.strip().lower() not in NULL_TOKENS]
        found = data_profile.personal_of(name, present)
        if found:
            table.personal[name] = str(found["kind"])
    return table


def json_cell(record: dict[str, Any], key: str) -> str | None:
    if key not in record:
        return ""
    value = record[key]
    if value is None:
        return None
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def files_of(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() in SUFFIXES else []
    return sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in SUFFIXES)


# ---------------------------------------------------------------------------- one column


def private(value: str) -> bool:
    return any(check(value) for _, check in data_profile.VALUE_CHECKS)


def number_shape(value: str) -> str | None:
    return next((name for name, pattern in NUMBER_SHAPES if pattern.match(value)), None)


def date_shape(value: str, name: str) -> tuple[str, date | None] | None:
    for label, pattern, order in DATE_SHAPES:
        match = pattern.match(value)
        if not match:
            continue
        if label == "YYYYMMDD" and not DATE_NAME.search(name):
            return None
        a, b, c = (int(g) for g in match.groups())
        if order == "ymd":
            year, month, day = a, b, c
        elif order == "dmy":
            day, month, year = a, b, c
        else:
            label = "DD/MM/YYYY" if a > 12 else "MM/DD/YYYY" if b > 12 else label
            day, month, year = (a, b, c) if a > 12 else (b, a, c)
        try:
            return label, date(year, month, day)
        except ValueError:
            return label, None
    return None


def placeholder(value: str, parsed: date | None) -> bool:
    if value[:10] in PLACEHOLDER_DATES:
        return True
    return parsed is not None and (parsed.year >= 2900 or parsed.year <= 1900)


def column_report(table: Table, name: str) -> dict[str, Any]:
    raw = table.column(name)
    personal = table.personal.get(name)
    tokens: Counter[str] = Counter()
    present: list[str] = []
    for value in raw:
        if value is None:
            tokens[JSON_NULL] += 1
        elif value.strip().lower() in NULL_TOKENS:
            tokens["" if not value.strip() else value.strip()] += 1
        else:
            present.append(value.strip())
    report: dict[str, Any] = {"name": name, "rows": len(raw), "values": len(present), "distinct": len(set(present))}
    if personal:
        report["personal"] = personal
    if tokens:
        report["empty"] = sum(tokens.values())
        if len(tokens) > 1 or set(tokens) - {""}:
            report["null_tokens"] = dict(tokens.most_common())
    if not present:
        report["empty_in_all_rows"] = True
        return report
    if table.delimiter:
        inside = sum(1 for v in present if table.delimiter in v)
        if inside:
            report["values_holding_the_delimiter"] = inside
    shapes = Counter(number_shape(v) for v in present)
    numeric = sum(n for s, n in shapes.items() if s)
    dates: Counter[str] = Counter()
    holders: Counter[str] = Counter()
    for value in present:
        found = date_shape(value, name)
        if found:
            dates[found[0]] += 1
            if placeholder(value, found[1]):
                holders[value] += 1
    if dates and sum(dates.values()) >= 0.8 * len(present) and not (set(dates) <= {"YYYYMMDD"} and numeric):
        report["date_formats"] = dict(dates.most_common())
        if holders:
            report["placeholders"] = dict(holders.most_common())
        report["kind"] = "date"
    elif numeric >= 0.8 * len(present):
        formats = {s: n for s, n in shapes.items() if s and s != "integer"}
        point = formats.get("decimal_point", 0) + formats.get("thousands_comma_decimal_point", 0)
        comma = formats.get("decimal_comma", 0) + formats.get("thousands_point_decimal_comma", 0)
        thousands = sum(n for s, n in formats.items() if s.startswith("thousands"))
        report["kind"] = "number"
        report["numbers"] = {"integer": shapes.get("integer", 0), "decimal_point": point, "decimal_comma": comma}
        if thousands:
            report["numbers"]["thousands_separator"] = thousands
        nines = Counter(v for v in present if re.fullmatch(r"9{4,}([.,]9+)?|9{4,}[.,]0+", v))
        if nines:
            report["placeholders"] = dict(nines)
        if numeric < len(present):
            report["not_numbers"] = len(present) - numeric
    else:
        report["kind"] = "text"
    if DELETE_NAME.search(name):
        report["delete_marker"] = True
    if not personal and 1 <= len(set(present)) <= SHORT and len(present) >= 10 and report["kind"] != "date":
        counts = Counter(present)
        if not any(private(v) or len(v) > 40 for v in counts):
            report["codes"] = dict(counts.most_common())
    return report


# ---------------------------------------------------------------------------- one file and the delivery


def key_of(table: Table) -> list[str]:
    """The id in the first column, with the second when only the two together are unique (an order and its line)."""
    if not table.header or not KEY_NAME.search(table.header[0]):
        return []
    first = table.column(table.header[0])
    if len(set(first)) == len(first) or len(table.header) < 2 or not LINE_NAME.search(table.header[1]):
        return [table.header[0]]
    pairs = list(zip(first, table.column(table.header[1]), strict=True))
    return table.header[:2] if len(set(pairs)) == len(pairs) else [table.header[0]]


def key_report(table: Table) -> dict[str, Any] | None:
    key = key_of(table)
    if not key:
        return None
    index = [table.header.index(k) for k in key]
    values = ["|".join(row[i] or "" for i in index) for row in table.rows]
    counts = Counter(v for v in values if v.strip("|"))
    duplicated = sorted(k for k, n in counts.items() if n > 1)
    report: dict[str, Any] = {
        "columns": key,
        "rows": len(values),
        "empty": sum(1 for v in values if not v.strip("|")),
        "distinct": len(counts),
        "duplicated_keys": len(duplicated),
        "rows_in_duplicates": sum(counts[k] for k in duplicated),
    }
    if duplicated:
        differ: Counter[str] = Counter()
        identical = 0
        for k in duplicated:
            copies = [row for row, v in zip(table.rows, values, strict=True) if v == k]
            changed = [name for j, name in enumerate(table.header) if len({row[j] for row in copies}) > 1]
            differ.update(changed)
            identical += not changed
        report["columns_that_differ"] = dict(differ.most_common())
        report["identical_copies"] = identical
        if not table.personal:
            report["examples"] = duplicated[:5]
    return report


def references(tables: list[Table]) -> list[dict[str, Any]]:
    """Ids in one file that point to the key column of another file of the same delivery and find nothing there."""
    keys = {key_of(t)[0]: t for t in tables if key_of(t)}
    found = []
    for table in tables:
        own = key_of(table)
        for name in table.header:
            parent = keys.get(name)
            if name in own or parent is None or parent is table:
                continue
            known = {v for v in parent.column(name) if v}
            values = [v for v in table.column(name) if v]
            orphans = [v for v in values if v not in known]
            found.append(
                {
                    "file": table.path.name,
                    "column": name,
                    "points_to": parent.path.name,
                    "rows_with_a_value": len(values),
                    "empty": len(table.rows) - len(values),
                    "orphan_rows": len(orphans),
                    "orphan_ids": len(set(orphans)),
                }
            )
    return found


def weekday_gaps(table: Table, report: dict[str, Any]) -> dict[str, Any] | None:
    """Weekdays with no rows inside the span of a date column that covers between two days and three months."""
    days = set()
    for value in table.column(report["name"]):
        found = date_shape(value.strip(), report["name"]) if value else None
        if found and found[1] and not placeholder(value or "", found[1]):
            days.add(found[1])
    if len(days) < 2 or (max(days) - min(days)).days > 92:
        return None
    span = [min(days) + timedelta(n) for n in range((max(days) - min(days)).days + 1)]
    missing = [d.isoformat() for d in span if d.weekday() < 5 and d not in days]
    return {
        "column": report["name"],
        "from": min(days).isoformat(),
        "to": max(days).isoformat(),
        "weekdays_without_rows": missing,
    }


def file_report(table: Table) -> dict[str, Any]:
    columns = [column_report(table, name) for name in table.header]
    report: dict[str, Any] = {
        "file": table.path.name,
        "format": table.kind,
        "rows": table.total,
        "rows_read": len(table.rows),
        "encoding": table.encoding,
        "byte_order_mark": table.bom,
        "line_endings": table.line_endings,
        "delimiter": table.delimiter,
        "quoted_fields": table.quoted_fields,
        "ragged_rows": table.ragged_rows,
        "columns": columns,
    }
    if table.personal:
        report["personal_columns"] = table.personal
    key = key_report(table)
    if key:
        report["key"] = key
    gaps = [g for g in (weekday_gaps(table, c) for c in columns if c.get("kind") == "date") if g]
    if gaps:
        report["date_spans"] = gaps
    if table.notes:
        report["notes"] = table.notes
    return report


# ---------------------------------------------------------------------------- earlier deliveries


def as_day(path: Path) -> date | None:
    match = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", path.name)
    if not match:
        return None
    try:
        return date(*(int(g) for g in match.groups()))
    except ValueError:
        return None


def style(table: Table, name: str) -> str:
    """How a column writes its values, in a word: the decimal separator of numbers, the main format of dates."""
    report = column_report(table, name)
    if report.get("kind") == "date":
        return str(max(report["date_formats"].items(), key=lambda kv: kv[1])[0])
    numbers = report.get("numbers")
    if numbers and (numbers["decimal_point"] or numbers["decimal_comma"]):
        return "decimal comma" if numbers["decimal_comma"] > numbers["decimal_point"] else "decimal point"
    return str(report.get("kind", "empty"))


def history(deliveries: list[Path], latest: dict[str, Table], max_rows: int) -> dict[str, Any]:
    steps = []
    previous: dict[str, Table] | None = None
    sets = [{t.path.name: t for t in (read(p, max_rows) for p in files_of(d))} for d in deliveries[:-1]]
    sets.append(latest)
    for folder, tables in zip(deliveries, sets, strict=True):
        step: dict[str, Any] = {"delivery": folder.as_posix(), "files": {}}
        for name, table in sorted(tables.items()):
            entry: dict[str, Any] = {"rows": table.total, "delimiter": table.delimiter}
            if previous is not None and name in previous:
                before = previous[name]
                added = [c for c in table.header if c not in before.header]
                removed = [c for c in before.header if c not in table.header]
                common = [c for c in table.header if c in before.header]
                entry |= {"added": added, "removed": removed}
                entry["moved"] = common != [c for c in before.header if c in table.header]
                if before.delimiter != table.delimiter:
                    entry["delimiter_before"] = before.delimiter
                changes = {c: f"{a} -> {b}" for c in common if (a := style(before, c)) != (b := style(table, c))}
                if changes:
                    entry["format_changes"] = changes
                key = key_of(table)
                if key and key == key_of(before):
                    old = {v for v in before.column(key[0]) if v}
                    new = {v for v in table.column(key[0]) if v}
                    if old & new:  # a full extract: a key that is gone was deleted at the source
                        entry["keys_new"], entry["keys_gone"] = len(new - old), len(old - new)
                    else:
                        entry["incremental"] = True  # no key in common: each delivery holds new rows only
            elif previous is not None:
                entry["new_file"] = True
            step["files"][name] = entry
        if previous is not None:
            step["files_gone"] = sorted(set(previous) - set(tables))
        steps.append(step)
        previous = tables
    days = [d for d in (as_day(p) for p in deliveries) if d]
    missing: list[str] = []
    if len(days) == len(deliveries) and len(days) > 1:
        span = [min(days) + timedelta(n) for n in range((max(days) - min(days)).days + 1)]
        missing = [d.isoformat() for d in span if d.weekday() < 5 and d not in days]
    return {"deliveries": steps, "weekdays_without_a_delivery": missing}


# ---------------------------------------------------------------------------- the vendor's document


def parse_doc(text: str, names: list[str]) -> dict[str, Any]:
    stems = {Path(n).stem: n for n in names}
    sections: dict[str, dict[str, dict[str, str]]] = {}
    current = ""
    for line in text.splitlines():
        heading = re.match(r"^#{1,4}\s+`?([\w.-]+?)`?\s*$", line)
        if heading:
            word = heading.group(1)
            current = stems.get(Path(word).stem, word if Path(word).suffix.lower() in SUFFIXES else "")
            if current:
                sections.setdefault(current, {})
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.lstrip().startswith("|") else []
        if current and len(cells) >= 2:
            column = cells[0].strip("`").strip()
            if re.fullmatch(r"\w+", column) and column.lower() not in ("column", "name", "field"):
                meaning = cells[2] if len(cells) > 2 else ""
                sections[current][column] = {"type": cells[1].strip("`").lower(), "meaning": meaning}
    claims: dict[str, Any] = {}
    delimiter = re.search(r"\b(comma|semicolon|tab|pipe)[- ](separated|delimited)", text, re.I)
    if delimiter:
        claims["delimiter"] = DOC_DELIMITERS[delimiter.group(1).lower()]
    decimal = re.search(r"\bdecimal (point|comma)\b", text, re.I)
    if decimal:
        claims["decimal"] = decimal.group(1).lower()
    formats = sorted(set(DOC_DATE.findall(text)))
    if formats:
        claims["date_formats"] = formats
    encoding = DOC_ENCODING.search(text)
    if encoding:
        claims["encoding"] = encoding.group(1)
    by = re.search(r"\bby (\d{1,2}:\d{2})\b", text)
    if by:
        claims["deliver_by"] = by.group(1)
    return {"claims": claims, "sections": sections}


def documented_values(meaning: str) -> list[str]:
    """`A active, I inactive, X closed by ...` gives A, I, X; `sr, hu or en` gives sr, hu, en."""
    head = re.split(r"[;.(]", meaning, maxsplit=1)[0]
    parts = [p.strip() for p in re.split(r",\s*|\s+or\s+", head) if p.strip()]
    if len(parts) < 2:
        return []
    if all(re.fullmatch(r"[\w-]+", p) for p in parts):
        return parts
    firsts = [p.split()[0] for p in parts]
    if all(len(f) <= 3 and len(p.split()) > 1 for f, p in zip(firsts, parts, strict=True)):
        return firsts
    return []


def compare_doc(doc: dict[str, Any], tables: dict[str, Table], reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    claims = doc["claims"]
    conflicts: list[dict[str, Any]] = []
    consistent: list[dict[str, Any]] = []
    not_delivered: list[str] = []
    not_documented: list[str] = []
    for name, table in sorted(tables.items()):
        stem = Path(name).stem
        documented = doc["sections"].get(name)
        if documented is None:
            conflicts.append({"what": "file not in the document", "file": name})
            continue
        not_delivered += [f"{stem}.{c}" for c in documented if c not in table.header]
        not_documented += [f"{stem}.{c}" for c in table.header if c not in documented]
        if claims.get("delimiter") and table.delimiter and claims["delimiter"] != table.delimiter:
            conflicts.append(
                {"what": "delimiter", "file": name, "document": claims["delimiter"], "data": table.delimiter}
            )
        if claims.get("encoding") and claims["encoding"].lower().startswith("utf") != (table.encoding == "utf-8"):
            conflicts.append({"what": "encoding", "file": name, "document": claims["encoding"], "data": table.encoding})
        columns = {c["name"]: c for c in reports[name]["columns"]}
        for column, spec in documented.items():
            seen = columns.get(column)
            if seen is not None:
                conflicts += column_conflicts(stem, column, spec, seen, claims, consistent)
    return {
        "claims": claims,
        "files_documented": sorted(doc["sections"]),
        "documented_not_delivered": sorted(not_delivered),
        "delivered_not_documented": sorted(not_documented),
        "conflicts": conflicts,
        "consistent": consistent,
    }


def column_conflicts(
    stem: str, column: str, spec: dict[str, str], seen: dict[str, Any], claims: dict[str, Any], ok: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    where = f"{stem}.{column}"
    found: list[dict[str, Any]] = []
    numbers = seen.get("numbers", {})
    if claims.get("decimal") == "point" and numbers.get("decimal_comma"):
        found.append({"what": "decimal separator", "column": where, "document": "decimal point", "data": numbers})
    if claims.get("decimal") == "comma" and numbers.get("decimal_point"):
        found.append({"what": "decimal separator", "column": where, "document": "decimal comma", "data": numbers})
    formats = seen.get("date_formats", {})
    other = {f: n for f, n in formats.items() if f.split("T")[0] not in claims.get("date_formats", [f.split("T")[0]])}
    if other:
        found.append({"what": "date format", "column": where, "document": claims.get("date_formats"), "data": formats})
    meaning = spec["meaning"].lower()
    may_be_empty = bool(re.search(r"\bempty\b|\boptional\b", meaning))
    holders = seen.get("placeholders", {})
    if may_be_empty and holders and not seen.get("empty"):
        found.append(
            {
                "what": "placeholder where the document says empty",
                "column": where,
                "document": spec["meaning"],
                "data": {"placeholders": holders, "empty": 0},
            }
        )
    elif may_be_empty and seen.get("empty_in_all_rows"):
        ok.append({"what": "documented as possibly empty, and empty in every row", "column": where})
    tokens = seen.get("null_tokens")
    if tokens:
        found.append({"what": "no value written in several ways", "column": where, "data": tokens})
    allowed = documented_values(spec["meaning"])
    codes = seen.get("codes")
    if allowed and codes:
        extra = {v: n for v, n in codes.items() if v not in allowed}
        if extra:
            found.append(
                {"what": "values the document does not list", "column": where, "document": allowed, "data": extra}
            )
        else:
            ok.append({"what": "every value is documented", "column": where, "document": allowed, "data": codes})
    return found


# ---------------------------------------------------------------------------- the hits


def hits_of(result: dict[str, Any]) -> list[str]:
    hits = []
    for report in result["files"]:
        name = report["file"]
        if report["encoding"] != "utf-8" or report["byte_order_mark"]:
            hits.append(f"{name}: encoding {report['encoding']}, byte order mark {report['byte_order_mark']}")
        if report.get("personal_columns"):
            counts = {c["name"]: c["values"] for c in report["columns"] if c["name"] in report["personal_columns"]}
            hits.append(f"{name}: personal columns, values per column {counts}")
        if report["ragged_rows"]:
            hits.append(f"{name}: {report['ragged_rows']} rows with a different number of fields")
        for column in report["columns"]:
            where = f"{name} {column['name']}"
            numbers = column.get("numbers", {})
            if numbers.get("decimal_comma"):
                hits.append(f"{where}: decimal comma in {numbers['decimal_comma']} values")
            if len(column.get("date_formats", {})) > 1:
                hits.append(f"{where}: date formats {column['date_formats']}")
            if column.get("null_tokens"):
                hits.append(f"{where}: no value written as {column['null_tokens']}")
            if column.get("placeholders"):
                hits.append(f"{where}: placeholders {column['placeholders']}")
            if column.get("delete_marker"):
                hits.append(f"{where}: a delete marker column")
        key = report.get("key")
        if key and key["duplicated_keys"]:
            hits.append(f"{name} {'+'.join(key['columns'])}: {key['duplicated_keys']} keys delivered more than once")
        for span in report.get("date_spans", []):
            if span["weekdays_without_rows"]:
                hits.append(f"{name} {span['column']}: {len(span['weekdays_without_rows'])} weekdays without rows")
    for ref in result["references"]:
        if ref["orphan_rows"]:
            hits.append(
                f"{ref['file']} {ref['column']}: {ref['orphan_rows']} rows point to no row of {ref['points_to']}"
            )
    for step in result.get("history", {}).get("deliveries", []):
        for name, entry in step["files"].items():
            if entry.get("added") or entry.get("removed") or entry.get("moved"):
                hits.append(f"{step['delivery']} {name}: columns added {entry['added']}, removed {entry['removed']}")
            if entry.get("format_changes"):
                hits.append(f"{step['delivery']} {name}: format changed {entry['format_changes']}")
            if entry.get("keys_gone"):
                hits.append(f"{step['delivery']} {name}: {entry['keys_gone']} keys gone since the delivery before")
    doc = result.get("doc")
    if doc:
        hits += [f"document: {c['what']} {c.get('file') or c.get('column')}" for c in doc["conflicts"]]
        hits += [f"document lists {c}, not delivered" for c in doc["documented_not_delivered"]]
        hits += [f"delivered {c}, not in the document" for c in doc["delivered_not_documented"]]
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("deliveries", nargs="+", type=Path, help="delivery folders or files, oldest first")
    parser.add_argument("--doc", type=Path, help="the vendor's Markdown document of the source")
    parser.add_argument("--max-rows", type=int, default=200_000, help="rows read per file; all are counted")
    args = parser.parse_args(argv)
    for path in args.deliveries:
        if not path.exists() or not files_of(path):
            print(f"no data files in {path}", file=sys.stderr)
            return 2
    latest = {t.path.name: t for t in (read(p, args.max_rows) for p in files_of(args.deliveries[-1]))}
    reports = {name: file_report(table) for name, table in sorted(latest.items())}
    result: dict[str, Any] = {
        "delivery": args.deliveries[-1].as_posix(),
        "understood": {
            "files": {
                name: f"{t.kind}, delimiter {t.delimiter!r}" if t.delimiter else t.kind for name, t in latest.items()
            },
            "earlier_deliveries": [p.as_posix() for p in args.deliveries[:-1]],
            "document": args.doc.as_posix() if args.doc else None,
        },
        "files": list(reports.values()),
        "references": references(list(latest.values())),
    }
    if len(args.deliveries) > 1:
        result["history"] = history(args.deliveries, latest, args.max_rows)
    if args.doc:
        doc = parse_doc(args.doc.read_text(encoding="utf-8", errors="replace"), sorted(latest))
        result["doc"] = compare_doc(doc, latest, reports)
        result["understood"]["document"] = f"{args.doc.as_posix()}: {len(doc['sections'])} file sections"
    result["hits"] = hits_of(result)
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
