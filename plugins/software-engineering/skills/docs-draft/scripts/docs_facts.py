#!/usr/bin/env python3
"""What a repository exposes and what its documents say about it, so a document can be written from facts.

Usage: python3 docs_facts.py REPO [--path SUBDIR] [--docs FILE ...]

What comes out, read-only, standard library only, JSON on stdout:
- `docs`: every document found (README*, CONTRIBUTING*, CHANGELOG*, docs/**, adr/**, *.md at the top) with its headings
  and the commands in its code blocks, plus any file given with --docs
- `exposed`: what the code offers, each with where it is defined and the documents that mention it:
    entry        console scripts, `python -m package`, Dockerfile CMD and ENTRYPOINT, `if __name__ == "__main__"`
    command      argparse subparsers, click and typer commands, with their help text
    flag         argparse, click and typer options, with the command they belong to and their help text
    route        HTTP routes: decorators (@app.get, @router.post, @bp.route), add_url_rule, Django path(), and the
                 literal paths an http.server handler compares self.path with
    config       names read from the environment (os.environ, os.getenv), the fields of a Settings class, and the
                 keys of example configuration files (names only, never a value)
    target       Makefile targets, package.json scripts, CI steps that run a command
    job          scheduled jobs: job files (jobs/*.yaml with name, schedule, steps), Airflow DAGs (dag_id, schedule,
                 task ids), CI schedules and crontab lines, each with its schedule read as text (daily at 06:30)
  `status` is documented (a document names it), undocumented, or guessed (found by a shallow pattern)
- `stale`: commands, flags, routes, configuration names and job names a document uses that the code does not have,
  and a time a document gives for a job that disagrees with the job's schedule
- `counts`: exposed items by kind and status

Files named .env or .env.* are never opened; an example file gives key names only. Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SKIP_DIRS = {
    ".git",
    ".hg",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "site-packages",
}
MAX_BYTES = 2_000_000
DOC_NAME = re.compile(r"^(?:README|CONTRIBUTING|CHANGELOG|INSTALL|USAGE|SETUP)(?:\.[\w-]+)?$", re.IGNORECASE)
DOC_DIRS = {"docs", "doc", "adr", "adrs", "wiki"}
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE = re.compile(r"^\s*(```|~~~)")
INDENTED = re.compile(r"^(?: {4}|\t)(\S.*)$")
INLINE_CODE = re.compile(r"`([^`\n]+)`")
COMMAND_WORDS = (
    "python",
    "python3",
    "py",
    "pip",
    "uv",
    "make",
    "npm",
    "pnpm",
    "yarn",
    "npx",
    "node",
    "docker",
    "docker-compose",
    "go",
    "cargo",
    "dotnet",
    "poetry",
    "pytest",
    "ruff",
    "mypy",
    "bash",
    "sh",
    "curl",
)
ENV_READ = re.compile(r"""(?:os\.)?(?:environ(?:\.get)?|getenv)\s*[\[(]\s*["']([A-Z][A-Z0-9_]{2,})["']""")
ENV_FILE_KEY = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][\w.-]*)\s*[=:]", re.MULTILINE)
UPPER_NAME = re.compile(r"\b([A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+)\b")
ROUTE_DECORATOR = re.compile(
    r"""@(?:\w+\.)?(get|post|put|patch|delete|route|api_route|websocket)\(\s*["']([^"']+)["']"""
)
ROUTE_METHOD = re.compile(r"""\b(?:add_url_rule|add_api_route|add_route|path|re_path|url)\(\s*r?["']([^"']+)["']""")
HANDLER_PATH = re.compile(r"""self\.path(?:\.startswith)?\s*(?:==|\()\s*["']([^"']+)["']""")
DOC_ROUTE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[\w/<>{}:.-]*)")
MAKE_TARGET = re.compile(r"^([A-Za-z_][\w.-]*):(?!=)", re.MULTILINE)
DOCKER_CMD = re.compile(r"^(?:CMD|ENTRYPOINT)\s+(.+)$", re.MULTILINE)
CI_RUN = re.compile(r"^\s*-?\s*run:\s*(.+)$", re.MULTILINE)
SCRIPTS_TABLE = re.compile(r"^\[project\.scripts\]\s*$(.*?)(?=^\[|\Z)", re.MULTILINE | re.DOTALL)
SCRIPT_LINE = re.compile(r"^\s*([\w.-]+)\s*=\s*[\"']([\w.]+):(\w+)[\"']", re.MULTILINE)
MAIN_GUARD = re.compile(r"""^if\s+__name__\s*==\s*["']__main__["']""", re.MULTILINE)
EXAMPLE_FILE = re.compile(
    r"(^|/)(\.env\.example|\.env\.sample|[^/]+\.example|[^/]+\.sample|example\.[^/]+)$", re.IGNORECASE
)
SETTINGS_CLASS = re.compile(r"(?i)settings|config")
JOB_KEY = re.compile(r"^(name|schedule|cron|timezone|enabled|description|sla):\s*(.*)$", re.MULTILINE)
JOB_STEP = re.compile(r"^\s*-\s*(?:task|name|id|step):\s*(\S+)", re.MULTILINE)
DAG = re.compile(r"\bDAG\(\s*(?:dag_id\s*=\s*)?[\"']([\w.-]+)[\"']|@dag\(\s*(?:dag_id\s*=\s*)?[\"']([\w.-]+)[\"']")
DAG_SCHEDULE = re.compile(r"\bschedule(?:_interval)?\s*=\s*([\"'][^\"']*[\"']|[\w.()=, ]+)")
TASK_ID = re.compile(r"task_id\s*=\s*[\"']([\w.-]+)[\"']")
CI_CRON = re.compile(r"^\s*-\s*cron:\s*[\"']?([^\"'\n]+?)[\"']?\s*$", re.MULTILINE)
CRONTAB_LINE = re.compile(r"^\s*((?:[\d*/,-]+\s+){4}[\d*/,A-Za-z-]+)\s+(?:\S+\s+)?(.+)$", re.MULTILINE)
JOB_IN_DOC = re.compile(r"`([a-z][a-z0-9_]{2,})`|\bJOB=([a-z][a-z0-9_]{2,})\b")
CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\b")
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def is_secret(name: str) -> bool:
    return name == ".env" or (name.startswith(".env.") and not name.endswith((".example", ".sample")))


