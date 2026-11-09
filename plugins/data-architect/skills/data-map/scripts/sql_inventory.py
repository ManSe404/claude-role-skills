#!/usr/bin/env python3
"""Read a repository's SQL, dbt models and notebooks into a table-level inventory and lineage.

Usage: python3 sql_inventory.py REPO [--checks]

Comments and string literals are removed before anything is read. It understands T-SQL, PostgreSQL and
Spark SQL statements, dbt (`ref`, `source`, schema.yml) and notebooks (`spark.sql`, `spark.table`,
`saveAsTable`, `%%sql`). It reports the tables, who reads and writes them, DDL columns and keys, tables
nobody in the repository reads, cycles, and dynamic SQL, which cannot be read and is listed for a person.

--checks adds hits for a review, in families. A hit is a place to read, not a finding: confirm each one.

Lineage is per table, not per column, and a script without `;` or GO gives coarser edges. Only names are
read from the code, never data. Read-only, standard library only, JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SKIP_DIRS = {".git", "node_modules", "target", "dbt_packages", "dbt_modules", ".venv", "venv", "__pycache__", "logs"}
SQL_SUFFIXES = {".sql", ".hql", ".ddl"}
TOKEN = re.compile(r'\[[^\]\n]+\]|"[^"\n]+"|`[^`\n]+`|[A-Za-z_@#][\w$@#]*|\d+(?:\.\d+)?|\S')
IDENT = re.compile(r'^(\[.+\]|".+"|`.+`|[A-Za-z_@#][\w$@#]*)$')
REF = re.compile(r"""\bref\(\s*['"]([^'"]+)['"](?:\s*,\s*['"]([^'"]+)['"])?\s*\)""")
SOURCE = re.compile(r"""\bsource\(\s*['"]([^'"]+)['"]\s*,\s*['"]([^'"]+)['"]\s*\)""")
FROM_FUNCTIONS = {"EXTRACT", "SUBSTRING", "TRIM", "OVERLAY", "POSITION"}
NOT_A_TABLE = {"SELECT", "VALUES", "LATERAL", "ONLY", "UNNEST", "TABLE", "WITH"}
CLAUSE = {
    "ON",
    "WHERE",
    "GROUP",
    "ORDER",
    "HAVING",
    "LIMIT",
    "UNION",
    "EXCEPT",
    "INTERSECT",
    "JOIN",
    "INNER",
    "LEFT",
    "RIGHT",
    "FULL",
    "CROSS",
    "OUTER",
    "USING",
    "SET",
    "WHEN",
    "WITH",
    "FROM",
    "SELECT",
    "QUALIFY",
    "WINDOW",
    "FETCH",
    "OFFSET",
    "INTO",
    "VALUES",
    "MERGE",
    "INSERT",
    "UPDATE",
    "DELETE",
    "GO",
    "BEGIN",
    "END",
    "NATURAL",
    "PIVOT",
    "UNPIVOT",
    "RETURNING",
}
CREATE_WORDS = {
    "OR",
    "REPLACE",
    "ALTER",
    "TEMP",
    "TEMPORARY",
    "GLOBAL",
    "LOCAL",
    "EXTERNAL",
    "MATERIALIZED",
    "UNIQUE",
    "CLUSTERED",
    "NONCLUSTERED",
    "UNLOGGED",
    "TRANSIENT",
    "SECURE",
}
COLUMN_END = {
    "NOT",
    "NULL",
    "DEFAULT",
    "PRIMARY",
    "REFERENCES",
    "IDENTITY",
    "CONSTRAINT",
    "UNIQUE",
    "CHECK",
    "COLLATE",
    "GENERATED",
    "COMMENT",
}
MONEY = re.compile(
    r"amount|price|cost|total|revenue|(^|_)net(_|$)|gross|(^|_)tax|(^|_)vat|(^|_)fee|margin|discount", re.I
)
PERSONAL = re.compile(
    r"e_?mail|phone|mobile|jmbg|national_?id|(^|_)oib(_|$)|iban|birth|address|first_?name|last_?name|full_?name|surname",
    re.I,
)
MASKS = {
    "HASHBYTES",
    "SHA2",
    "SHA256",
    "MD5",
    "HASH",
    "MASK",
    "REDACT",
    "ENCRYPT",
    "LEFT",
    "RIGHT",
    "SUBSTRING",
    "SUBSTR",
}
SPARK_SQL = re.compile(r"""spark\.sql\(\s*(f?)("{3}|'{3}|"|')(.*?)\2""", re.S)
SPARK_READ = re.compile(r"""(?:spark\.read\.table|spark\.table|\.read\.table)\(\s*f?["']([^"']+)["']""")
SPARK_WRITE = re.compile(r"""\.(?:saveAsTable|insertInto)\(\s*f?["']([^"']+)["']""")


@dataclass
class Join:
    table: str
    alias: str
    columns: list[str]
    line: int


@dataclass
class Statement:
    line: int
    reads: list[tuple[str, int]] = field(default_factory=list)
    writes: list[tuple[str, int, str]] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    stars: list[tuple[str, int]] = field(default_factory=list)
    joins: list[Join] = field(default_factory=list)
    updates: list[tuple[list[str], int]] = field(default_factory=list)
    guarded: bool = False


@dataclass
class Parsed:
    statements: list[Statement] = field(default_factory=list)
    ctes: dict[str, str | None] = field(default_factory=dict)
    ddl: list[dict[str, Any]] = field(default_factory=list)
    procedures: list[tuple[str, int]] = field(default_factory=list)
    calls: list[tuple[str, int]] = field(default_factory=list)
    dynamic: list[tuple[int, str]] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)
    personal: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class Job:
    file: str
    name: str
    kind: str  # model, script, query or notebook
    parsed: Parsed
    raw: list[str]
    where: dict[int, str] = field(default_factory=dict)


def clean_sql(text: str) -> tuple[str, dict[str, str], set[str]]:
    """Blank comments, strings and Jinja, keeping every line where it was. A ref() or source() becomes a token."""
    out = list(text)
    refs: dict[str, str] = {}
    sources: set[str] = set()

    def wipe(start: int, end: int) -> None:
        for k in range(start, end):
            if out[k] != "\n":
                out[k] = " "

    i, n = 0, len(text)
    while i < n:
        two = text[i : i + 2]
        if two in ("{{", "{%", "{#"):
            close = {"{{": "}}", "{%": "%}", "{#": "#}"}[two]
            end = text.find(close, i + 2)
            end = n if end < 0 else end + 2
            body = text[i:end]
            wipe(i, end)
            found_ref = REF.search(body) if two == "{{" else None
            found_source = SOURCE.search(body) if two == "{{" else None
            name = None
            if found_ref:
                name = found_ref.group(2) or found_ref.group(1)
            elif found_source:
                name = f"{found_source.group(1)}.{found_source.group(2)}"
                sources.add(name.lower())
            if name:
                token = f"__J{len(refs)}__"
                refs[token] = name
                out[i : i + len(token)] = token
            i = end
        elif two == "--":
            end = text.find("\n", i)
            end = n if end < 0 else end
            wipe(i, end)
            i = end
        elif two == "/*":
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            wipe(i, end)
            i = end
        elif text[i] == "'":
            j = i + 1
            while j < n:
                if text[j] == "'" and text[j + 1 : j + 2] == "'":
                    j += 2
                elif text[j] == "'":
                    break
                else:
                    j += 1
            wipe(i, min(j + 1, n))
            i = j + 1
        else:
            i += 1
    return "".join(out), refs, sources


def tokenize(clean: str, offset: int = 0) -> list[tuple[str, int]]:
    tokens = []
    line, pos = 1 + offset, 0
    for match in TOKEN.finditer(clean):
        line += clean.count("\n", pos, match.start())
        pos = match.start()
        tokens.append((match.group(), line))
    return tokens


def unquote(name: str) -> str:
    return name[1:-1] if name[:1] in '["`' else name


def parse_sql(text: str, offset: int = 0) -> Parsed:
    clean, refs, sources = clean_sql(text)
    tokens = tokenize(clean, offset)
    up = [t.upper() for t, _ in tokens]
    n = len(tokens)
    result = Parsed(sources=sources)
    stmt = Statement(line=tokens[0][1] if tokens else 1)

    def tok(j: int) -> str:
        return tokens[j][0] if 0 <= j < n else ""

    def word(j: int) -> str:
        return up[j] if 0 <= j < n else ""

    def name_at(j: int) -> tuple[str | None, int]:
        if not IDENT.match(tok(j)):
            return None, j
        parts = [unquote(tok(j))]
        k = j + 1
        while tok(k) == ".":
            if tok(k + 1) == ".":
                k += 1
                continue
            if not IDENT.match(tok(k + 1)):
                break
            parts.append(unquote(tok(k + 1)))
            k += 2
        return refs.get(parts[0], ".".join(parts)) if len(parts) == 1 else ".".join(parts), k

    def after_parens(j: int) -> int:
        depth = 0
        while j < n:
            if tok(j) == "(":
                depth += 1
            elif tok(j) == ")":
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        return j

    def alias_at(k: int) -> tuple[str | None, int]:
        if word(k) == "AS" and IDENT.match(tok(k + 1)):
            return unquote(tok(k + 1)), k + 2
        if IDENT.match(tok(k)) and word(k) not in CLAUSE and word(k) != "AS":
            return unquote(tok(k)), k + 1
        return None, k

    def skip_hints(k: int) -> int:
        return after_parens(k + 1) if word(k) == "WITH" and tok(k + 1) == "(" else k

    def table_refs(j: int, many: bool) -> int:
        while True:
            name, k = name_at(j)
            if name is None or word(j) in NOT_A_TABLE or tok(k) == "(":
                return j
            stmt.reads.append((name, tokens[j][1]))
            alias, k = alias_at(k)
            if alias:
                stmt.aliases[alias.lower()] = name
            k = skip_hints(k)
            if many and tok(k) == ",":
                j = k + 1
                continue
            return k

    def write(name: str | None, how: str, line: int) -> None:
        if name and not name.startswith(("@", "#")):
            stmt.writes.append((name, line, how))

    def cte_at(j: int) -> bool:
        name, k = name_at(j)
        if name is None or "." in name or name.startswith("__J"):
            return False
        if tok(k) == "(":
            k = after_parens(k)
        if word(k) != "AS" or tok(k + 1) != "(":
            return False
        body = k + 2
        through = None
        if word(body) == "SELECT" and tok(body + 1) == "*" and word(body + 2) == "FROM":
            source, end = name_at(body + 3)
            if source and tok(end) == ")":
                through = source
        result.ctes[name.lower()] = through
        return True

    def finish() -> None:
        nonlocal stmt
        stmt.writes = [
            (stmt.aliases.get(w.lower(), w) if "." not in w else w, line, how) for w, line, how in stmt.writes
        ]
        if stmt.reads or stmt.writes or stmt.stars or stmt.joins:
            result.statements.append(stmt)
        stmt = Statement(line=tokens[i + 1][1] if i + 1 < n else 1)

    stack: list[str] = []
    star_line: int | None = None
    pending_update = False
    in_select = False
    i = 0
    while i < n:
        text_now, line = tokens[i]
        now = up[i]
        if text_now == "(":
            stack.append(word(i - 1))
        elif text_now == ")":
            if stack:
                stack.pop()
        elif text_now == ";" or (now == "GO" and tok(i + 1) != "" and tokens[i + 1][1] != line):
            finish()
            in_select = False
        elif now == "WITH":
            j = i + 2 if word(i + 1) == "RECURSIVE" else i + 1
            if tok(i + 1) == "(":
                i = after_parens(i + 1)
                continue
            cte_at(j)
        elif text_now == ",":
            cte_at(i + 1)
        elif now == "SELECT":
            in_select = True
            j = i + 1
            if word(j) == "DISTINCT":
                j += 1
            if word(j) == "TOP":
                j += 2
            if tok(j) == "*":
                star_line = line
        elif now == "FROM":
            if (stack and stack[-1] in FROM_FUNCTIONS) or word(i - 1) in ("NEXT", "PRIOR", "FIRST", "LAST"):
                i += 1
                continue
            in_select = False
            if word(i - 1) == "DELETE":
                name, k = name_at(i + 1)
                write(name, "delete", line)
                i = k
                continue
            if star_line is not None:
                name, k = name_at(i + 1)
                if name and tok(k) != "(":
                    stmt.stars.append((name, star_line))
                star_line = None
            i = table_refs(i + 1, many=True)
            continue
        elif now == "JOIN":
            start = i + 1
            k = table_refs(start, many=False)
            if k > start:
                table, after = name_at(start)
                alias, _ = alias_at(after)
                short = (alias or (table or "").rsplit(".", 1)[-1]).lower()
                columns: list[str] = []
                if word(k) == "ON":
                    depth, j = 0, k + 1
                    while j < n:
                        if tok(j) == "(":
                            depth += 1
                        elif tok(j) == ")":
                            if depth == 0:
                                break
                            depth -= 1
                        elif tok(j) == ";" or (depth == 0 and word(j) in CLAUSE):
                            break
                        found, e = name_at(j)
                        if found and "." in found:
                            first, last = found.rsplit(".", 1)
                            if first.lower() == short:
                                columns.append(unquote(last).lower())
                            j = e
                            continue
                        j += 1
                stmt.joins.append(Join(table or "", short, columns, line))
            i = k
            continue
        elif now == "USING" and tok(i + 1) != "(":
            i = table_refs(i + 1, many=False)
            continue
        elif now == "INSERT":
            j = i + 1
            while word(j) in ("INTO", "OVERWRITE", "TABLE"):
                if word(j) == "OVERWRITE":
                    stmt.guarded = True
                j += 1
            name, k = name_at(j)
            if name and word(j) not in ("VALUES", "DEFAULT", "SELECT"):
                write(name, "insert", line)
                i = k
                continue
        elif now == "INTO":
            name, k = name_at(i + 1)
            if name:
                write(name, "into", line)
                i = k
                continue
        elif now == "MERGE":
            j = i + 1
            if word(j) == "TOP":
                j = after_parens(j + 1)
            if word(j) == "INTO":
                j += 1
            name, k = name_at(j)
            write(name, "merge", line)
            alias, k = alias_at(k)
            if alias and name:
                stmt.aliases[alias.lower()] = name
            i = k
            continue
        elif now == "UPDATE":
            pending_update = True
            name, k = name_at(i + 1)
            if name and word(i + 1) not in ("SET", "STATISTICS") and word(i + 1) not in CLAUSE:
                write(name, "update", line)
                i = k
                continue
        elif now == "SET" and pending_update:
            pending_update = False
            assigned: list[str] = []
            depth, j = 0, i + 1
            while j < n:
                if tok(j) == "(":
                    depth += 1
                elif tok(j) == ")":
                    depth -= 1
                elif tok(j) == ";" or (depth == 0 and word(j) in ("WHEN", "WHERE", "FROM", "OUTPUT")):
                    break
                elif depth == 0:
                    found, e = name_at(j)
                    if found and tok(e) == "=":
                        assigned.append(found.rsplit(".", 1)[-1].lower())
                        j = e
                j += 1
            stmt.updates.append((assigned, line))
        elif now == "DELETE" and word(i + 1) != "FROM":
            name, k = name_at(i + 1)
            if name and word(i + 1) not in CLAUSE and tok(k - 1) != "":
                write(name, "delete", line)
                i = k
                continue
        elif now == "TRUNCATE" and word(i + 1) == "TABLE":
            name, k = name_at(i + 2)
            write(name, "truncate", line)
            i = k
            continue
        elif now == "CREATE":
            j = i + 1
            temporary = False
            while word(j) in CREATE_WORDS:
                temporary = temporary or word(j) in ("TEMP", "TEMPORARY")
                j += 1
            what = word(j)
            if what in ("PROC", "PROCEDURE", "FUNCTION", "TRIGGER"):
                name, k = name_at(j + 1)
                if name:
                    result.procedures.append((name, line))
                i = k
                continue
            if what in ("TABLE", "VIEW"):
                j += 1
                if word(j) == "IF":
                    j += 3
                name, k = name_at(j)
                if name and temporary:
                    result.ctes[name.lower()] = None
                elif name:
                    write(name, "create", line)
                    if what == "TABLE" and tok(k) == "(":
                        result.ddl.append(parse_ddl(name, line, tokens, k))
                i = k
                continue
        elif now in ("EXEC", "EXECUTE"):
            following = tok(i + 1)
            if following == "(" or following.lower() == "sp_executesql" or (following[:1] == "@" and tok(i + 2) != "="):
                result.dynamic.append((line, "EXEC"))
            elif IDENT.match(following):
                name, _ = name_at(i + 1)
                if name:
                    result.calls.append((name, line))
        elif now == "EXISTS" and word(i - 1) == "NOT":
            stmt.guarded = True
        elif in_select and IDENT.match(text_now) and word(i - 1) != "AS" and tok(i + 1) != "(":
            found, e = name_at(i)
            last = (found or "").rsplit(".", 1)[-1]
            if PERSONAL.search(last) and not any(f in MASKS for f in stack):
                result.personal.append((last.lower(), line))
            i = e
            continue
        i += 1
    i = n - 1
    finish()
    return result


def parse_ddl(name: str, line: int, tokens: list[tuple[str, int]], start: int) -> dict[str, Any]:
    """Columns and keys of a CREATE TABLE whose column list opens at tokens[start]."""
    items: list[list[str]] = [[]]
    lines: list[int] = [tokens[start][1]]
    depth, j = 0, start
    while j < len(tokens):
        t = tokens[j][0]
        if t == "(":
            depth += 1
            if depth > 1:
                items[-1].append(t)
        elif t == ")":
            depth -= 1
            if depth == 0:
                break
            items[-1].append(t)
        elif t == "," and depth == 1:
            items.append([])
            lines.append(tokens[j + 1][1] if j + 1 < len(tokens) else tokens[j][1])
        else:
            if not items[-1]:
                lines[-1] = tokens[j][1]
            items[-1].append(t)
        j += 1

    def parens(words: list[str], at: int) -> list[str]:
        names: list[str] = []
        k = at + 1
        while k < len(words) and words[k] != ")":
            if words[k] != ",":
                names.append(unquote(words[k]).lower())
            k += 1
        return names

    columns: list[dict[str, Any]] = []
    primary: list[str] = []
    foreign: list[dict[str, Any]] = []
    for words, at in zip(items, lines, strict=True):
        if not words:
            continue
        upper = [w.upper() for w in words]
        if upper[0] == "CONSTRAINT":
            words, upper = words[2:], upper[2:]
        if upper[0] == "PRIMARY" and "(" in words:
            primary = parens(words, words.index("("))
        elif upper[0] == "FOREIGN" and "REFERENCES" in upper:
            ref = upper.index("REFERENCES")
            foreign.append({"columns": parens(words, words.index("(")), "references": unquote(words[ref + 1]).lower()})
        elif upper[0] not in ("UNIQUE", "CHECK", "INDEX", "KEY", "PERIOD"):
            cut = next((k for k in range(1, len(upper)) if upper[k] in COLUMN_END), len(upper))
            column: dict[str, Any] = {
                "name": unquote(words[0]).lower(),
                "type": "".join(unquote(w) if w[:1] == "[" else w for w in words[1:cut]).upper(),
                "line": at,
                "not_null": "NOT" in upper[cut:],
            }
            columns.append(column)
            if "PRIMARY" in upper[cut:]:
                primary.append(column["name"])
    return {"name": name, "line": line, "columns": columns, "primary_key": primary, "foreign_keys": foreign}


def parse_dbt_yaml(text: str) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    """Sources and model tests from a dbt schema file, read by indentation (no YAML in the standard library)."""
    sources: dict[str, list[str]] = {}
    models: dict[str, dict[str, Any]] = {}
    section = ""
    source: str | None = None
    model: dict[str, Any] | None = None
    column: str | None = None
    columns_at = tests_at = -1
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        body = line.strip()
        if indent == 0:
            section = body.split(":")[0]
            source, model, column = None, None, None
            columns_at = tests_at = -1
            continue
        if tests_at >= 0 and indent <= tests_at and not (indent == tests_at and body.startswith("- ")):
            tests_at = -1
        named = re.match(r"-\s+name:\s*['\"]?([\w.-]+)", body)
        if section == "sources":
            if (named and source is None) or (named and indent <= columns_at):
                source = named.group(1)
                sources[source] = []
                columns_at = indent
            elif named and source:
                sources[source].append(named.group(1))
        elif section == "models":
            if named and (columns_at < 0 or indent <= columns_at):
                model = {"line": number, "columns": {}, "tests": []}
                models[named.group(1)] = model
                columns_at, tests_at, column = -1, -1, None
            elif named and model is not None:
                column = named.group(1)
                model["columns"][column] = []
                tests_at = -1
            elif body in ("columns:", "- columns:"):
                columns_at = indent
            elif body in ("tests:", "data_tests:"):
                tests_at = indent
            elif tests_at >= 0 and model is not None:
                test = re.match(r"-\s+([\w.]+)", body)
                if test:
                    (model["columns"][column] if column else model["tests"]).append(test.group(1))
    return sources, models


def parse_notebook(cells: list[tuple[int, str]]) -> tuple[Parsed, dict[int, str]]:
    """Spark reads and writes from code cells, given as (cell number, source). Lines are numbered across cells."""
    merged = Parsed()
    where: dict[int, str] = {}
    offset = 0
    for cell, source in cells:
        lines = source.split("\n")
        for k in range(len(lines)):
            where[offset + k + 1] = f"cell {cell}, line {k + 1}"
        if source.lstrip().startswith("%%sql"):
            _absorb(merged, parse_sql(source.replace("%%sql", "     ", 1), offset))
        else:
            _absorb(merged, parse_python(source, offset))
        offset += len(lines)
    return merged, where


def parse_python(code: str, offset: int = 0) -> Parsed:
    merged = Parsed()
    stmt = Statement(line=1 + offset)

    def at(pos: int) -> int:
        return offset + code.count("\n", 0, pos) + 1

    for match in SPARK_READ.finditer(code):
        stmt.reads.append((match.group(1), at(match.start())))
    for match in SPARK_WRITE.finditer(code):
        stmt.writes.append((match.group(1), at(match.start()), "spark"))
    if stmt.reads or stmt.writes:
        merged.statements.append(stmt)
    for match in SPARK_SQL.finditer(code):
        if match.group(1) and "{" in match.group(3):
            merged.dynamic.append((at(match.start()), "f-string in spark.sql"))
        else:
            _absorb(merged, parse_sql(match.group(3), at(match.start(3)) - 1))
    return merged


def _absorb(into: Parsed, part: Parsed) -> None:
    into.statements += part.statements
    into.ctes.update(part.ctes)
    into.ddl += part.ddl
    into.procedures += part.procedures
    into.calls += part.calls
    into.dynamic += part.dynamic
    into.sources |= part.sources
    into.personal += part.personal


def layer_of(path: str, name: str) -> str | None:
    p = f"/{path.lower()}"
    schema, _, short = name.lower().rpartition(".")
    schema = f"/{schema}/"
    if re.search(r"/(reports?|exports?|analyses|dashboards)/", p):
        return "consumer"
    for layer, folders, prefixes in (
        ("staging", "staging|bronze|raw|landing", ("stg_", "raw_", "bronze_")),
        ("intermediate", "intermediate|silver", ("int_", "silver_")),
        ("marts", "marts?|gold", ("fct_", "fact_", "dim_", "mart_", "gold_", "rpt_")),
    ):
        if re.search(f"/({folders})/", p) or re.search(f"/({folders})/", schema) or short.startswith(prefixes):
            return layer
    return None


def collect(repo: Path) -> tuple[list[Job], dict[str, list[str]], dict[str, dict[str, Any]], Counter[str], list[str]]:
    is_dbt = any(p.name == "dbt_project.yml" for p in repo.rglob("dbt_project.yml"))
    jobs: list[Job] = []
    sources: dict[str, list[str]] = {}
    tests: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    notes: list[str] = []
    for path in sorted(p for p in repo.rglob("*") if p.is_file()):
        rel = path.relative_to(repo)
        if SKIP_DIRS & set(rel.parts):
            continue
        suffix = path.suffix.lower()
        if suffix not in (*SQL_SUFFIXES, ".ipynb", ".py", ".yml", ".yaml"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        file = rel.as_posix()
        if suffix in SQL_SUFFIXES:
            counts["sql"] += 1
            modeled = is_dbt and "models" in rel.parts
            jobs.append(Job(file, path.stem, "model" if modeled else "script", parse_sql(text), text.splitlines()))
        elif suffix == ".ipynb":
            counts["notebooks"] += 1
            try:
                book = json.loads(text)
            except json.JSONDecodeError:
                notes.append(f"{file}: not valid JSON, skipped")
                continue
            cells = [
                (i + 1, "".join(c.get("source", [])))
                for i, c in enumerate(book.get("cells", []))
                if c.get("cell_type") == "code"
            ]
            parsed, where = parse_notebook(cells)
            raw = [line for _, source in cells for line in source.split("\n")]
            jobs.append(Job(file, path.stem, "notebook", parsed, raw, where))
        elif suffix == ".py":
            if "spark." in text or ".saveAsTable" in text:
                counts["python"] += 1
                jobs.append(Job(file, path.stem, "notebook", parse_python(text), text.splitlines()))
        elif is_dbt and path.name != "dbt_project.yml" and ("models:" in text or "sources:" in text):
            counts["dbt_yaml"] += 1
            found_sources, found_models = parse_dbt_yaml(text)
            for key, tables in found_sources.items():
                sources.setdefault(key, []).extend(tables)
            for key, model in found_models.items():
                tests[key] = {**model, "file": file}
    return jobs, sources, tests, counts, notes


class Names:
    """One name per table, however the code spells it."""

    def __init__(self, jobs: list[Job], sources: dict[str, list[str]]) -> None:
        self.models = {j.name.lower() for j in jobs if j.kind == "model"}
        self.sources = {f"{s}.{t}".lower() for s, tables in sources.items() for t in tables}
        for job in jobs:
            self.sources |= job.parsed.sources
        self.declared: set[str] = set()
        for job in jobs:
            for stmt in job.parsed.statements:
                self.declared |= {self.short(w) for w, _, _ in stmt.writes if job.kind != "model"}

    @staticmethod
    def short(name: str) -> str:
        return ".".join(name.lower().split(".")[-2:])

    def resolve(self, name: str) -> str:
        c = self.short(name)
        last = c.rsplit(".", 1)[-1]
        if c in self.sources or (c in self.declared and "." in c):
            return c
        if last in self.models:
            return last
        if "." not in c:
            matches = sorted(d for d in self.declared if d.endswith(f".{c}"))
            if len(matches) == 1:
                return matches[0]
        return c


def lineage(jobs: list[Job], names: Names) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    objects: dict[str, dict[str, Any]] = {}

    def node(name: str, kind: str, file: str | None = None, line: int | None = None) -> None:
        rank = ("external", "query", "view", "table", "model", "source")
        if name not in objects or rank.index(kind) > rank.index(objects[name]["kind"]):
            previous = objects.get(name, {})
            objects[name] = {
                "name": name,
                "kind": kind,
                "file": file or previous.get("file"),
                "line": line or previous.get("line"),
                "layer": layer_of(file or "", name) or previous.get("layer"),
            }

    def link(read: str, target: str, job: Job, line: int) -> None:
        if read != target:
            edges.setdefault((read, target), {"from": read, "to": target, "file": job.file, "line": line})

    for job in jobs:
        has_writes = any(stmt.writes for stmt in job.parsed.statements)

        def reads(stmt: Statement, ctes: dict[str, str | None] = job.parsed.ctes) -> list[tuple[str, int]]:
            return [
                (names.resolve(r), line)
                for r, line in stmt.reads
                if r.lower() not in ctes and not r.startswith(("@", "#"))
            ]

        if job.kind == "model":
            target = job.name.lower()
            node(target, "model", job.file, 1)
            for stmt in job.parsed.statements:
                for read, line in reads(stmt):
                    node(read, "source" if read in names.sources else "external")
                    link(read, target, job, line)
            continue
        if job.kind == "notebook":
            everything = [r for stmt in job.parsed.statements for r in reads(stmt)]
            targets = [(w, line) for stmt in job.parsed.statements for w, line, _ in stmt.writes]
            for read, _ in everything:
                node(read, "source" if read in names.sources else "external")
            for name, line in targets:
                target = names.resolve(name)
                node(target, "table", job.file, line)
                for read, read_line in everything:
                    link(read, target, job, read_line)
            continue
        for stmt in job.parsed.statements:
            found = reads(stmt)
            for read, _ in found:
                node(read, "source" if read in names.sources else "external")
            for name, line, _ in stmt.writes:
                target = names.resolve(name)
                node(target, "table", job.file, line)
                for read, read_line in found:
                    link(read, target, job, read_line)
            if not has_writes and found:
                target = job.name.lower()
                node(target, "query", job.file, stmt.line)
                for read, read_line in found:
                    link(read, target, job, read_line)
    for name in names.sources:
        node(name, "source")
    for entry in objects.values():
        entry["layer"] = entry["layer"] or layer_of("", entry["name"])
        if entry["kind"] == "source":
            entry["layer"] = "raw"
        entry["read_by"] = sum(1 for e in edges.values() if e["from"] == entry["name"])
        entry["fed_by"] = sum(1 for e in edges.values() if e["to"] == entry["name"])
    return sorted(edges.values(), key=lambda e: (e["from"], e["to"])), objects


def cycles(edges: list[dict[str, Any]]) -> list[list[str]]:
    """Strongly connected groups of more than one table (Tarjan, iterative enough for repository sizes)."""
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 10_000))
    graph: dict[str, list[str]] = {}
    for edge in edges:
        graph.setdefault(edge["from"], []).append(edge["to"])
        graph.setdefault(edge["to"], [])
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on: set[str] = set()
    found: list[list[str]] = []

    def visit(v: str) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        on.add(v)
        for w in graph[v]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            group = []
            while True:
                w = stack.pop()
                on.discard(w)
                group.append(w)
                if w == v:
                    break
            if len(group) > 1:
                found.append(sorted(group))

    for v in sorted(graph):
        if v not in index:
            visit(v)
    return found


