#!/usr/bin/env python3
"""Check a data contract against what the source really delivers, or draft one from the deliveries.

Usage: python3 contract_check.py check CONTRACT.yaml [--root DIR] [--data FILE ...] [--deliveries LOG] [--doc DOC.md]
       python3 contract_check.py draft DATA [DATA ...] [--deliveries LOG] [--doc DOC.md]

check reads the contract (YAML: the flat shapes of a contract file, with `columns` or `fields` as a list or a mapping,
a `key`, `quality` rules, an owner, a change process and a delivery block) and compares it with:
- the delivered files: those its delivery path matches under --root (a `{date}` in the path stands for the day), or
  the files given with --data. Per file: delimiter, encoding, the columns missing from the file and the ones the
  contract does not list, values that break a column's type, format, `required` or `allowed` list (counted, with the
  shape of the breaking values such as 9,99), duplicated keys, and the `quality` rules it can read (a comparison with a
  number, a list of columns that are unique together, a column that must be filled).
- the delivery log (--deliveries, JSON Lines or CSV with a file and an arrival time): arrivals per day against
  `deliver_by` in the contract's time zone, late days with the earliest and the latest late arrival, the weekdays of
  the late and the on-time days, days with no delivery.
- the source's metadata document (--doc, Markdown with a table of columns under a heading per file): columns it lists
  that the contract leaves out and the other way round, and its claims on delimiter, decimal separator, date format
  and delivery time against the contract's.
It also lists what the contract leaves open: an owner or change process that is empty or TBD, no deliver_by, no key.

draft profiles the delivered files (a folder per delivery, oldest first, or files) and proposes a contract's content:
per file the format, per column the type, the format, whether it is always filled, its values when it is a short code
list, which columns are personal; key candidates; with --deliveries the arrival times; with --doc the conflicts
between the document and the data.

It prints column names, counts, shapes and codes, never a value of a personal column and never a row. Read-only,
standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_profile

DATA_SUFFIXES = {".csv", ".tsv", ".txt", ".jsonl", ".ndjson"}
EMPTY = {"", "tbd", "todo", "?", "n/a", "na", "none", "unknown", "null", "-"}
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
LOG_FIELDS = {
    "source": ("system", "source_system", "feed"),
    "file": ("path", "file_name", "filename", "object", "key", "name"),
    "arrived_at": ("arrived", "arrival", "received_at", "landed_at", "created_at", "modified", "timestamp", "time"),
    "rows": ("row_count", "records", "lines"),
}
TYPES = {
    "integer": re.compile(r"^[+-]?\d+$"),
    "decimal": re.compile(r"^[+-]?\d+(\.\d+)?$"),
    "boolean": re.compile(r"^(true|false|0|1|yes|no)$", re.I),
    "timestamp": re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$"),
}
TYPE_NAMES = {
    "int": "integer", "integer": "integer", "bigint": "integer", "long": "integer", "smallint": "integer",
    "decimal": "decimal", "number": "decimal", "numeric": "decimal", "float": "decimal", "double": "decimal",
    "money": "decimal", "date": "date", "timestamp": "timestamp", "datetime": "timestamp", "bool": "boolean",
    "boolean": "boolean", "string": "string", "text": "string", "varchar": "string", "char": "string",
}  # fmt: skip
DATE_FORMATS = {
    "YYYY-MM-DD": r"\d{4}-\d{2}-\d{2}",
    "DD.MM.YYYY": r"\d{2}\.\d{2}\.\d{4}\.?",
    "DD/MM/YYYY": r"\d{2}/\d{2}/\d{4}",
    "MM/DD/YYYY": r"\d{2}/\d{2}/\d{4}",
    "YYYYMMDD": r"\d{8}",
}
SHORT = 12


# ---------------------------------------------------------------------------- YAML, the flat shapes only


def _strip_comment(line: str) -> str:
    quote = ""
    for i, char in enumerate(line):
        if char in "\"'" and not quote:
            quote = char
        elif char == quote:
            quote = ""
        elif char == "#" and not quote and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _split_flow(text: str) -> list[str]:
    parts, depth, quote, current = [], 0, "", ""
    for char in text:
        if char in "\"'" and not quote:
            quote = char
        elif char == quote:
            quote = ""
        elif not quote and char in "[{":
            depth += 1
        elif not quote and char in "]}":
            depth -= 1
        if char == "," and not quote and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    return [p for p in (*parts, current) if p.strip()]


def scalar(text: str) -> Any:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        return [scalar(p) for p in _split_flow(text[1:-1])]
    if text.startswith("{") and text.endswith("}"):
        pairs = [p.partition(":") for p in _split_flow(text[1:-1])]
        return {k.strip().strip("\"'"): scalar(v) for k, _, v in pairs}
    if text in ("", "~", "null"):
        return None
    if text in ("true", "false"):
        return text == "true"
    return text


KEY_LINE = re.compile(r"^[\w.$/-]+\s*:(\s|$)")


def parse_yaml(text: str) -> Any:
    """A YAML reader for the flat shapes of contract, job and check files: mappings, lists, flow lists, scalars."""
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        line = _strip_comment(raw).rstrip()
        if line.strip() and line.strip() != "---":
            lines.append((len(line) - len(line.lstrip(" ")), line.strip()))
    if not lines:
        return None
    value, _ = _block(lines, 0, lines[0][0])
    return value


def _block(lines: list[tuple[int, str]], i: int, indent: int) -> tuple[Any, int]:
    if lines[i][1] == "-" or lines[i][1].startswith("- "):
        items: list[Any] = []
        while i < len(lines) and lines[i][0] == indent and (lines[i][1] == "-" or lines[i][1].startswith("- ")):
            rest = lines[i][1][1:].strip()
            if not rest:
                if i + 1 < len(lines) and lines[i + 1][0] > indent:
                    value, i = _block(lines, i + 1, lines[i + 1][0])
                else:
                    value, i = None, i + 1
            elif KEY_LINE.match(rest) and not rest.startswith(("'", '"')):
                inner = indent + len(lines[i][1]) - len(rest)
                lines[i] = (inner, rest)
                value, i = _block(lines, i, inner)
            else:
                value, i = scalar(rest), i + 1
            items.append(value)
        return items, i
    mapping: dict[str, Any] = {}
    while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith("- "):
        key, _, rest = lines[i][1].partition(":")
        key, rest = key.strip().strip("\"'"), rest.strip()
        i += 1
        if rest in ("|", ">", "|-", ">-"):
            body = []
            while i < len(lines) and lines[i][0] > indent:
                body.append(lines[i][1])
                i += 1
            mapping[key] = ("\n" if rest.startswith("|") else " ").join(body)
        elif rest:
            mapping[key] = scalar(rest)
        elif i < len(lines) and (lines[i][0] > indent or (lines[i][0] == indent and lines[i][1].startswith("- "))):
            mapping[key], i = _block(lines, i, lines[i][0])
        else:
            mapping[key] = None
    return mapping, i


# ---------------------------------------------------------------------------- reading records and data files


def read_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if text.lstrip().startswith("["):
        data = json.loads(text)
        return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
    if path.suffix.lower() in (".jsonl", ".ndjson", ".json"):
        records = []
        for line in text.splitlines():
            try:
                record = json.loads(line) if line.strip() else None
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
        return records
    first = text.split("\n", 1)[0]
    return [dict(r) for r in csv.DictReader(text.splitlines(), delimiter=max(",;\t|", key=first.count))]


def normalise(record: dict[str, Any], fields: dict[str, tuple[str, ...]]) -> dict[str, Any]:
    lowered = {re.sub(r"[\s-]+", "_", str(k).strip().lower()): v for k, v in record.items()}
    found: dict[str, Any] = {}
    for name, aliases in fields.items():
        for alias in (name, *aliases):
            if alias in lowered:
                found[name] = lowered[alias]
                break
    return found


def understood(records: list[dict[str, Any]], fields: dict[str, tuple[str, ...]]) -> dict[str, Any]:
    keys = {re.sub(r"[\s-]+", "_", str(k).strip().lower()): str(k) for r in records[:200] for k in r}
    mapped = {}
    for name, aliases in fields.items():
        hit = next((keys[a] for a in (name, *aliases) if a in keys), None)
        if hit:
            mapped[name] = hit
    return {"records": len(records), "fields": mapped, "missing": [f for f in fields if f not in mapped]}


def read_data(path: Path) -> tuple[list[str], list[dict[str, str]], dict[str, Any]]:
    raw = path.read_bytes()
    try:
        text, encoding = raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        text, encoding = raw.decode("cp1250", errors="replace"), "not utf-8"
    info: dict[str, Any] = {"encoding": encoding, "delimiter": None}
    if path.suffix.lower() in (".jsonl", ".ndjson"):
        rows = []
        for line in text.splitlines():
            try:
                record = json.loads(line) if line.strip() else None
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                rows.append(
                    {k: "" if v is None else v if isinstance(v, str) else json.dumps(v) for k, v in record.items()}
                )
        return list(dict.fromkeys(k for r in rows for k in r)), rows, info
    first = text.split("\n", 1)[0]
    delimiter = "\t" if path.suffix.lower() == ".tsv" else max(",;\t|", key=first.count)
    info["delimiter"] = delimiter
    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    header = [h.strip() for h in next(reader, [])]
    rows = [dict(zip(header, r, strict=False)) for r in reader if r]
    return header, rows, info


def shape(value: str) -> str:
    """7110.00 is 9.99, 18846,00 is 9,99, 1.234,50 is 9.999,99: the first run of digits is one 9."""
    runs = iter(range(10_000))
    return re.sub(r"\d+", lambda m: "9" if next(runs) == 0 else "9" * len(m.group()), value)


def personal(name: str, values: list[str]) -> str | None:
    found = data_profile.personal_of(name, [v for v in values if v][:2000])
    return str(found["kind"]) if found else None


def day_of(path: str) -> str:
    match = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", path)
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else path


# ---------------------------------------------------------------------------- the contract


def find(node: Any, names: tuple[str, ...]) -> Any:
    """The value of the first key in names, looked for at the top and one level down."""
    if not isinstance(node, dict):
        return None
    for name in names:
        if name in node:
            return node[name]
    for value in node.values():
        if isinstance(value, dict):
            for name in names:
                if name in value:
                    return value[name]
    return None


def columns_of(contract: dict[str, Any]) -> list[dict[str, Any]]:
    raw = find(contract, ("columns", "fields", "properties"))
    if raw is None and isinstance(contract.get("schema"), list) and contract["schema"]:
        raw = find(contract["schema"][0], ("columns", "fields", "properties"))
    if raw is None and isinstance(contract.get("models"), dict) and contract["models"]:
        raw = find(next(iter(contract["models"].values())), ("columns", "fields", "properties"))
    if isinstance(raw, dict):
        return [{"name": k, **(v if isinstance(v, dict) else {"type": v})} for k, v in raw.items()]
    return [c for c in raw or [] if isinstance(c, dict) and c.get("name")]


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [v.strip() for v in str(value).split(",") if v.strip()]


def summary(contract: dict[str, Any]) -> dict[str, Any]:
    columns = columns_of(contract)
    return {
        "name": find(contract, ("contract", "name", "id", "title")),
        "version": find(contract, ("version",)),
        "owner": find(contract, ("owner", "owners", "team", "contact")),
        "change_process": find(contract, ("change_process", "change_management", "change_policy", "versioning")),
        "path": find(contract, ("path", "location", "file")),
        "format": find(contract, ("format",)),
        "delimiter": find(contract, ("delimiter", "separator")),
        "encoding": find(contract, ("encoding",)),
        "deliver_by": find(contract, ("deliver_by", "delivered_by", "available_by", "delivery_time", "due_by")),
        "timezone": find(contract, ("timezone", "time_zone", "tz")),
        "frequency": find(contract, ("frequency", "schedule", "cadence")),
        "key": as_list(find(contract, ("key", "primary_key", "keys", "unique_key"))),
        "columns": [c["name"] for c in columns],
        "quality": [
            q if isinstance(q, str) else str(q.get("rule") or q.get("description") or q)
            for q in (find(contract, ("quality", "rules", "checks")) or [])
        ],
        "consumers": as_list(find(contract, ("consumers", "used_by"))),
    }


def gaps_of(info: dict[str, Any]) -> list[dict[str, Any]]:
    gaps = []
    for name in ("owner", "change_process", "deliver_by", "version"):
        value = info[name]
        if value is None or str(value).strip().lower() in EMPTY:
            gaps.append({"field": name, "value": value, "why": "empty or a placeholder"})
    for name in ("key", "columns", "quality"):
        if not info[name]:
            gaps.append({"field": name, "value": None, "why": "missing"})
    if info["deliver_by"] and not info["timezone"]:
        gaps.append({"field": "timezone", "value": None, "why": "a delivery time without a time zone"})
    return gaps


def checker(column: dict[str, Any]) -> tuple[str, re.Pattern[str] | None]:
    kind = TYPE_NAMES.get(str(column.get("type") or column.get("logicalType") or "string").lower(), "string")
    if kind == "date":
        fmt = str(column.get("format") or "YYYY-MM-DD")
        return f"date {fmt}", re.compile(f"^{DATE_FORMATS.get(fmt, DATE_FORMATS['YYYY-MM-DD'])}$")
    unit = column.get("unit")
    return (f"{kind} ({unit})" if unit else kind), TYPES.get(kind)


def check_file(path: Path, contract: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    header, rows, seen = read_data(path)
    columns = {c["name"]: c for c in columns_of(contract)}
    report: dict[str, Any] = {
        "file": path.as_posix(),
        "day": day_of(path.as_posix()),
        "rows": len(rows),
        "encoding": seen["encoding"],
        "delimiter": seen["delimiter"],
        "missing_columns": [c for c in columns if c not in header],
        "extra_columns": [c for c in header if c not in columns],
    }
    order = [c for c in columns if c in header]
    if order != [c for c in header if c in columns]:
        report["order_differs"] = True
    if info["delimiter"] and seen["delimiter"] and str(info["delimiter"]) != seen["delimiter"]:
        report["delimiter_differs"] = {"contract": info["delimiter"], "file": seen["delimiter"]}
    problems: dict[str, Any] = {}
    observed: dict[str, Any] = {}
    for name, column in columns.items():
        if name not in header:
            continue
        values = [str(r.get(name) or "").strip() for r in rows]
        is_personal = personal(name, values)
        found: dict[str, Any] = {}
        kind, pattern = checker(column)
        if pattern is not None:
            bad = [v for v in values if v and not pattern.match(v)]
            if bad:
                found["type"] = {
                    "expected": kind,
                    "values_breaking": len(bad),
                    "of": sum(1 for v in values if v),
                    "shapes": dict(Counter(shape(v) for v in bad).most_common(5)),
                }
                if seen["delimiter"]:
                    holding = sum(1 for v in bad if seen["delimiter"] in v)
                    if holding:
                        found["type"]["quoted_because_they_hold_the_delimiter"] = holding
        required = column.get("required") is True or column.get("nullable") is False or column.get("not_null") is True
        if required and (empty := sum(1 for v in values if not v)):
            found["required_but_empty"] = empty
        allowed = column.get("allowed") or column.get("enum") or column.get("accepted_values") or column.get("values")
        if isinstance(allowed, list):
            counts = Counter(v for v in values if v)
            outside = {v: n for v, n in counts.items() if v not in [str(a) for a in allowed]}
            if outside:
                found["not_allowed"] = (
                    {"rows": sum(outside.values())} if is_personal else dict(sorted(outside.items())[:SHORT])
                )
            if not is_personal:
                observed[name] = dict(counts.most_common(SHORT))
        if found:
            problems[name] = found
    report["column_problems"] = problems
    if observed:
        report["allowed_values_seen"] = observed
    key = [k for k in info["key"] if k in header]
    if key:
        keys = Counter(tuple(r.get(k, "") for k in key) for r in rows)
        report["key"] = {"columns": key, "duplicated_keys": sum(1 for n in keys.values() if n > 1)}
    report["quality"] = [rule_result(rule, rows, header) for rule in info["quality"]]
    return report


def number(value: str) -> float | None:
    text = value.strip()
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def rule_result(rule: str, rows: list[dict[str, str]], header: list[str]) -> dict[str, Any]:
    text = rule.strip()
    compare = re.fullmatch(r"(\w+)\s*(>=|<=|>|<|=|!=|<>)\s*(-?[\d.]+)", text)
    if compare and compare.group(1) in header:
        column, op, limit = compare.group(1), compare.group(2), float(compare.group(3))
        tests = {">": limit.__lt__, ">=": limit.__le__, "<": limit.__gt__, "<=": limit.__ge__, "=": limit.__eq__}
        test = tests.get(op, limit.__ne__)
        parsed = [number(str(r.get(column) or "")) for r in rows]
        return {
            "rule": rule,
            "checked": True,
            "rows_breaking": sum(1 for v in parsed if v is not None and not test(v)),
            "rows_not_numbers": sum(1 for v in parsed if v is None),
            "read_as": "numbers, with a decimal comma read as a point",
        }
    together = re.fullmatch(r"(?:unique\s*\(([\w, ]+)\))|([\w, ]+?)\s+(?:together\s+)?(?:is|are)\s+unique", text)
    if together:
        names = [c for c in re.split(r"[\s,]+|\band\b", together.group(1) or together.group(2)) if c and c != "and"]
        if names and all(c in header for c in names):
            counts = Counter(tuple(r.get(c, "") for c in names) for r in rows)
            return {"rule": rule, "checked": True, "rows_breaking": sum(n for n in counts.values() if n > 1)}
    filled = re.fullmatch(r"(\w+)\s+(?:is\s+not\s+null|is\s+required|not\s+null|is\s+always\s+filled)", text)
    if filled and filled.group(1) in header:
        empty = sum(1 for r in rows if not str(r.get(filled.group(1)) or "").strip())
        return {"rule": rule, "checked": True, "rows_breaking": empty}
    return {"rule": rule, "checked": False, "why": "not a rule shape this script reads"}


def path_pattern(template: str) -> re.Pattern[str]:
    parts = re.split(r"(\{[^}]*\})", template)
    regex = "".join(
        (r"(\d{4}-?\d{2}-?\d{2})" if "date" in p.lower() or "yyyy" in p.lower() else r"[^/]+")
        if p.startswith("{")
        else re.escape(p)
        for p in parts
    )
    return re.compile(f"(?:^|/){regex}$")


def delivered_files(root: Path, template: str) -> list[Path]:
    pattern = path_pattern(template)
    base = template.split("{", 1)[0].rsplit("/", 1)[0]
    start = root / base if base and (root / base).is_dir() else root
    found = [p for p in start.rglob("*") if p.is_file() and pattern.search(p.relative_to(root).as_posix())]
    return sorted(found, key=lambda p: day_of(p.as_posix()))


# ---------------------------------------------------------------------------- the delivery log


def local_time(stamp: Any, zone: str | None) -> datetime | None:
    try:
        if isinstance(stamp, int | float):
            moment = datetime.fromtimestamp(float(stamp), tz=ZoneInfo("UTC"))
        else:
            moment = datetime.fromisoformat(str(stamp).strip().replace("Z", "+00:00"))
    except (ValueError, OverflowError, ZoneInfoNotFoundError):
        return None
    if moment.tzinfo is not None and zone:
        try:
            return moment.astimezone(ZoneInfo(zone))
        except (ZoneInfoNotFoundError, ValueError):
            return moment
    return moment


def arrivals(
    log: list[dict[str, Any]],
    pattern: re.Pattern[str] | None,
    name: str | None,
    deliver_by: str | None,
    zone: str | None,
) -> dict[str, Any]:
    matched = []
    for record in log:
        item = normalise(record, LOG_FIELDS)
        file = str(item.get("file") or "")
        if (pattern and pattern.search(file)) or (not pattern and name and Path(file).name == name):
            moment = local_time(item.get("arrived_at"), zone)
            if moment:
                matched.append((moment, item))
    matched.sort(key=lambda pair: pair[0])
    result: dict[str, Any] = {"deliveries": len(matched)}
    if not matched:
        return result
    days = [m.date() for m, _ in matched]
    result["from"], result["to"] = days[0].isoformat(), days[-1].isoformat()
    span = [days[0] + timedelta(n) for n in range((days[-1] - days[0]).days + 1)]
    result["days_without_a_delivery"] = [d.isoformat() for d in span if d not in set(days)]
    result["times"] = {"earliest": min(m.strftime("%H:%M") for m, _ in matched),
                       "latest": max(m.strftime("%H:%M") for m, _ in matched)}  # fmt: skip
    if deliver_by:
        due = str(deliver_by)[:5]
        late = [(m, i) for m, i in matched if m.strftime("%H:%M") > due]
        on_time = [(m, i) for m, i in matched if m.strftime("%H:%M") <= due]
        minutes = [(m.hour * 60 + m.minute) - (int(due[:2]) * 60 + int(due[3:5])) for m, _ in late]
        result["deliver_by"] = due
        result["late"] = len(late)
        result["on_time"] = len(on_time)
        if late:
            result["late_between"] = [
                min(m.strftime("%H:%M") for m, _ in late),
                max(m.strftime("%H:%M") for m, _ in late),
            ]
            result["minutes_late"] = {"median": statistics.median(minutes), "max": max(minutes)}
            result["late_by_weekday"] = dict(Counter(WEEKDAYS[m.weekday()] for m, _ in late))
        if on_time:
            result["on_time_by_weekday"] = dict(Counter(WEEKDAYS[m.weekday()] for m, _ in on_time))
            result["on_time_days"] = [m.date().isoformat() for m, _ in on_time][:31]
    return result


# ---------------------------------------------------------------------------- the metadata document


def parse_doc(text: str) -> dict[str, Any]:
    sections: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        heading = re.match(r"^#{1,4}\s+`?([\w.-]+?)`?\s*$", line)
        if heading:
            current = heading.group(1)
            sections.setdefault(current, [])
            continue
        if current and line.lstrip().startswith("|"):
            cell = line.strip().strip("|").split("|")[0].strip().strip("`")
            if re.fullmatch(r"\w+", cell) and cell.lower() not in ("column", "name", "field"):
                sections[current].append(cell)
    claims: dict[str, Any] = {}
    if found := re.search(r"\b(comma|semicolon|tab|pipe)[- ](separated|delimited)", text, re.I):
        claims["delimiter"] = {"comma": ",", "semicolon": ";", "tab": "\t", "pipe": "|"}[found.group(1).lower()]
    if found := re.search(r"\bdecimal (point|comma)\b", text, re.I):
        claims["decimal"] = found.group(1).lower()
    if found := re.search(r"\bby (\d{1,2}:\d{2})\b", text):
        claims["deliver_by"] = found.group(1).zfill(5)
    if formats := sorted(set(re.findall(r"\b(YYYY-MM-DD|DD\.MM\.YYYY|MM/DD/YYYY|DD/MM/YYYY|YYYYMMDD)\b", text))):
        claims["date_formats"] = formats
    return {"sections": {k: v for k, v in sections.items() if v}, "claims": claims}


def doc_vs_contract(doc: dict[str, Any], info: dict[str, Any], file_name: str) -> dict[str, Any]:
    section = next((cols for name, cols in doc["sections"].items() if Path(name).stem == Path(file_name).stem), None)
    result: dict[str, Any] = {"claims": doc["claims"], "sections": sorted(doc["sections"])}
    if section is None:
        result["section"] = f"the document has no section for {file_name}"
    else:
        result["in_document_not_in_contract"] = [c for c in section if c not in info["columns"]]
        result["in_contract_not_in_document"] = [c for c in info["columns"] if c not in section]
    conflicts: list[dict[str, Any]] = []
    claims = doc["claims"]
    if section is None:  # the document is about other files: its general claims need not hold for this one
        result["conflicts"] = conflicts
        return result
    if claims.get("delimiter") and info["delimiter"] and claims["delimiter"] != str(info["delimiter"]):
        conflicts.append({"what": "delimiter", "document": claims["delimiter"], "contract": info["delimiter"]})
    if claims.get("deliver_by") and info["deliver_by"] and claims["deliver_by"] != str(info["deliver_by"])[:5]:
        conflicts.append({"what": "delivery time", "document": claims["deliver_by"], "contract": info["deliver_by"]})
    result["conflicts"] = conflicts
    return result


# ---------------------------------------------------------------------------- the two modes


def check(args: argparse.Namespace) -> dict[str, Any]:
    contract = parse_yaml(args.contract.read_text(encoding="utf-8"))
    if not isinstance(contract, dict):
        raise SystemExit(f"{args.contract}: not a YAML mapping")
    info = summary(contract)
    root = args.root or (args.contract.parent.parent if args.contract.parent.name == "contracts" else Path("."))
    files = [Path(p) for p in args.data] if args.data else []
    if not files and info["path"]:
        files = delivered_files(root, str(info["path"]))
    reports = [check_file(p, contract, info) for p in files]
    result: dict[str, Any] = {
        "understood": {
            "contract": f"{args.contract.as_posix()}: {len(info['columns'])} columns, {len(info['quality'])} rules",
            "files": [r["file"] for r in reports],
            "deliveries": None,
            "document": args.doc.as_posix() if args.doc else None,
        },
        "contract": info,
        "open_in_the_contract": gaps_of(info),
        "files": reports,
        "columns_over_time": over_time(info, reports),
    }
    if args.deliveries:
        log = read_records(args.deliveries)
        result["understood"]["deliveries"] = {"file": args.deliveries.as_posix(), **understood(log, LOG_FIELDS)}
        pattern = path_pattern(str(info["path"])) if info["path"] else None
        name = Path(str(info["path"])).name if info["path"] else None
        result["arrivals"] = arrivals(log, pattern, name, info["deliver_by"], info["timezone"])
    if args.doc:
        file_name = Path(str(info["path"] or info["name"] or "")).name
        result["document"] = doc_vs_contract(parse_doc(args.doc.read_text(encoding="utf-8")), info, file_name)
    result["hits"] = check_hits(result)
    return result


def over_time(info: dict[str, Any], reports: list[dict[str, Any]]) -> dict[str, Any]:
    timeline: dict[str, Any] = {}
    for column in info["columns"]:
        gone = [r["day"] for r in reports if column in r["missing_columns"]]
        if gone:
            timeline[column] = {"missing_from": gone, "present_in": [r["day"] for r in reports if r["day"] not in gone]}
    for report in reports:
        for name, problem in report["column_problems"].items():
            if "type" in problem:
                shapes = problem["type"]["shapes"]
                timeline.setdefault(name, {}).setdefault("breaking_shapes", {})[report["day"]] = shapes
    return timeline


def check_hits(result: dict[str, Any]) -> list[str]:
    hits = [f"contract: {g['field']} {g['why']} ({g['value']})" for g in result["open_in_the_contract"]]
    for report in result["files"]:
        day = report["day"]
        if report["missing_columns"]:
            hits.append(f"{day}: contract columns missing from the file {report['missing_columns']}")
        if report["extra_columns"]:
            hits.append(f"{day}: columns the contract does not list {report['extra_columns']}")
        if report.get("delimiter_differs"):
            hits.append(f"{day}: delimiter {report['delimiter_differs']}")
        for name, problem in report["column_problems"].items():
            if "type" in problem:
                t = problem["type"]
                hits.append(
                    f"{day} {name}: {t['values_breaking']} of {t['of']} values are not {t['expected']}, {t['shapes']}"
                )
            if "not_allowed" in problem:
                hits.append(f"{day} {name}: values outside the allowed list {problem['not_allowed']}")
            if "required_but_empty" in problem:
                hits.append(f"{day} {name}: required but empty in {problem['required_but_empty']} rows")
        if report.get("key", {}).get("duplicated_keys"):
            hits.append(f"{day}: {report['key']['duplicated_keys']} duplicated keys {report['key']['columns']}")
        for rule in report["quality"]:
            if rule.get("rows_breaking"):
                hits.append(f"{day}: rule '{rule['rule']}' broken by {rule['rows_breaking']} rows")
    arrivals_seen = result.get("arrivals")
    if arrivals_seen and arrivals_seen.get("late"):
        a = arrivals_seen
        hits.append(f"arrivals: {a['late']} of {a['deliveries']} after {a['deliver_by']}, between {a['late_between']}")
    document = result.get("document")
    if document:
        hits += [
            f"document: {c['what']} {c['document']} against the contract's {c['contract']}"
            for c in document["conflicts"]
        ]
    return hits


def draft(args: argparse.Namespace) -> dict[str, Any]:
    groups: dict[str, list[Path]] = {}
    for path in args.data:
        for file in (
            [path] if path.is_file() else sorted(p for p in path.iterdir() if p.suffix.lower() in DATA_SUFFIXES)
        ):
            groups.setdefault(file.name, []).append(file)
    proposals = [propose(name, files) for name, files in sorted(groups.items())]
    result: dict[str, Any] = {
        "understood": {"files": {name: [f.as_posix() for f in files] for name, files in sorted(groups.items())}},
        "proposals": proposals,
    }
    log = read_records(args.deliveries) if args.deliveries else []
    doc = parse_doc(args.doc.read_text(encoding="utf-8")) if args.doc else None
    if args.deliveries:
        result["understood"]["deliveries"] = {"file": args.deliveries.as_posix(), **understood(log, LOG_FIELDS)}
    for proposal in proposals:
        if args.deliveries:
            due = doc["claims"].get("deliver_by") if doc else None
            proposal["arrivals"] = arrivals(log, None, proposal["file"], due, None)
        if doc:
            section = next((c for n, c in doc["sections"].items() if Path(n).stem == Path(proposal["file"]).stem), None)
            delivered = [c["name"] for c in proposal["columns"]]
            proposal["document"] = (
                {"section": "none"}
                if section is None
                else {
                    "in_document_not_delivered": [c for c in section if c not in delivered],
                    "delivered_not_in_document": [c for c in delivered if c not in section],
                }
            )
    if doc:
        result["document_claims"] = doc["claims"]
    result["hits"] = draft_hits(result)
    return result


def propose(name: str, files: list[Path]) -> dict[str, Any]:
    latest = files[-1]
    _, rows, seen = read_data(latest)
    profile, _ = data_profile.profile_file(latest, 200_000)
    headers = [read_data(f)[0] for f in files]
    columns = []
    for column in profile["columns"]:
        col = column["name"]
        values = [str(r.get(col) or "").strip() for r in rows]
        entry: dict[str, Any] = {
            "name": col,
            "type": {"code": "string", "text": "string", "datetime": "timestamp"}.get(column["type"], column["type"]),
            "always_filled": column["nulls"] == 0,
            "in_every_delivery": all(col in h for h in headers),
        }
        if re.search(r"(^|_)(id|code|key|no|ref)$", col, re.I):
            entry["type"] = "string"  # an identifier: leading zeros and letters must survive
        numbers = number_format([v for v in values if v])
        if numbers:
            entry["type"], entry["number_format"] = "decimal", numbers
        if column.get("issues"):
            entry["issues"] = column["issues"]
        if column.get("personal"):
            entry["personal"] = column["personal"]["kind"]
        elif 1 <= column["distinct"] <= SHORT and len(rows) >= 10 and column["type"] in ("text", "code"):
            entry["values"] = sorted({v for v in values if v})
        if column["type"] == "date":
            formats = Counter(f for f, rx in DATE_FORMATS.items() for v in values if v and re.fullmatch(rx, v))
            entry["formats"] = dict(formats.most_common(3))
        columns.append(entry)
    return {
        "file": name,
        "deliveries": [f.as_posix() for f in files],
        "rows": len(rows),
        "format": {"encoding": seen["encoding"], "delimiter": seen["delimiter"], "header": True},
        "columns": columns,
        "columns_not_in_every_delivery": [c["name"] for c in columns if not c["in_every_delivery"]],
        "key_candidates": profile["candidate_keys"],
        "almost_keys": profile["almost_keys"],
    }


def number_format(values: list[str]) -> dict[str, int] | None:
    """How decimals are written, when most values are numbers with a fraction: point, comma, thousands separators."""
    shapes = {
        "decimal_point": r"[+-]?\d+\.\d+|[+-]?\d{1,3}(,\d{3})+\.\d+",
        "decimal_comma": r"[+-]?\d+,\d+|[+-]?\d{1,3}(\.\d{3})+,\d+",
    }
    counts = {k: sum(1 for v in values if re.fullmatch(rx, v)) for k, rx in shapes.items()}
    if not values or sum(counts.values()) < 0.8 * len(values):
        return None
    counts["thousands_separator"] = sum(1 for v in values if re.fullmatch(r"[+-]?\d{1,3}([.,]\d{3})+[.,]\d+", v))
    return counts


def draft_hits(result: dict[str, Any]) -> list[str]:
    hits = []
    for p in result["proposals"]:
        if not p["key_candidates"]:
            hits.append(f"{p['file']}: no column or pair of columns is unique: {p['almost_keys']}")
        if p["columns_not_in_every_delivery"]:
            hits.append(f"{p['file']}: columns not in every delivery {p['columns_not_in_every_delivery']}")
        hits += [f"{p['file']} {c['name']}: {'; '.join(c['issues'])}" for c in p["columns"] if c.get("issues")]
        hits += [
            f"{p['file']} {c['name']}: decimal comma in {c['number_format']['decimal_comma']} values"
            for c in p["columns"]
            if c.get("number_format", {}).get("decimal_comma")
        ]
        personal_columns = [c["name"] for c in p["columns"] if c.get("personal")]
        if personal_columns:
            hits.append(f"{p['file']}: personal columns {personal_columns}")
        doc = p.get("document", {})
        if doc.get("in_document_not_delivered") or doc.get("delivered_not_in_document"):
            hits.append(f"{p['file']}: document and delivery differ {doc}")
        if p.get("arrivals", {}).get("late"):
            hits.append(f"{p['file']}: {p['arrivals']['late']} deliveries after {p['arrivals']['deliver_by']}")
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    modes = parser.add_subparsers(dest="mode", required=True)
    one = modes.add_parser("check", help="a contract against the deliveries")
    one.add_argument("contract", type=Path)
    one.add_argument("--root", type=Path, help="where the contract's delivery path starts; default its repository")
    one.add_argument("--data", nargs="+", default=[], help="delivered files, instead of the contract's path")
    two = modes.add_parser("draft", help="a contract's content from the deliveries")
    two.add_argument("data", nargs="+", type=Path, help="delivery folders, oldest first, or files")
    for sub in (one, two):
        sub.add_argument("--deliveries", type=Path, help="the delivery log: JSON Lines or CSV, a file and its arrival")
        sub.add_argument("--doc", type=Path, help="the source's metadata document, Markdown")
    args = parser.parse_args(argv)
    result = check(args) if args.mode == "check" else draft(args)
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False, default=str)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