def walk(repo: Path, scope: Path) -> list[Path]:
    files = []
    for path in sorted(scope.rglob("*")):
        rel = path.relative_to(repo)
        if any(part in SKIP_DIRS for part in rel.parts) or is_secret(path.name) or not path.is_file():
            continue
        if path.stat().st_size <= MAX_BYTES:
            files.append(path)
    return files


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def is_doc(repo: Path, path: Path) -> bool:
    rel = path.relative_to(repo)
    if path.suffix.lower() not in {".md", ".markdown", ".rst", ".txt", ".adoc"}:
        return False
    return bool(DOC_NAME.match(path.stem) or DOC_NAME.match(path.name) or (rel.parts and rel.parts[0] in DOC_DIRS))


def commands_in_doc(text: str) -> list[dict[str, Any]]:
    """Command lines in fenced or indented code blocks that start with a known tool."""
    found = []
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        candidates = []
        if fenced:
            candidates = [line.strip()]
        else:
            match = INDENTED.match(line)
            candidates = [match.group(1).strip()] if match else [c.strip() for c in INLINE_CODE.findall(line)]
        for candidate in candidates:
            candidate = re.sub(r"^\$\s+", "", candidate)
            first = candidate.split()[0] if candidate.split() else ""
            if first in COMMAND_WORDS or re.match(r"^[A-Z_]+=\S+\s+\w", candidate):
                found.append({"line": number, "command": candidate[:200]})
    return found


def doc_record(repo: Path, path: Path) -> dict[str, Any]:
    text = read(path)
    headings = [m.group(2).strip() for m in (HEADING.match(line) for line in text.splitlines()) if m]
    return {
        "path": path.relative_to(repo).as_posix(),
        "lines": text.count("\n") + 1,
        "headings": headings[:60],
        "commands": commands_in_doc(text),
        "text": text,
    }