def checks(
    jobs: list[Job],
    names: Names,
    edges: list[dict[str, Any]],
    objects: dict[str, dict[str, Any]],
    tests: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    keys: dict[str, set[str]] = {}
    for job in jobs:
        for table in job.parsed.ddl:
            if table["primary_key"]:
                keys[names.resolve(table["name"])] = set(table["primary_key"])
    for model, info in tests.items():
        unique = {c.lower() for c, found in info["columns"].items() if "unique" in found}
        if unique:
            keys[model.lower()] = unique
    hits: list[dict[str, Any]] = []

    def hit(family: str, job: Job, line: int, detail: str) -> None:
        index = line - 1
        text = job.raw[index].strip()[:160] if 0 <= index < len(job.raw) else ""
        place = job.where.get(line)
        entry = {"family": family, "file": job.file, "line": line, "text": text, "detail": detail}
        if place:
            entry["where"] = place
        hits.append(entry)

    by_file = {j.file: j for j in jobs}
    for job in jobs:
        parsed = job.parsed
        layer = layer_of(job.file, job.name)
        for table in parsed.ddl:
            for column in table["columns"]:
                if re.match(r"FLOAT|REAL|DOUBLE", column["type"]) and MONEY.search(column["name"]):
                    hit("float_money", job, column["line"], f"{table['name']}.{column['name']} is {column['type']}")
        for line, kind in parsed.dynamic:
            whole = "\n".join(job.raw)
            concat = kind == "EXEC" and bool(re.search(r"(?is)set\s+@\w+\s*=.*?\+\s*@\w+", whole))
            hit("dynamic_sql", job, line, f"{kind}{', built by concatenating a value' if concat else ''}")
        strong = {
            names.resolve(w)
            for stmt in parsed.statements
            for w, _, how in stmt.writes
            if how in ("delete", "truncate", "merge")
        }
        for stmt in parsed.statements:
            if job.kind == "script" and not stmt.guarded:
                for name, line, how in stmt.writes:
                    if how == "insert" and names.resolve(name) not in strong:
                        hit("rerun_unsafe", job, line, f"inserts into {name}; nothing clears or merges it in this file")
            if layer != "staging":
                # `with a as (select * from x)` only gives a table a local name: not a wide select.
                through = {t.lower() for t in parsed.ctes.values() if t}
                for name, line in stmt.stars:
                    if name.lower() not in parsed.ctes and name.lower() not in through:
                        hit("select_star", job, line, f"SELECT * from {name}")
            for columns, line in stmt.updates:
                targets = [w for w, _, how in stmt.writes if how in ("merge", "update")]
                if columns and any("dim" in t.lower().rsplit(".", 1)[-1] for t in targets):
                    hit("overwrite_history", job, line, f"{targets[0]}: overwrites {', '.join(columns)} in place")
            for join in stmt.joins:
                joined = names.resolve(parsed.ctes.get(join.table.lower()) or join.table)
                known = keys.get(joined)
                if known and join.columns and not known & set(join.columns):
                    keys_text = ", ".join(sorted(known))
                    hit(
                        "fanout_candidate",
                        job,
                        join.line,
                        f"joins {joined} on {', '.join(join.columns)}; key: {keys_text}",
                    )
        if layer in ("consumer", "marts"):
            for column, line in parsed.personal:
                hit("personal_served", job, line, f"{column} selected in the {layer} layer with no mask")
    for edge in edges:
        source, target = objects[edge["from"]], objects[edge["to"]]
        skipped = (target["layer"] == "consumer" and source["layer"] in ("raw", "staging")) or (
            target["layer"] == "marts" and source["layer"] == "raw"
        )
        job_of = by_file.get(edge["file"])
        if skipped and job_of:
            hit(
                "layer_skip",
                job_of,
                edge["line"],
                f"{edge['to']} ({target['layer']}) reads {edge['from']} ({source['layer']})",
            )
    for job in jobs:
        if job.kind == "model" and job.name.lower().startswith(("fct_", "fact_", "dim_")):
            spec = tests.get(job.name)
            tested = spec and (
                spec["tests"] or any({"unique", "not_null"} & set(found) for found in spec["columns"].values())
            )
            if not tested:
                hit("no_key_tests", job, 1, f"{job.name} has no unique or not_null test")
    return sorted(hits, key=lambda h: (h["family"], h["file"], h["line"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read SQL, dbt and notebooks into a table-level inventory.")
    parser.add_argument("repo", type=Path)
    parser.add_argument("--checks", action="store_true", help="add hits for a review, per family")
    args = parser.parse_args(argv)
    if not args.repo.is_dir():
        print(f"not a folder: {args.repo}", file=sys.stderr)
        return 2
    jobs, sources, tests, counts, notes = collect(args.repo)
    names = Names(jobs, sources)
    edges, objects = lineage(jobs, names)
    result: dict[str, Any] = {
        "files": dict(counts),
        "layers": dict(Counter(str(o["layer"]) for o in objects.values())),
        "objects": sorted(objects.values(), key=lambda o: o["name"]),
        "edges": edges,
        "unread": sorted(o["name"] for o in objects.values() if o["kind"] in ("model", "table") and not o["read_by"]),
        "cycles": cycles(edges),
        "dynamic": [
            {"file": j.file, "line": line, "kind": kind, **({"where": j.where[line]} if line in j.where else {})}
            for j in jobs
            for line, kind in j.parsed.dynamic
        ],
        "ddl": [{"file": j.file, **table} for j in jobs for table in j.parsed.ddl],
        "procedures": [{"file": j.file, "name": n, "line": line} for j in jobs for n, line in j.parsed.procedures],
        "dbt": {
            "sources": sources,
            "tests": {
                k: {"file": v["file"], "columns": v["columns"], "tests": v["tests"]} for k, v in sorted(tests.items())
            },
        },
        "notes": notes,
    }
    if args.checks:
        found = checks(jobs, names, edges, objects, tests)
        result["checks"] = found
        result["check_counts"] = dict(Counter(h["family"] for h in found))
    json.dump(result, sys.stdout, indent=1, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
