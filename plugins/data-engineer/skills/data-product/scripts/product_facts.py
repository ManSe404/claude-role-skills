#!/usr/bin/env python3
"""Gather the facts a consumer guide for one served table needs, and the places where the documents disagree.

Usage: python3 product_facts.py REPO --table SCHEMA.TABLE [--grain K1,K2 ...] [--sample FILE] [--queries FILE]
                                     [--results FILE] [--runs FILE]

It reads the repository: the SQL that builds the table (its columns, expressions, sources and GROUP BY), a sample
of the table (CSV, TSV, JSON Lines or a JSON array whose name is the table's), the query log, check definitions in
YAML (a list of checks naming the table, or dbt `models:` with column tests), check results and run records, the job
definition that builds it (schedule, SLA), and every Markdown, text or YAML document that names the table. Field
names match case-insensitively with common aliases; `inputs` says which file fed what.

It prints: the columns and how each is computed; the grain each candidate key gives on the sample (rows, keys with
more than one row, the columns that differ inside those keys) and the smallest unique keys; personal columns by name
and by value, counted; consumers and how often each reads; the checks that cover the table and its sources, with
their results and test cases; freshness against the job's SLA; the product document's stated grain, owner, refresh
and columns; every definition of each column across documents and SQL, with the terms one definition includes and
another excludes; the contract, if any; and the git history of the files that make the table.

It never prints a value of a personal column, only names and counts. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import csv
import io
import itertools
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".tox", "dist", "build"}
DATA_SUFFIXES = {".csv", ".tsv", ".jsonl", ".ndjson", ".json"}
DOC_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".yaml", ".yml"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
IBAN = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
PHONE = re.compile(r"^(\+|00)\d[\d ()/-]{6,}\d$|^0\d{1,3}[ /-]\d{3}[ /-]?\d{2,4}([ /-]?\d{2,4})?$")
PERSONAL_NAMES = [
    ("e-mail", r"e_?mail"),
    ("phone", r"phone|mobile|(^|_)tel(_|$)"),
    ("national id", r"jmbg|national_?id|(^|_)ssn(_|$)|passport"),
    ("bank account", r"iban|bank_?account|account_?number"),
    ("address", r"address|street|post_?code|zip_?code"),
    ("birth date", r"birth|(^|_)dob(_|$)"),
    ("person name", r"(first|last|full|given|family|contact|person)_?name|surname"),
    ("ip address", r"(^|_)ip(_?address)?(_|$)"),
]
KEYISH = re.compile(r"(^|_)(id|key|code|no|date|day|week|month|year|currency|type|channel|region|country)$", re.I)
FRESH_COLUMNS = ("built_at", "loaded_at", "refreshed_at", "updated_at", "load_date", "_loaded_at", "snapshot_at")
ROLES: dict[str, dict[str, list[str]]] = {
    "queries": {
        "date": ["date", "day", "query_date", "start_time", "started_at", "timestamp", "ts", "executed_at"],
        "consumer": [
            "consumer",
            "user",
            "user_name",
            "username",
            "client",
            "application",
            "app",
            "principal",
            "reader",
            "service",
        ],
        "table": ["table", "table_name", "object", "object_name", "relation", "accessed_table", "base_object"],
        "count": ["queries", "query_count", "count", "reads", "num_queries", "executions", "n"],
    },
    "results": {
        "date": ["date", "run_date", "day", "checked_at", "executed_at", "timestamp"],
        "check": ["check", "check_name", "test", "test_name", "rule", "expectation"],
        "table": ["table", "table_name", "model", "dataset", "object"],
        "status": ["status", "result", "outcome", "state"],
        "failing": ["failing_rows", "failures", "failed_rows", "rows_failed", "unexpected_count"],
    },
    "runs": {
        "job": ["job", "job_name", "pipeline", "dag_id", "flow"],
        "task": ["task", "task_id", "step", "table", "model", "node"],
        "start": ["start", "started_at", "start_time", "start_ts"],
        "end": ["end", "ended_at", "end_time", "finished_at", "end_ts"],
        "status": ["status", "state", "result", "outcome"],
        "error": ["error", "error_message", "message"],
    },
}
REQUIRED: dict[str, list[list[str]]] = {
    "queries": [["date"], ["consumer"], ["table"]],
    "results": [["check"], ["status"]],
    "runs": [["job"], ["status"], ["start", "end"]],
}
TERMS = {
    "returns": r"\breturn(s|ed)?\b",
    "cancellations": r"\bcancel\w*",
    "discounts": r"\bdiscount\w*",
    "tax": r"\b(tax|taxes|vat)\b",
    "shipping": r"\b(shipping|freight|delivery fees?)\b",
    "refunds": r"\brefund\w*",
    "credit notes": r"\bcredit notes?\b",
    "currency conversion": r"\b(exchange rates?|fx rates?|currency conversion|converted (?:in)?to [a-z]{3})\b",
}
NEGATION = re.compile(r"\b(not|without|excluding|excludes?|except|never|no)\b", re.I)
QNAME = r'[A-Za-z_"`\[][\w"`\[\]$]*(?:\.[\w"`\[\]$]+)+'


# ---------------------------------------------------------------------------- reading


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def table_key(name: str) -> str:
    return ".".join(re.sub(r'["`\[\]]', "", name.strip()).lower().split(".")[-2:])


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def walk(root: Path, suffixes: set[str]) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in suffixes and not set(p.relative_to(root).parts) & SKIP_DIRS
    )


def read_rows(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if path.suffix.lower() in (".jsonl", ".ndjson", ".json"):
        if path.suffix.lower() == ".json":
            data = json.loads(text)
            records = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])
        else:
            records = [json.loads(line) for line in text.splitlines() if line.strip().startswith("{")]
        return [
            {norm(str(k)): "" if v is None else str(v) for k, v in r.items()} for r in records if isinstance(r, dict)
        ]
    first = text.split("\n", 1)[0]
    reader = csv.DictReader(io.StringIO(text), delimiter=max(",;\t|", key=first.count))
    return [{norm(k): (v or "") for k, v in row.items() if k is not None} for row in reader]


def header_of(path: Path) -> list[str]:
    try:
        with path.open(encoding="utf-8-sig", errors="replace") as handle:
            first = handle.readline()
        if path.suffix.lower() in (".jsonl", ".ndjson"):
            return [norm(k) for k in json.loads(first)] if first.strip().startswith("{") else []
        if path.suffix.lower() == ".json":
            rows = read_rows(path)
            return list(rows[0]) if rows else []
        return [norm(c) for c in next(csv.reader([first], delimiter=max(",;\t|", key=first.count)), [])]
    except (OSError, ValueError, UnicodeError):
        return []


def pick(columns: Iterable[str], aliases: Sequence[str]) -> str | None:
    present = set(columns)
    return next((a for a in aliases if a in present), None)


@dataclass
class Source:
    path: Path
    fields: dict[str, str]
    rows: list[dict[str, str]] = field(default_factory=list)

    def get(self, row: dict[str, str], name: str) -> str:
        column = self.fields.get(name)
        return row.get(column, "").strip() if column else ""


def find_source(role: str, root: Path, given: Path | None, files: list[Path]) -> Source | None:
    options = [given] if given else files
    for path in options:
        columns = header_of(path)
        found = {f: c for f, aliases in ROLES[role].items() if (c := pick(columns, aliases))}
        if all(any(f in found for f in need) for need in REQUIRED[role]):
            if role == "results" and "consumer" in found:
                continue
            return Source(path, found, read_rows(path))
    if given:
        raise SystemExit(f"{given}: no {role} columns found")
    return None


# ---------------------------------------------------------------------------- YAML, flat shapes


def strip_comment(line: str) -> str:
    quote = ""
    for i, char in enumerate(line):
        if quote:
            quote = "" if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def scalar(text: str) -> Any:
    value = text.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        return [scalar(part) for part in value[1:-1].split(",") if part.strip()]
    return None if value in ("null", "~", "") else value


KEY = re.compile(r"""^("[^"]*"|'[^']*'|[^\s"'#:-][^:]*?|-[^\s:][^:]*?)\s*:(\s+|$)""")