def python_facts(rel: str, text: str, items: list[dict[str, Any]]) -> None:
    try:
        tree = ast.parse(text, filename=rel)
    except (SyntaxError, ValueError):
        return
    parsers: dict[str, str] = {}
    if guard := MAIN_GUARD.search(text):
        items.append(
            {
                "kind": "entry",
                "name": f"python {rel}",
                "where": f"{rel}:{text[: guard.start()].count(chr(10)) + 1}",
                "detail": "__main__ guard",
            }
        )
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            name = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")
            if (
                name == "add_parser"
                and call.args
                and isinstance(call.args[0], ast.Constant)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                parsers[node.targets[0].id] = str(call.args[0].value)
        if isinstance(node, ast.Call):
            name = call.func.attr if isinstance((call := node).func, ast.Attribute) else getattr(call.func, "id", "")
            help_text = next(
                (kw.value.value for kw in call.keywords if kw.arg == "help" and isinstance(kw.value, ast.Constant)), ""
            )
            if name == "add_parser" and call.args and isinstance(call.args[0], ast.Constant):
                items.append(
                    {
                        "kind": "command",
                        "name": str(call.args[0].value),
                        "where": f"{rel}:{node.lineno}",
                        "detail": str(help_text),
                    }
                )
            elif name == "add_argument" and call.args and isinstance(call.args[0], ast.Constant):
                owner = (
                    call.func.value.id
                    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
                    else ""
                )
                command = parsers.get(owner, "")
                flag = str(call.args[0].value)
                items.append(
                    {
                        "kind": "flag",
                        "name": flag,
                        "where": f"{rel}:{node.lineno}",
                        "detail": str(help_text),
                        "command": command,
                    }
                )
            elif (
                name in {"option", "argument"}
                and call.args
                and isinstance(call.args[0], ast.Constant)
                and str(call.args[0].value).startswith("-")
            ):
                items.append(
                    {
                        "kind": "flag",
                        "name": str(call.args[0].value),
                        "where": f"{rel}:{node.lineno}",
                        "detail": str(help_text),
                        "command": "",
                    }
                )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                dec_name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
                if dec_name == "command":
                    label = next(
                        (a.value for a in getattr(decorator, "args", []) if isinstance(a, ast.Constant)),
                        node.name.replace("_", "-"),
                    )
                    items.append(
                        {
                            "kind": "command",
                            "name": str(label),
                            "where": f"{rel}:{node.lineno}",
                            "detail": ast.get_docstring(node) or "",
                        }
                    )
        if isinstance(node, ast.ClassDef) and SETTINGS_CLASS.search(node.name):
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    items.append(
                        {
                            "kind": "config",
                            "name": stmt.target.id,
                            "where": f"{rel}:{stmt.lineno}",
                            "detail": f"field of {node.name}",
                        }
                    )
    for match in ENV_READ.finditer(text):
        items.append(
            {
                "kind": "config",
                "name": match.group(1),
                "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                "detail": "read from the environment",
            }
        )
    for match in ROUTE_DECORATOR.finditer(text):
        items.append(
            {
                "kind": "route",
                "name": f"{match.group(1).upper() if match.group(1) != 'route' else 'ANY'} {match.group(2)}",
                "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                "detail": "decorator",
            }
        )
    for match in ROUTE_METHOD.finditer(text):
        items.append(
            {
                "kind": "route",
                "name": f"ANY {match.group(1)}",
                "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                "detail": "registered",
            }
        )
    for match in HANDLER_PATH.finditer(text):
        items.append(
            {
                "kind": "route",
                "name": f"GET {match.group(1)}",
                "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                "detail": "http.server handler compares self.path",
                "guessed": True,
            }
        )


def shallow_facts(rel: str, text: str, items: list[dict[str, Any]]) -> None:
    for match in ENV_READ.finditer(text):
        items.append(
            {
                "kind": "config",
                "name": match.group(1),
                "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                "detail": "read from the environment",
                "guessed": True,
            }
        )
    for match in re.finditer(r"process\.env\.([A-Z][A-Z0-9_]{2,})", text):
        items.append(
            {
                "kind": "config",
                "name": match.group(1),
                "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                "detail": "process.env",
                "guessed": True,
            }
        )
    for match in ROUTE_DECORATOR.finditer(text):
        items.append(
            {
                "kind": "route",
                "name": f"{match.group(1).upper()} {match.group(2)}",
                "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                "detail": "decorator",
                "guessed": True,
            }
        )
    for match in re.finditer(r"""\b(?:app|router)\.(get|post|put|patch|delete|use)\(\s*["']([^"']+)["']""", text):
        items.append(
            {
                "kind": "route",
                "name": f"{match.group(1).upper()} {match.group(2)}",
                "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                "detail": "express style",
                "guessed": True,
            }
        )


def cron_text(expression: str) -> tuple[str, str | None]:
    """A cron expression as a sentence, and its HH:MM when it names one time a day."""
    fields = expression.split()
    if len(fields) != 5:
        return expression, None
    minute, hour, dom, month, dow = fields
    if minute.startswith("*/") and hour == "*":
        return f"every {minute[2:]} minutes", None
    if hour.startswith("*/") and minute.isdigit():
        return f"every {hour[2:]} hours at :{int(minute):02d}", None
    if minute.isdigit() and hour.isdigit():
        clock = f"{int(hour):02d}:{int(minute):02d}"
        when = f"at {clock}"
        if dow != "*":
            names = []
            for part in dow.split(","):
                first, _, last = part.partition("-")
                if first.isdigit() and (last.isdigit() or not last):
                    numbers = range(int(first), int(last or first) + 1)
                    names += [DAYS[(n - 1) % 7] for n in numbers]
                else:
                    names.append(part)
            return f"{when} on {', '.join(names)}", clock
        if dom != "*" or month != "*":
            return f"{when} on day {dom}" + (f" of month {month}" if month != "*" else ""), clock
        return f"daily {when}", clock
    return expression, None


def job_facts(repo: Path, path: Path, text: str, items: list[dict[str, Any]]) -> None:
    rel = path.relative_to(repo).as_posix()
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"} and ".github/workflows" not in rel:
        keys = {key: value.strip().strip("\"'") for key, value in JOB_KEY.findall(text)}
        schedule = keys.get("schedule") or keys.get("cron")
        if (
            keys.get("name")
            and (schedule or "steps:" in text)
            and (rel.startswith("jobs/") or "/jobs/" in rel or schedule)
        ):
            sentence, clock = cron_text(schedule) if schedule else ("no schedule", None)
            items.append(
                {
                    "kind": "job",
                    "name": keys["name"],
                    "where": f"{rel}:1",
                    "detail": keys.get("description", ""),
                    "schedule": schedule,
                    "schedule_text": sentence + (f" ({keys['timezone']})" if keys.get("timezone") else ""),
                    "clock": clock,
                    "sla": keys.get("sla"),
                    "enabled": keys.get("enabled", "true").split("#")[0].strip().lower() != "false",
                    "steps": JOB_STEP.findall(text),
                }
            )
    elif suffix == ".py" and ("DAG(" in text or "@dag(" in text):
        for match in DAG.finditer(text):
            name = match.group(1) or match.group(2)
            after = text[match.end() : match.end() + 600]
            schedule_match = DAG_SCHEDULE.search(after)
            schedule = schedule_match.group(1).strip("\"' ") if schedule_match else None
            sentence, clock = cron_text(schedule) if schedule else ("no schedule", None)
            items.append(
                {
                    "kind": "job",
                    "name": name,
                    "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                    "detail": "Airflow DAG",
                    "schedule": schedule,
                    "schedule_text": sentence,
                    "clock": clock,
                    "enabled": True,
                    "steps": TASK_ID.findall(text),
                }
            )
    elif ".github/workflows" in rel and "schedule:" in text:
        name_match = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
        for match in CI_CRON.finditer(text):
            sentence, clock = cron_text(match.group(1))
            items.append(
                {
                    "kind": "job",
                    "name": (name_match.group(1).strip() if name_match else path.stem),
                    "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                    "detail": "CI schedule",
                    "schedule": match.group(1),
                    "schedule_text": sentence,
                    "clock": clock,
                    "enabled": True,
                    "steps": [],
                }
            )
    elif path.name in {"crontab", "crontab.txt"} or suffix == ".cron" or "/cron.d/" in f"/{rel}":
        for match in CRONTAB_LINE.finditer(text):
            if match.group(0).lstrip().startswith("#"):
                continue
            sentence, clock = cron_text(match.group(1))
            items.append(
                {
                    "kind": "job",
                    "name": match.group(2).strip()[:120],
                    "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                    "detail": "crontab line",
                    "schedule": match.group(1),
                    "schedule_text": sentence,
                    "clock": clock,
                    "enabled": True,
                    "steps": [],
                }
            )


def stale_jobs(docs: list[dict[str, Any]], exposed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A job name a document uses that no job file has, and a time a document gives that the schedule contradicts."""
    jobs = {i["name"]: i for i in exposed if i["kind"] == "job"}
    if not jobs:
        return []
    known = {i["name"] for i in exposed} | {i["name"].split()[-1] for i in exposed if i["kind"] == "target"}
    known |= {step for job in jobs.values() for step in job.get("steps", [])}
    stale = []
    for doc in docs:
        in_jobs_table = False
        for number, line in enumerate(doc["text"].splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("|") and "|" in stripped[1:]:
                cells = [c.strip().lower() for c in stripped.strip("|").split("|")]
                if any(c in {"job", "jobs", "job name"} for c in cells):
                    in_jobs_table = True
                    continue
            elif in_jobs_table and not stripped.startswith("|"):
                in_jobs_table = False
            matches = [m for m in JOB_IN_DOC.finditer(line) if line[m.end() : m.end() + 1] != "<"]
            named = [m.group(1) or m.group(2) for m in matches]
            for name in named:
                if name in known:
                    continue
                if in_jobs_table or f"JOB={name}" in line:
                    stale.append(
                        {
                            "doc": doc["path"],
                            "line": number,
                            "text": stripped[:160],
                            "why": f"no job {name} in the job files",
                        }
                    )
            for name in named:
                job = jobs.get(name)
                if not job or not job.get("clock"):
                    continue
                for hour, minute in CLOCK.findall(line):
                    said = f"{int(hour):02d}:{minute}"
                    if said != job["clock"] and said != job.get("sla"):
                        stale.append(
                            {
                                "doc": doc["path"],
                                "line": number,
                                "text": stripped[:160],
                                "why": (
                                    f"job {name} runs {job['schedule_text']} by its schedule; the document says {said}"
                                ),
                            }
                        )
    return stale


def manifest_facts(repo: Path, path: Path, items: list[dict[str, Any]]) -> None:
    rel = path.relative_to(repo).as_posix()
    name = path.name
    text = read(path)
    if name == "pyproject.toml":
        table = SCRIPTS_TABLE.search(text)
        if table:
            for match in SCRIPT_LINE.finditer(table.group(1)):
                line = text[: table.start() + match.start()].count("\n") + 1
                items.append(
                    {
                        "kind": "entry",
                        "name": match.group(1),
                        "where": f"{rel}:{line}",
                        "detail": f"console script {match.group(2)}:{match.group(3)}",
                    }
                )
    elif name == "package.json":
        try:
            data = json.loads(text)
        except ValueError:
            return
        for key in data.get("scripts") or {}:
            items.append(
                {
                    "kind": "target",
                    "name": f"npm run {key}",
                    "where": rel,
                    "detail": str((data.get("scripts") or {})[key])[:120],
                }
            )
    elif name in {"Makefile", "makefile", "GNUmakefile"}:
        for match in MAKE_TARGET.finditer(text):
            if not match.group(1).startswith("."):
                items.append(
                    {
                        "kind": "target",
                        "name": f"make {match.group(1)}",
                        "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                        "detail": "Makefile target",
                    }
                )
    elif name.startswith("Dockerfile"):
        for match in DOCKER_CMD.finditer(text):
            items.append(
                {
                    "kind": "entry",
                    "name": match.group(1).strip()[:120],
                    "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                    "detail": "container command",
                }
            )
    elif name == "__main__.py":
        package = path.parent.name
        items.append({"kind": "entry", "name": f"python -m {package}", "where": rel, "detail": "runnable package"})
    elif EXAMPLE_FILE.search(rel) and path.suffix.lower() in {
        ".example",
        ".sample",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".env",
        ".cfg",
        "",
    }:
        for match in ENV_FILE_KEY.finditer(text):
            items.append(
                {
                    "kind": "config",
                    "name": match.group(1),
                    "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                    "detail": "key of an example file",
                }
            )
    elif ".github/workflows" in rel or name in {".gitlab-ci.yml", "azure-pipelines.yml"}:
        for match in CI_RUN.finditer(text):
            command = match.group(1).strip().strip("|>").strip()
            if command:
                items.append(
                    {
                        "kind": "target",
                        "name": command[:120],
                        "where": f"{rel}:{text[: match.start()].count(chr(10)) + 1}",
                        "detail": "CI step",
                    }
                )


def mentions(item: dict[str, Any], docs: list[dict[str, Any]]) -> list[str]:
    name = item["name"]
    if item["kind"] == "route":
        needle = re.escape(name.split(" ", 1)[1].rstrip("/").split("<")[0].split("{")[0]) or "/"
        pattern = re.compile(needle)
    elif item["kind"] == "command":
        pattern = re.compile(rf"(?:^|\s|`){re.escape(name)}(?:\s|`|$)", re.MULTILINE)
    elif item["kind"] == "flag":
        pattern = re.compile(re.escape(name) + r"(?![\w-])")
    elif item["kind"] == "entry" and name.startswith("python -m "):
        pattern = re.compile(re.escape(name))
    elif item["kind"] == "entry":
        pattern = re.compile(re.escape(name.split()[0]))
    else:
        pattern = re.compile(rf"\b{re.escape(name)}\b")
    return [doc["path"] for doc in docs if pattern.search(doc["text"])]


def stale_in(docs: list[dict[str, Any]], exposed: list[dict[str, Any]], prog_names: set[str]) -> list[dict[str, Any]]:
    commands = {i["name"] for i in exposed if i["kind"] == "command"}
    flags = {i["name"] for i in exposed if i["kind"] == "flag"}
    routes = {i["name"].split(" ", 1)[1].rstrip("/") for i in exposed if i["kind"] == "route"}
    config = {i["name"] for i in exposed if i["kind"] == "config"}
    targets = {i["name"] for i in exposed if i["kind"] == "target"}
    prefixes = {n.split("_")[0] + "_" for n in config if "_" in n}
    stale = []
    for doc in docs:
        for command in doc["commands"]:
            words = command["command"].split()
            if not words:
                continue
            if words[0] == "make" and len(words) > 1 and targets and f"make {words[1]}" not in targets:
                stale.append(
                    {
                        "doc": doc["path"],
                        "line": command["line"],
                        "text": command["command"],
                        "why": f"no Makefile target {words[1]}",
                    }
                )
            if (
                words[0] in {"npm", "pnpm", "yarn"}
                and len(words) > 2
                and words[1] == "run"
                and targets
                and f"npm run {words[2]}" not in targets
            ):
                stale.append(
                    {
                        "doc": doc["path"],
                        "line": command["line"],
                        "text": command["command"],
                        "why": f"no script {words[2]} in package.json",
                    }
                )
            if commands and any(w in prog_names for w in words[:3]):
                after = [w for w in words[1:] if not w.startswith("-") and w not in prog_names]
                if after and after[0] not in commands:
                    stale.append(
                        {
                            "doc": doc["path"],
                            "line": command["line"],
                            "text": command["command"],
                            "why": f"no command {after[0]} in the code",
                        }
                    )
                for word in words:
                    if word.startswith("--") and flags and word.split("=")[0] not in flags:
                        stale.append(
                            {
                                "doc": doc["path"],
                                "line": command["line"],
                                "text": command["command"],
                                "why": f"no flag {word.split('=')[0]} in the code",
                            }
                        )
        for number, line in enumerate(doc["text"].splitlines(), start=1):
            for match in DOC_ROUTE.finditer(line):
                path = match.group(2).rstrip("/")
                if routes and not any(path.startswith(r.rstrip("/")) or r.startswith(path) for r in routes):
                    stale.append(
                        {
                            "doc": doc["path"],
                            "line": number,
                            "text": line.strip()[:160],
                            "why": f"no route {path} in the code",
                        }
                    )
            for match in UPPER_NAME.finditer(line):
                name = match.group(1)
                if prefixes and any(name.startswith(p) for p in prefixes) and name not in config:
                    stale.append(
                        {
                            "doc": doc["path"],
                            "line": number,
                            "text": line.strip()[:160],
                            "why": f"no setting {name} in the code",
                        }
                    )
    seen = set()
    unique = []
    for item in stale:
        key = (item["doc"], item["line"], item["why"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def facts(repo: Path, scope: Path, extra_docs: list[Path]) -> dict[str, Any]:
    files = walk(repo, scope)
    docs = [doc_record(repo, p) for p in files if is_doc(repo, p)]
    for path in extra_docs:
        if path.is_file() and path.resolve() not in {p.resolve() for p in files}:
            record = doc_record(path.parent, path)
            record["path"] = str(path)
            docs.append(record)
    items: list[dict[str, Any]] = []
    for path in files:
        rel = path.relative_to(repo).as_posix()
        if (
            path.suffix.lower() in {".py", ".yaml", ".yml", ".cron"}
            or path.name.startswith("crontab")
            or "/cron.d/" in f"/{rel}"
        ):
            job_facts(repo, path, read(path), items)
        if path.suffix == ".py":
            python_facts(rel, read(path), items)
            if path.name == "__main__.py":
                manifest_facts(repo, path, items)
        elif path.suffix in {".js", ".ts", ".mjs", ".cjs", ".tsx", ".jsx", ".cs", ".go", ".java"}:
            shallow_facts(rel, read(path), items)
        else:
            manifest_facts(repo, path, items)
    prog_names = {
        i["name"] for i in items if i["kind"] == "entry" and not i["name"].startswith(("python ", "CMD", "["))
    }
    prog_names |= {i["name"] for i in items if i["kind"] == "entry" and i["name"].startswith("python -m ")}
    prog_names |= {n.split()[-1] for n in prog_names if n.startswith("python -m ")}
    seen: set[tuple[str, str]] = set()
    exposed = []
    for item in items:
        key = (item["kind"], item["name"])
        if key in seen:
            continue
        seen.add(key)
        where = item.get("where", "")
        if "/tests/" in f"/{where}" or where.startswith("tests/"):
            continue
        docs_naming = mentions(item, docs)
        item["documented_in"] = docs_naming
        item["status"] = "guessed" if item.get("guessed") else ("documented" if docs_naming else "undocumented")
        item.pop("guessed", None)
        exposed.append(item)
    stale = stale_in(docs, exposed, prog_names) + stale_jobs(docs, exposed)
    counts: dict[str, Any] = {
        "exposed": dict(Counter(i["kind"] for i in exposed)),
        "status": dict(Counter(i["status"] for i in exposed)),
        "docs": len(docs),
        "stale": len(stale),
    }
    for doc in docs:
        doc.pop("text", None)
    return {
        "repo": repo.name,
        "scope": scope.relative_to(repo).as_posix() if scope != repo else ".",
        "docs": docs,
        "exposed": exposed,
        "stale": stale,
        "counts": counts,
        "note": (
            "A name in exposed comes from the code; a document is the only place a claim about behaviour can come "
            "from, and a draft tags what neither gives [guess]."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", nargs="?", default=".", type=Path)
    parser.add_argument("--path", help="a folder inside REPO to read; the top-level documents are read as well")
    parser.add_argument("--docs", nargs="*", type=Path, default=[], help="documents outside the repository to include")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if not repo.is_dir():
        print(f"{args.repo} is not a directory", file=sys.stderr)
        return 2
    scope = (repo / args.path).resolve() if args.path else repo
    if not scope.is_relative_to(repo) or not scope.is_dir():
        print(f"{args.path} is not a folder inside {args.repo}", file=sys.stderr)
        return 2
    result = facts(repo, scope, args.docs)
    if scope != repo:
        top = [doc_record(repo, p) for p in sorted(repo.iterdir()) if p.is_file() and is_doc(repo, p)]
        for doc in top:
            doc.pop("text", None)
        result["docs"] = top + [d for d in result["docs"] if d["path"] not in {t["path"] for t in top}]
    json.dump(result, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