def parse_yaml(text: str) -> Any:
    """Mappings, lists, lists of mappings and flow lists, nested by indentation. Each mapping that starts a list item
    also gets `__line__`, its line in the file."""
    lines: list[list[Any]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = strip_comment(raw).rstrip()
        if line.strip() and line.strip() not in ("---", "..."):
            lines.append([len(line) - len(line.lstrip(" ")), line.strip(), number])
    if not lines:
        return None
    return _block(lines, 0, lines[0][0])[0]


def _is_item(line: list[Any]) -> bool:
    return bool(line[1] == "-" or str(line[1]).startswith("- "))


def _block(lines: list[list[Any]], i: int, indent: int) -> tuple[Any, int]:
    if _is_item(lines[i]):
        return _list(lines, i, indent)
    if not KEY.match(lines[i][1]):
        return scalar(lines[i][1]), i + 1
    return _map(lines, i, indent)


def _map(lines: list[list[Any]], i: int, indent: int) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while i < len(lines) and lines[i][0] == indent and not _is_item(lines[i]):
        match = KEY.match(lines[i][1])
        if not match:
            i += 1
            continue
        key = str(scalar(match.group(1)))
        rest = lines[i][1][match.end() :].strip()
        i += 1
        if rest and rest not in ("|", ">", "|-", ">-"):
            result[key] = scalar(rest)
        elif i < len(lines) and (lines[i][0] > indent or (lines[i][0] == indent and _is_item(lines[i]))):
            result[key], i = _block(lines, i, lines[i][0])
        else:
            result[key] = None
    return result, i


def _list(lines: list[list[Any]], i: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while i < len(lines) and lines[i][0] == indent and _is_item(lines[i]):
        content = lines[i][1][1:].strip()
        number = lines[i][2]
        if not content:
            i += 1
            value: Any = None
            if i < len(lines) and lines[i][0] > indent:
                value, i = _block(lines, i, lines[i][0])
            items.append(value)
        elif KEY.match(content):
            lines[i] = [indent + 2, content, number]
            mapping, i = _map(lines, i, indent + 2)
            mapping["__line__"] = number
            items.append(mapping)
        else:
            items.append(scalar(content))
            i += 1
    return items, i


def mappings(value: Any) -> Iterable[dict[str, Any]]:
    """Every mapping inside a parsed YAML value, depth first."""
    if isinstance(value, dict):
        yield value
        for inner in value.values():
            yield from mappings(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from mappings(inner)


# ---------------------------------------------------------------------------- SQL


def clean_sql(text: str) -> str:
    def blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    return re.sub(r"--[^\n]*|/\*.*?\*/", blank, text, flags=re.S)


def split_top(text: str) -> list[tuple[int, str]]:
    """Split on commas outside brackets and quotes; each part with its offset."""
    parts, depth, quote, start = [], 0, "", 0
    for i, char in enumerate(text):
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append((start, text[start:i]))
            start = i + 1
    parts.append((start, text[start:]))
    return parts


def top_keyword(text: str, word: str, start: int = 0) -> int:
    depth, quote = 0, ""
    pattern = re.compile(rf"\b{word}\b", re.I)
    for i in range(start, len(text)):
        char = text[i]
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and pattern.match(text, i) and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")):
            return i
    return -1


@dataclass
class Definition:
    file: str
    line: int
    build: str
    columns: list[dict[str, Any]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    group_by: list[str] = field(default_factory=list)


def find_definition(root: Path, table: str) -> Definition | None:
    target = re.escape(table).replace(r"\.", r'["`\]]?\.["`\[]?')
    writer = re.compile(
        rf"(?is)\b(create\s+(?:or\s+replace\s+)?(?:table|view|materialized\s+view)\s+(?:if\s+not\s+exists\s+)?|"
        rf"insert\s+(?:into|overwrite)\s+(?:table\s+)?|merge\s+into\s+)(?:[\w\"`\[\]]+\.)?[\"`\[]?{target}[\"`\]]?\b"
    )
    for path in walk(root, {".sql"}):
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = clean_sql(raw)
        match = writer.search(text)
        if not match:
            continue
        rest = text[match.end() :]
        end = rest.find(";")
        body = rest if end < 0 else rest[:end]
        offset = match.end()
        select_at = top_keyword(body, "select")
        definition = Definition(
            file=rel(path, root),
            line=text.count("\n", 0, match.start()) + 1,
            build="full rebuild" if re.search(r"(?i)or\s+replace|overwrite|truncate", text) else "incremental",
        )
        if select_at < 0:
            return definition
        from_at = top_keyword(body, "from", select_at + 6)
        items = body[select_at + 6 : from_at if from_at > 0 else len(body)]
        item_offset = offset + select_at + 6
        for start, item in split_top(items):
            expression = " ".join(item.split())
            if not expression:
                continue
            alias_match = re.search(r"(?is)\s+as\s+[\"`\[]?(\w+)[\"`\]]?\s*$", item)
            if alias_match:
                alias = alias_match.group(1)
                expression = " ".join(item[: alias_match.start()].split())
            else:
                alias = re.split(r"[.\s]", expression)[-1].strip('"`[]')
            line = text.count("\n", 0, item_offset + start + len(item) - len(item.lstrip())) + 1
            definition.columns.append({"column": alias.lower(), "expression": expression, "line": line})
        tail = body[from_at:] if from_at > 0 else ""
        definition.sources = sorted(
            {table_key(m.group(2)) for m in re.finditer(rf"(?is)\b(from|join)\s+({QNAME})", tail)}
        )
        group_at = re.search(r"(?is)\bgroup\s+by\b(.*?)(\bhaving\b|\border\s+by\b|\bqualify\b|$)", tail)
        if group_at:
            by_expression = {c["expression"].lower(): c["column"] for c in definition.columns}
            for _, part in split_top(group_at.group(1)):
                term = " ".join(part.split()).lower()
                if term.isdigit() and 0 < int(term) <= len(definition.columns):
                    definition.group_by.append(definition.columns[int(term) - 1]["column"])
                elif term:
                    definition.group_by.append(by_expression.get(term, term.split(".")[-1]))
        return definition
    return None


# ---------------------------------------------------------------------------- the sample


def personal_by_name(column: str) -> str | None:
    return next((label for label, pattern in PERSONAL_NAMES if re.search(pattern, column, re.I)), None)


def personal_by_value(values: list[str]) -> tuple[str, int] | None:
    filled = [v.strip() for v in values if v.strip()]
    if not filled:
        return None
    for label, test in (
        ("e-mail", lambda v: bool(EMAIL.fullmatch(v))),
        ("bank account", lambda v: bool(IBAN.match(v.replace(" ", "")))),
        ("phone", lambda v: bool(PHONE.match(v)) and sum(c.isdigit() for c in v) >= 8),
    ):
        hits = sum(1 for v in filled if test(v))
        if hits and hits >= len(filled) // 2:
            return label, hits
    return None


def grain_of(rows: list[dict[str, str]], key: list[str], personal: set[str]) -> dict[str, Any]:
    groups: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(k, "") for k in key)].append(row)
    duplicated = {k: v for k, v in groups.items() if len(v) > 1}
    varies: Counter[str] = Counter()
    for members in duplicated.values():
        for column in members[0]:
            if len({m.get(column, "") for m in members}) > 1:
                varies[column] += 1
    result: dict[str, Any] = {
        "key": key,
        "rows": len(rows),
        "distinct_keys": len(groups),
        "keys_with_more_than_one_row": len(duplicated),
        "extra_rows": sum(len(v) - 1 for v in duplicated.values()),
        "max_rows_a_key": max((len(v) for v in groups.values()), default=0),
        "unique": not duplicated,
        "columns_that_differ_inside_a_key": dict(varies.most_common()),
    }
    if duplicated and not set(key) & personal:
        result["examples"] = [dict(zip(key, k, strict=True)) for k in list(duplicated)[:3]]
    return result


def smallest_keys(rows: list[dict[str, str]], columns: list[str], personal: set[str]) -> list[list[str]]:
    distinct = {c: len({r.get(c, "") for r in rows}) for c in columns}
    candidates = [
        c
        for c in columns
        if c not in personal and distinct[c] > 1 and (KEYISH.search(c) or (distinct[c] <= 20 and not numeric(rows, c)))
    ][:12]
    found: list[list[str]] = []
    for size in (1, 2, 3):
        for combo in itertools.combinations(candidates, size):
            if any(set(f) <= set(combo) for f in found):
                continue
            if len({tuple(r.get(c, "") for c in combo) for r in rows}) == len(rows):
                found.append(list(combo))
        if found:
            break
    return found[:6]


def numeric(rows: list[dict[str, str]], column: str) -> bool:
    values = [r.get(column, "") for r in rows[:500] if r.get(column, "")]
    return bool(values) and all(re.fullmatch(r"[+-]?\d+([.,]\d+)?", v) for v in values)


def profile_sample(path: Path, root: Path, keys: list[list[str]]) -> dict[str, Any]:
    rows = read_rows(path)
    columns = list(rows[0]) if rows else header_of(path)
    personal: dict[str, dict[str, Any]] = {}
    for column in columns:
        values = [r.get(column, "") for r in rows]
        by_name = personal_by_name(column)
        by_value = personal_by_value(values)
        if by_name or by_value:
            personal[column] = {
                "by_name": by_name,
                "by_value": by_value[0] if by_value else None,
                "values_that_look_personal": by_value[1] if by_value else 0,
                "filled": sum(1 for v in values if v.strip()),
            }
    few: dict[str, dict[str, int]] = {}
    for column in columns:
        if column in personal:
            continue
        counts = Counter(r.get(column, "") for r in rows)
        if 1 < len(counts) <= 12 and len(counts) < len(rows) and not numeric(rows, column):
            few[column] = dict(counts.most_common())
    fresh = next((c for c in FRESH_COLUMNS if c in columns), None)
    tested = []
    seen: set[tuple[str, ...]] = set()
    for key in keys:
        usable = [k for k in key if k in columns]
        if usable and tuple(usable) not in seen:
            seen.add(tuple(usable))
            tested.append(grain_of(rows, usable, set(personal)))
    return {
        "file": rel(path, root),
        "rows": len(rows),
        "columns": columns,
        "distinct": {c: len({r.get(c, "") for r in rows}) for c in columns if c not in personal},
        "value_counts": few,
        "personal_columns": personal,
        "freshness_column": fresh,
        "latest_freshness_value": max((r.get(fresh, "") for r in rows), default=None) if fresh else None,
        "grain_tested": tested,
        "smallest_unique_keys": smallest_keys(rows, columns, set(personal)),
    }


# ---------------------------------------------------------------------------- documents


def words_of(column: str) -> str:
    return column.replace("_", " ").lower()


def term_states(text: str, is_sql: bool) -> dict[str, str]:
    states: dict[str, str] = {}
    for term, pattern in TERMS.items():
        found = list(re.finditer(pattern, text, re.I))
        if not found:
            continue
        negated = False
        for match in found:
            before = " ".join(text[: match.start()].split()[-4:])
            after = " ".join(text[match.end() :].split()[:3])
            if not is_sql and (NEGATION.search(before) or re.match(r"(?i)^(are|is|were|was)?\s*not\b", after)):
                negated = True
        states[term] = "excluded" if negated else "included"
    return states


def table_rows(lines: list[str]) -> Iterable[tuple[int, list[str]]]:
    for number, line in enumerate(lines, start=1):
        if line.strip().startswith("|") and not re.match(r"^\s*\|[\s:|-]+\|\s*$", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            yield number, cells


def read_documents(root: Path, table: str, columns: list[str]) -> dict[str, Any]:
    short = table.split(".")[-1]
    mention = re.compile(rf"(?i)(?<![\w.]){re.escape(short)}\b|\b{re.escape(table)}\b")
    documents: list[dict[str, Any]] = []
    definitions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    product: dict[str, Any] | None = None
    for path in walk(root, DOC_SUFFIXES):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not mention.search(text):
            continue
        name = rel(path, root)
        lines = text.splitlines()
        if path.suffix.lower() in (".yaml", ".yml") and not re.search(r"(?m)^\s*description\s*:", text):
            documents.append({"file": name, "kind": "yaml"})
            continue
        title = next((line.lstrip("# ").strip() for line in lines if line.startswith("# ")), "")
        is_product = path.stem.lower() == short or table in title.lower()
        documents.append(
            {
                "file": name,
                "kind": "product document" if is_product else "names the table",
                "title": title,
                "lines": [n for n, line in enumerate(lines, 1) if mention.search(line)][:20],
            }
        )
        for number, cells in table_rows(lines):
            first = cells[0].strip("` ").lower()
            joined = " | ".join(cells)
            column = None
            if first in columns:
                column = first
            elif norm(first) in columns:
                column = norm(first)
            else:
                ref = re.search(rf"(?i)\b(?:{re.escape(table)}|{re.escape(short)})\.(\w+)", joined)
                if ref and ref.group(1).lower() in columns:
                    column = ref.group(1).lower()
            if column and len(cells) > 1:
                text_cells = [c for c in cells[1:] if not re.fullmatch(rf"(?i)`?[\w.]*{column}`?", c.strip())]
                meaning = " | ".join(text_cells).strip()
                if meaning and meaning.lower() not in ("meaning", "definition", "column"):
                    definitions[column].append({"where": f"{name}:{number}", "name": cells[0], "text": meaning})
        for number, line in enumerate(lines, start=1):
            yaml_name = re.match(r"^\s*-\s*name\s*:\s*[\"']?(\w+)", line)
            if yaml_name and yaml_name.group(1).lower() in columns:
                for look in lines[number : number + 4]:
                    described = re.match(r"^\s*description\s*:\s*[\"']?(.+?)[\"']?\s*$", look)
                    if described:
                        definitions[yaml_name.group(1).lower()].append(
                            {"where": f"{name}:{number}", "name": yaml_name.group(1), "text": described.group(1)}
                        )
                        break
        if is_product and product is None:
            stated = {}
            for number, line in enumerate(lines, start=1):
                label = re.match(r"^\s*[-*]?\s*\**([A-Z][\w ]{1,24}?)\**\s*:\s+(.+)$", line)
                if label and not line.startswith("|"):
                    stated[label.group(1).strip().lower()] = {"where": f"{name}:{number}", "text": label.group(2)}
            documented = [cells[0].strip("` ").lower() for _, cells in table_rows(lines) if cells[0].startswith("`")]
            product = {
                "file": name,
                "title": title,
                "stated": stated,
                "names_an_owner": bool(re.search(r"(?i)\b(owner|owned by|steward|maintainer)\b", text)),
                "states_a_time": sorted(set(re.findall(r"\b\d{1,2}:\d{2}\b", text))),
                "mentions_a_contract": bool(re.search(r"(?i)\bcontract\b", text)),
                "mentions_releases": bool(re.search(r"(?i)\b(release|changelog|version|breaking change)", text)),
                "sections": [line.lstrip("# ").strip() for line in lines if re.match(r"^#{2,3} ", line)],
                "starter_queries": len(re.findall(r"(?m)^```sql", text)),
                "columns_documented": documented,
            }
    return {"documents": documents, "definitions": definitions, "product": product}


# ---------------------------------------------------------------------------- checks, jobs, runs


def key_of_check(query: str) -> list[str] | None:
    match = re.search(r"(?is)group\s+by\s+(.+?)\s+having\s+count\s*\(\s*\*\s*\)\s*>\s*1", query)
    if not match:
        return None
    return [part.strip().split(".")[-1].lower() for part in match.group(1).split(",")]


def find_checks(root: Path, tables: set[str]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    checks: list[dict[str, Any]] = []
    cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in walk(root, {".yaml", ".yml"}):
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            data = parse_yaml(text)
        except (ValueError, IndexError):
            continue
        name = rel(path, root)
        for item in mappings(data):
            target = item.get("table") or item.get("model") or item.get("dataset")
            if isinstance(item.get("check"), str) and ("result" in item or "tried_on" in item):
                cases[item["check"]].append(
                    {
                        "where": f"{name}:{item.get('__line__')}",
                        "tried_on": item.get("tried_on"),
                        "result": item.get("result"),
                        "input": item.get("bad_rows") or item.get("input"),
                    }
                )
            elif isinstance(target, str) and table_key(target) in tables and item.get("name"):
                query = str(item.get("query") or item.get("sql") or "")
                checks.append(
                    {
                        "check": str(item["name"]),
                        "table": table_key(target),
                        "where": f"{name}:{item.get('__line__')}",
                        "kind": "freshness" if item.get("freshness") else "query" if query else "other",
                        "runs": item.get("runs") or item.get("schedule"),
                        "fail_if": item.get("fail_if"),
                        "warn_if": item.get("warn_if"),
                        "key_columns": key_of_check(query),
                        "freshness_column": item.get("freshness"),
                    }
                )
        if isinstance(data, dict) and isinstance(data.get("models"), list):
            for model in data["models"]:
                if not isinstance(model, dict) or str(model.get("name", "")).lower() not in {
                    t.split(".")[-1] for t in tables
                }:
                    continue
                for column in model.get("columns") or []:
                    if isinstance(column, dict):
                        for test in column.get("tests") or column.get("data_tests") or []:
                            label = test if isinstance(test, str) else next(iter(test), "test")
                            checks.append(
                                {
                                    "check": f"{label}({column.get('name')})",
                                    "table": str(model["name"]),
                                    "where": f"{name}:{column.get('__line__')}",
                                    "kind": "dbt test",
                                }
                            )
    return checks, cases


def find_job(root: Path, table: str, definition: Definition | None) -> dict[str, Any] | None:
    for path in walk(root, {".yaml", ".yml"}):
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            data = parse_yaml(text)
        except (ValueError, IndexError):
            continue
        if not isinstance(data, dict) or not isinstance(data.get("schedule", data.get("cron")), str):
            continue
        steps = [s for s in data.get("steps") or data.get("tasks") or [] if isinstance(s, dict)]
        builds = any(
            table_key(str(s.get(k, ""))) == table for s in steps for k in ("task", "table", "target", "model")
        ) or (definition is not None and any(s.get("sql") == definition.file for s in steps))
        if not builds:
            continue

        def line(pattern: str, text: str = text) -> int | None:
            return next((n for n, row in enumerate(text.splitlines(), 1) if re.match(pattern, row)), None)

        sla = next((data[k] for k in ("sla", "deadline", "due_by", "freshness_sla", "ready_by") if data.get(k)), None)
        depends = data.get("depends_on") or []
        return {
            "job": str(data.get("name") or path.stem),
            "file": rel(path, root),
            "schedule": data.get("schedule", data.get("cron")),
            "schedule_line": line(r"^\s*(schedule|cron)\s*:"),
            "sla": sla,
            "sla_line": line(r"^\s*(sla|deadline|due_by|freshness_sla|ready_by)\s*:") if sla else None,
            "depends_on": depends if isinstance(depends, list) else [depends],
            "description": data.get("description"),
        }
    return None


def to_datetime(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def freshness(runs: Source | None, job: dict[str, Any] | None, table: str) -> dict[str, Any] | None:
    if runs is None or job is None:
        return None
    records = [
        r
        for r in runs.rows
        if runs.get(r, "job") == job["job"] and (not runs.get(r, "task") or table_key(runs.get(r, "task")) == table)
    ]
    if not records:
        return {"run_records": 0}
    statuses = Counter(runs.get(r, "status").lower() for r in records)
    ok = [r for r in records if runs.get(r, "status").lower() in ("success", "succeeded", "ok", "done", "warning")]
    ends = [(to_datetime(runs.get(r, "end")) or to_datetime(runs.get(r, "start"))) for r in ok]
    ends_known = [e for e in ends if e]
    last = max(ends_known, default=None)
    days = sorted({runs.get(r, "start")[:10] for r in records})
    late = []
    sla = str(job.get("sla") or "")
    if re.fullmatch(r"\d{1,2}:\d{2}", sla):
        hour, minute = map(int, sla.split(":"))
        late = sorted(e.isoformat() for e in ends_known if (e.hour, e.minute) > (hour, minute))
    bad = sorted(
        {
            runs.get(r, "start")[:10]
            for r in records
            if runs.get(r, "status").lower() not in ("success", "succeeded", "ok", "done", "warning")
        }
    )
    reasons = Counter(runs.get(r, "error") for r in records if runs.get(r, "error"))
    as_of = days[-1] if days else None
    return {
        "run_records": len(records),
        "statuses": dict(statuses),
        "first_day": days[0] if days else None,
        "last_day": as_of,
        "last_success_end": last.isoformat() if last else None,
        "days_without_a_success_at_the_end": sorted(d for d in bad if last is None or d > last.date().isoformat()),
        "not_successful_on": bad,
        "reasons": dict(reasons.most_common(5)),
        "successes_after_sla": late,
    }


def check_results(results: Source | None, checks: list[dict[str, Any]], tables: set[str]) -> dict[str, Any]:
    if results is None:
        return {}
    names = {c["check"] for c in checks}
    out: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in results.rows:
        name = results.get(row, "check")
        target = results.get(row, "table")
        if name in names or (target and table_key(target) in tables):
            grouped[name].append(row)
    for name, rows in sorted(grouped.items()):
        rows.sort(key=lambda r: results.get(r, "date"))
        statuses = Counter(results.get(r, "status").lower() for r in rows)
        out[name] = {
            "table": table_key(results.get(rows[-1], "table")) if results.get(rows[-1], "table") else None,
            "results": len(rows),
            "statuses": dict(statuses),
            "last": {"date": results.get(rows[-1], "date"), "status": results.get(rows[-1], "status")},
            "not_passed_on": [results.get(r, "date") for r in rows if results.get(r, "status").lower() != "pass"][-8:],
        }
    return out


def consumers_of(queries: Source | None, table: str) -> dict[str, Any] | None:
    if queries is None:
        return None
    per: dict[str, Counter[str]] = defaultdict(Counter)
    all_days: set[str] = set()
    labels: dict[str, str] = {}
    for row in queries.rows:
        day = queries.get(row, "date")[:10]
        all_days.add(day)
        if table_key(queries.get(row, "table")) != table:
            continue
        consumer = queries.get(row, "consumer")
        if EMAIL.search(consumer):
            consumer = labels.setdefault(consumer, f"user-{len(labels) + 1} (e-mail hidden)")
        count = int(float(queries.get(row, "count") or 1)) if "count" in queries.fields else 1
        per[consumer][day] += count
    result = []
    for consumer, days in sorted(per.items()):
        counts = list(days.values())
        result.append(
            {
                "consumer": consumer,
                "queries": sum(counts),
                "days_read": len(days),
                "max_a_day": max(counts),
                "min_a_day": min(counts),
                "every_day_of_the_log": len(days) == len(all_days),
            }
        )
    return {
        "log_days": len(all_days),
        "consumers": len(result),
        "queries": sum(c["queries"] for c in result),
        "by_consumer": result,
    }


def history(root: Path, files: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name in files:
        try:
            done = subprocess.run(
                ["git", "-C", str(root), "log", "--format=%ad %h %s", "--date=short", "-n", "10", "--", name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {}
        if done.returncode != 0:
            return {}
        out[name] = [EMAIL.sub("[e-mail]", line) for line in done.stdout.splitlines()]
    return out


# ---------------------------------------------------------------------------- the facts


def find_sample(root: Path, table: str, data_files: list[Path]) -> Path | None:
    schema, short = table.split(".") if "." in table else ("", table)
    names = {short, table, f"{schema}__{short}", f"{schema}_{short}"}
    hits = [p for p in data_files if p.stem.lower() in names]
    hits.sort(key=lambda p: (schema not in [part.lower() for part in p.parts], "sample" not in str(p).lower(), str(p)))
    return hits[0] if hits else None


def facts(root: Path, table: str, grains: list[list[str]], given: dict[str, Path | None]) -> dict[str, Any]:
    data_files = [p for p in walk(root, DATA_SUFFIXES) if p.stat().st_size < 200_000_000]
    definition = find_definition(root, table)
    sample_path = given.get("sample") or find_sample(root, table, data_files)
    others = [p for p in data_files if p != sample_path]
    queries = find_source("queries", root, given.get("queries"), others)
    results = find_source(
        "results", root, given.get("results"), [p for p in others if not queries or p != queries.path]
    )
    runs = find_source("runs", root, given.get("runs"), others)
    sources = set(definition.sources) if definition else set()
    checks, cases = find_checks(root, {table} | sources)
    own = [c for c in checks if c["table"] == table]
    upstream = [c for c in checks if c["table"] != table]
    keys = [*grains, *(c["key_columns"] for c in own if c.get("key_columns"))]
    if definition and definition.group_by:
        keys.append(definition.group_by)
    sample = profile_sample(sample_path, root, keys) if sample_path else None
    columns = sample["columns"] if sample else [c["column"] for c in (definition.columns if definition else [])]
    if definition:
        columns = list(dict.fromkeys([*columns, *(c["column"] for c in definition.columns)]))
    docs = read_documents(root, table, columns)
    by_column: dict[str, Any] = {}
    sql_by_column = {c["column"]: c for c in (definition.columns if definition else [])}
    for column in columns:
        found = list(docs["definitions"].get(column, []))
        if column in sql_by_column and definition:
            item = sql_by_column[column]
            found.append(
                {"where": f"{definition.file}:{item['line']}", "name": column, "text": item["expression"], "sql": True}
            )
        if not found:
            continue
        states = {d["where"]: term_states(d["text"], bool(d.get("sql"))) for d in found}
        hints = []
        for term in TERMS:
            seen = {where: s[term] for where, s in states.items() if term in s}
            included = sorted(w for w, s in seen.items() if s == "included")
            excluded = sorted(w for w, s in seen.items() if s == "excluded")
            silent_sql = [d["where"] for d in found if d.get("sql") and term not in states[d["where"]]]
            if included and (excluded or silent_sql):
                hints.append(
                    {"term": term, "included_in": included, "excluded_in": excluded, "not_in_the_sql": silent_sql}
                )
        by_column[column] = {"definitions": found, "term_conflicts": hints}
    product = docs["product"]
    if product:
        documented = set(product["columns_documented"])
        product["documented_not_in_table"] = sorted(documented - set(columns))
        product["in_table_not_documented"] = sorted(set(columns) - documented) if documented else []
    job = find_job(root, table, definition)
    personal_sql = sorted(c["column"] for c in sql_by_column.values() if personal_by_name(c["column"]))
    contracts: list[dict[str, str]] = []
    for path in walk(root, {".yaml", ".yml", ".md", ".json"}):
        if "contract" in rel(path, root).lower():
            text = path.read_text(encoding="utf-8", errors="replace")
            if re.search(rf"(?i)\b{re.escape(table)}\b|(?<![\w.]){re.escape(table.split('.')[-1])}\b", text):
                data = parse_yaml(text) if path.suffix.lower() in (".yaml", ".yml") else None
                role = "mentions the table"
                if isinstance(data, dict):
                    subject = data.get("table") or data.get("dataset") or data.get("model")
                    listed = data.get("consumers") or []
                    if isinstance(subject, str) and table_key(subject) == table:
                        role = "the table's own contract"
                    elif isinstance(listed, list) and table in {table_key(str(c)) for c in listed}:
                        role = "a source contract that lists the table as a consumer"
                contracts.append({"file": rel(path, root), "role": role})
    tracked = [
        f
        for f in (
            definition.file if definition else None,
            product["file"] if product else None,
            job["file"] if job else None,
        )
        if f
    ]
    return {
        "inputs": {
            "definition_sql": definition.file if definition else None,
            "sample": rel(sample_path, root) if sample_path else None,
            "query_log": {"file": rel(queries.path, root), "fields": queries.fields} if queries else None,
            "check_results": {"file": rel(results.path, root), "fields": results.fields} if results else None,
            "run_records": {"file": rel(runs.path, root), "fields": runs.fields} if runs else None,
            "job_definition": job["file"] if job else None,
            "documents": len(docs["documents"]),
        },
        "table": table,
        "definition": None
        if definition is None
        else {
            "file": definition.file,
            "line": definition.line,
            "build": definition.build,
            "sources": definition.sources,
            "group_by": definition.group_by,
            "columns": definition.columns,
            "personal_by_name": personal_sql,
        },
        "sample": sample,
        "consumers": consumers_of(queries, table),
        "checks": {
            "on_the_table": own,
            "on_its_sources": upstream,
            "results": check_results(results, checks, {table} | sources),
            "test_cases": {c["check"]: cases.get(c["check"], []) for c in checks},
        },
        "job": job,
        "freshness": freshness(runs, job, table),
        "documents": docs["documents"],
        "product_document": product,
        "definitions": by_column,
        "contract": contracts,
        "history": history(root, tracked),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", type=Path)
    parser.add_argument("--table", required=True, help="the served table, schema.table")
    parser.add_argument("--grain", action="append", default=[], help="a key to test on the sample, k1,k2 (repeatable)")
    parser.add_argument("--sample", type=Path)
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--results", type=Path, help="check results")
    parser.add_argument("--runs", type=Path, help="run records")
    args = parser.parse_args(argv)
    root = args.repo.resolve()
    if not root.is_dir():
        raise SystemExit(f"not a folder: {root}")
    grains = [[norm(k) for k in g.split(",") if k.strip()] for g in args.grain]
    given = {"sample": args.sample, "queries": args.queries, "results": args.results, "runs": args.runs}
    result = facts(root, table_key(args.table), grains, given)
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
