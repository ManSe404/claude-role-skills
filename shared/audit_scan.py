#!/usr/bin/env python3
"""Find the places in a repository where a bug review should read first, and the promises its docs make.

Usage: python3 audit_scan.py REPO [--path SUBDIR] [--max-per-rule N]

A hit is a place to look, not a finding. Each rule matches a shape that often hides a bug, and many hits are
fine: read the code around every hit before calling it a bug, and expect some of the worst bugs to have no hit.

Promises are the sentences that say never, always, every, must, guarantee, exactly once, at most, at least,
idempotent, deterministic, atomic, timeout, retry, reported or invariant, taken from README*, CLAUDE.md,
AGENTS.md, CONTRIBUTING*, docs/ and adr/ (Markdown or text) and from Python module, class and function
docstrings. Each gets a kind: timeout, retry, determinism, idempotency, data-loss, ordering, error-handling or
general. With --path, the top-level docs of the repository are read as well.

Python is read with ast. Rules:
  swallowed-exception  except Exception, BaseException or a bare except whose body only passes, returns,
                       continues, assigns or logs, and never raises
  suppress-all         contextlib.suppress(Exception) or suppress(BaseException)
  orphan-key           a key read with .get("k") or x["k"] that nothing in the repository writes: no dict literal,
                       x["k"] = ..., setdefault, keyword argument, parameter, class field, regex group, SQL column
                       or key in a .json, .toml, .yaml or .yml file (os.environ, headers, cookies, form and query
                       fields are left out); written keys with a close name are listed
  no-timeout           urlopen, requests.*, httpx.* and the httpx clients, socket.create_connection, without a
                       timeout
  retry-loop           while True around a try/except: its exits, whether it compares anything against a number or
                       an UPPER_CASE name, and bounded=false when an except handler neither leaves the loop nor
                       advances a counter that is compared against a limit
  delete-then-write    in one function, a call named delete/remove/drop/truncate/clear (or SQL DELETE) followed by
                       one named insert/upsert/write/add/put/save/store (or SQL INSERT), with the calls in between
                       and whether one `with` block holds both
  builtin-hash         hash(...), which is salted per process for str and bytes
  assert-in-code       assert outside the tests (python -O removes it)
  type-ignore          # type: ignore comments
  mutable-default      list, dict or set defaults of a def or lambda
  sql-concat           execute/executemany/executescript or sqlalchemy text() with SQL built by an f-string, + or %
                       or .format(): a value in it changes the query
  shell-input          os.system, os.popen, or subprocess with shell=True, with a command that is not a literal
  path-from-input      open() of a path built from a function parameter, in a function that never resolves or
                       checks the path against a root
  secret-literal       a string that looks like a real key (AWS, OpenAI, GitHub, Slack, JWT) or a literal of 8+
                       characters under a name like api_key, secret, token or password; the line is not shown
  unsafe-load          pickle/marshal/shelve/dill/jsonpickle loads, yaml.load without SafeLoader, eval or exec
                       of something that is not a literal
  url-from-input       requests, httpx or urlopen whose URL comes from a function parameter (SSRF when a request
                       can set it)
  call-in-loop         a database, HTTP or storage call inside a loop: one round trip per element (N+1)
  unbounded-read       a SELECT with no WHERE and no LIMIT: reads the whole table
  unclosed-resource    open(), connect(), socket(), Popen() or urlopen() bound to a name outside a with block and
                       never closed in that function
C#, TypeScript/JavaScript, Java and Go get shallow regex rules:
  catch-all            an empty catch block, or a catch-all catch without a throw; in Go an empty if err != nil {}
  sql-concat           query/execute/raw with a template literal holding ${...} or a string joined with +
  shell-input          exec, execSync, spawn with shell, Process.Start or Runtime.exec with a non-literal command
  unsafe-load          eval(), new Function(), BinaryFormatter.Deserialize, ObjectInputStream.readObject
  secret-literal       as in Python, by the value's shape
Every language:
  todo                 TODO, FIXME and HACK comments

Test files (tests/, test_*.py, *_test.py, *.spec.ts and the like) are counted but give no hits. Files named .env
or .env.* are never opened, and folders with those names are not walked. `counts` holds the total per rule;
`hits` keeps at most --max-per-rule of each. Read-only, standard library only, JSON on stdout. The git call has a
timeout.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePosixPath
from typing import Any

SKIP_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".tox"}
SKIP_DIRS |= {".mypy_cache", ".pytest_cache", ".ruff_cache"}
MAX_BYTES = 2_000_000
MAX_PROMISES = 400
PROMISE_CHARS = 240
CODE_CHARS = 200
LANGUAGES = {
    ".py": "python",
    ".cs": "csharp",
    ".java": "java",
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".md": "markdown",
    ".markdown": "markdown",
    ".rst": "text",
    ".txt": "text",
    ".adoc": "text",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sql": "sql",
}
SHALLOW = ("csharp", "java", "typescript", "javascript", "go")
CODE = ("python", *SHALLOW)
CONFIG_SUFFIXES = {".json", ".toml", ".yaml", ".yml"}
DOC_SUFFIXES = {".md", ".markdown", ".rst", ".txt", ".adoc"}
DOC_NAME = re.compile(r"^(?:(?:README|CONTRIBUTING)(?:\.[\w-]+)?|CLAUDE\.md|AGENTS\.md)$", re.IGNORECASE)
DOC_DIRS = {"docs", "adr", "adrs"}
TEST_PATH = re.compile(
    r"(^|/)(tests?|__tests__|spec|testing)/|(^|/)test_[^/]*\.py$|_test\.(py|go)$|(^|/)conftest\.py$"
    r"|\.(test|spec)\.[cm]?[jt]sx?$|Tests?\.(cs|java)$|(^|/)[^/]*\.Tests?/"
)
RULES = (
    "swallowed-exception",
    "suppress-all",
    "orphan-key",
    "no-timeout",
    "retry-loop",
    "delete-then-write",
    "builtin-hash",
    "assert-in-code",
    "type-ignore",
    "mutable-default",
    "sql-concat",
    "shell-input",
    "path-from-input",
    "secret-literal",
    "unsafe-load",
    "url-from-input",
    "call-in-loop",
    "unbounded-read",
    "unclosed-resource",
    "catch-all",
    "todo",
)
NOTE = (
    "A hit is a place to look, not a finding: read the code around each one, keep what you can show breaks "
    "something, and look for the bugs no rule matches by walking the failure paths."
)

PROMISE = re.compile(
    r"\b(never|always|every|must|guarantee[sd]?|exactly (?:once|one)|at most|at least|idempoten\w*"
    r"|deterministic\w*|atomic\w*|time-?outs?|retr(?:y|ies|ied|ying)|reported|invariants?)\b",
    re.IGNORECASE,
)
KINDS = (
    ("timeout", r"\btime-?outs?\b|\bdeadlines?\b"),
    ("retry", r"\bretr(?:y|ies|ied|ying)\b|\bdead[- ]letter|\battempts?\b|\bbackoff\b"),
    ("determinism", r"\bdeterminis\w*|\breproducib\w*|\bstable\b|\bsame (?:input|id|ids|output|result)\b"),
    ("idempotency", r"\bidempoten\w*|\bexactly once\b|\bat most once\b|\bat least once\b|\bduplicat\w*|\boverwrit\w*"),
    ("data-loss", r"\b(?:remov|delet|drop|lose|lost|loss|disappear|purg|truncat|corrupt)\w*"),
    ("ordering", r"\bends? with\b|\bbefore\b|\bafter\b|\bfirst\b|\blast\b|\bin order\b|\border(?:ed|ing)?\b"),
    ("error-handling", r"\berrors?\b|\bexceptions?\b|\bfail\w*|\breported\b|\bhidden\b|\braise[sd]?\b|\bswallow"),
)
KIND_RE = [(kind, re.compile(pattern, re.IGNORECASE)) for kind, pattern in KINDS]
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9`\"'(\[*_])")
BULLET = re.compile(r"([-*+]|\d+[.)])\s+")
RULE_LINE = re.compile(r"[=\-~^*#+_]{3,}")
TABLE_RULE = re.compile(r"[|:\-\s]+")

SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
LOOPS = (ast.For, ast.AsyncFor, ast.While)
TRIES = (ast.Try, ast.TryStar)
BROAD = {"Exception", "BaseException"}
LOG_CALLS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log", "print"}
HTTP_VERBS = {"get", "post", "put", "patch", "delete", "head", "options", "request", "stream"}
OUTSIDE_INPUT = {"environ", "headers", "cookies", "form", "args", "query_params", "GET", "POST", "META"}
TYPE_FORMS = {"Literal", "Annotated"}
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
UPPER = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
WORD = re.compile(r"[A-Za-z_]\w*")
SQL_TEXT = re.compile(
    r"\b(?:SELECT\b[\s\S]*\bFROM|INSERT\s+(?:OR\s+\w+\s+)?INTO|UPDATE\s+\w+\s+SET|CREATE\s+(?:TEMP\w*\s+)?TABLE"
    r"|DELETE\s+FROM)\b"
)
REGEX_GROUP = re.compile(r"\(\?P<(\w+)>")
CONFIG_KEY = re.compile(r"""["']([A-Za-z_][\w-]*)["']\s*:|^\s*-?\s*([A-Za-z_][\w-]*)\s*[:=]""", re.MULTILINE)
TOML_TABLE = re.compile(r"^\s*\[+\s*([\w.\-\" ]+?)\s*\]+", re.MULTILINE)
DELETE_WORDS = {"delete", "remove", "drop", "truncate", "clear"}
WRITE_WORDS = {"insert", "upsert", "write", "add", "put", "save", "store"}
SQL_METHODS = {"execute", "executemany", "executescript"}
SQL_DELETE = {"DELETE", "TRUNCATE", "DROP"}
SQL_WRITE = {"INSERT", "REPLACE", "UPSERT", "MERGE"}
CLOCK_CALLS = {"monotonic", "time", "perf_counter", "now", "utcnow"}
MUTABLE_CALLS = {"list", "dict", "set", "defaultdict", "OrderedDict", "deque", "bytearray"}
TYPE_IGNORE = re.compile(r"#\s*type:\s*ignore\b")
TODO = re.compile(r"\b(TODO|FIXME|HACK)\b")
LINE_COMMENT = re.compile(r"(//|/\*|^\s*\*)(.*)$")
CATCH = re.compile(r"\bcatch\b\s*(?:\(([^)]*)\))?\s*(when\s*\(.*?\)\s*)?\{")
GO_EMPTY_ERROR = re.compile(r"\bif\s+err\s*!=\s*nil\s*\{\s*\}")
COMMENTS = re.compile(r"//[^\n]*|/\*[\s\S]*?\*/")
SECRET_NAME = re.compile(
    r"api_?key|secret|token|passw(?:or)?d|(?:^|_)pwd(?:_|$)|private_?key|client_?secret", re.IGNORECASE
)
SECRET_VALUE = re.compile(
    r"AKIA[0-9A-Z]{16}|sk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|gh[ous]_[A-Za-z0-9]{30,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
PLACEHOLDER = re.compile(
    r"^(?:\$\{?\w+\}?|<[^>]*>|\{\{.*\}\}|%\(\w+\)s|change[-_ ]?me|xxx+|\*+|\.\.\.|your[-_ ].*|example.*|dummy.*|test.*"
    r"|placeholder.*|secret|password|token|none|null|todo|fixme|redacted)$",
    re.IGNORECASE,
)
UNSAFE_LOADS = {
    "pickle.load",
    "pickle.loads",
    "cPickle.load",
    "cPickle.loads",
    "marshal.load",
    "marshal.loads",
    "shelve.open",
    "dill.load",
    "dill.loads",
    "jsonpickle.decode",
}
SAFE_LOADERS = {"SafeLoader", "CSafeLoader", "BaseLoader", "CBaseLoader"}
SHELL_CALLS = {"run", "call", "check_call", "check_output", "Popen", "getoutput", "getstatusoutput"}
PATH_SAFETY = {
    "resolve",
    "realpath",
    "abspath",
    "normpath",
    "is_relative_to",
    "relative_to",
    "commonpath",
    "secure_filename",
}
LOOP_CALLS = {
    "execute",
    "executemany",
    "executescript",
    "fetchone",
    "fetchall",
    "query",
    "find_one",
    "get_object",
    "put_object",
    "upload_file",
    "download_file",
    "urlopen",
    "create_connection",
    "commit",
}
RESOURCE_CALLS = {"open", "connect", "socket", "urlopen", "Popen", "TemporaryFile", "NamedTemporaryFile", "ZipFile"}
SQL_SELECT = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
SHALLOW_SQL_CONCAT = re.compile(
    r"\.(?:query|execute|raw|exec|ExecuteSql\w*|FromSql\w*|createQuery|prepareStatement)\s*\(\s*(?:`[^`]*\$\{|[\"'][^\"'\n]*[\"']\s*\+|\$\")"
)
SHALLOW_SHELL = re.compile(
    r"\b(?:child_process\.)?(?:exec|execSync|spawn|spawnSync)\s*\(\s*(?![\"'`])\w|\bProcess\.Start\s*\(\s*(?![\"'])\w"
    r"|Runtime\.getRuntime\(\)\.exec\s*\(\s*(?![\"'])\w"
)
SHALLOW_UNSAFE = re.compile(
    r"\beval\s*\(|new\s+Function\s*\(|BinaryFormatter\b.*\.Deserialize|ObjectInputStream\b.*\.readObject"
)


# ---------------------------------------------------------------------------- files


def is_secret(name: str) -> bool:
    """A .env file: never listed, never opened."""
    return name == ".env" or name.startswith(".env.")


def is_test(rel: str) -> bool:
    return bool(TEST_PATH.search(rel))


def language(rel: str) -> str:
    return LANGUAGES.get(PurePosixPath(rel).suffix.lower(), "other")


def skipped_dir(name: str) -> bool:
    """A folder never walked: tool caches, virtualenvs, builds, and a folder named like a .env file."""
    return name in SKIP_DIRS or is_secret(name)


def keep(rel: str) -> bool:
    parts = rel.split("/")
    return not is_secret(parts[-1]) and not any(skipped_dir(part) for part in parts[:-1])


def list_files(repo: Path) -> list[str]:
    """Tracked and untracked files that git does not ignore; every file when REPO is not a git repository."""
    found: list[str] = []
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout
        found = [name for name in out.split("\0") if name]
    except (OSError, subprocess.SubprocessError):
        found = []
    if not found:
        for root, dirs, names in os.walk(repo):
            dirs[:] = sorted(d for d in dirs if not skipped_dir(d))
            found.extend((Path(root) / name).relative_to(repo).as_posix() for name in sorted(names))
    return sorted({rel for rel in found if keep(rel) and (repo / rel).is_file()})


def read_text(path: Path) -> str | None:
    """The text of a file, or None for a .env file, a file over MAX_BYTES or one that cannot be read."""
    if is_secret(path.name):
        return None
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def is_doc(rel: str) -> bool:
    path = PurePosixPath(rel)
    suffix = path.suffix.lower()
    if DOC_NAME.match(path.name):
        return suffix in DOC_SUFFIXES or not suffix
    return suffix in DOC_SUFFIXES and any(part.lower() in DOC_DIRS for part in path.parts[:-1])


def is_top_doc(rel: str) -> bool:
    parts = PurePosixPath(rel).parts
    return is_doc(rel) and (len(parts) == 1 or parts[0].lower() in DOC_DIRS)


def in_scope(rel: str, scope: str) -> bool:
    return not scope or rel == scope or rel.startswith(scope + "/")


# ---------------------------------------------------------------------------- promises


def kind_of(sentence: str) -> str:
    for kind, pattern in KIND_RE:
        if pattern.search(sentence):
            return kind
    return "general"


def units(lines: Iterable[tuple[int, str]], markdown: bool) -> list[list[tuple[int, str]]]:
    """Paragraphs, list items and table rows as lists of (line number, text); code blocks and headings are left out."""
    found: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    fence = False

    def flush() -> None:
        if current:
            found.append(list(current))
            current.clear()

    for number, raw in lines:
        text = raw.strip()
        if markdown and text.startswith(("```", "~~~")):
            flush()
            fence = not fence
            continue
        if fence:
            continue
        if not text or RULE_LINE.fullmatch(text):
            flush()
            continue
        if text.startswith(">>>") or (markdown and not current and raw.startswith(("    ", "\t"))):
            continue
        if markdown and text.startswith("#"):
            flush()
            continue
        if text.startswith("|"):
            flush()
            if not TABLE_RULE.fullmatch(text):
                found.append([(number, " | ".join(cell.strip() for cell in text.strip("|").split("|")))])
            continue
        bullet = BULLET.match(text)
        if bullet:
            flush()
            text = text[bullet.end() :]
        current.append((number, text))
    flush()
    return found


def sentences(unit: list[tuple[int, str]]) -> Iterator[tuple[int, str]]:
    """(line number, sentence) for each sentence of a paragraph."""
    text = ""
    starts: list[tuple[int, int]] = []
    for number, part in unit:
        if text:
            text += " "
        starts.append((len(text), number))
        text += part

    def line_at(offset: int) -> int:
        return max((number for start, number in starts if start <= offset), default=unit[0][0])

    begin = 0
    for match in SENTENCE_END.finditer(text):
        yield line_at(begin), text[begin : match.start()]
        begin = match.end()
    yield line_at(begin), text[begin:]


def promises_in(rel: str, lines: Iterable[tuple[int, str]], markdown: bool) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for unit in units(lines, markdown):
        for line, sentence in sentences(unit):
            if PROMISE.search(sentence):
                text = " ".join(sentence.split())
                if len(text) > PROMISE_CHARS:
                    text = text[: PROMISE_CHARS - 3].rstrip() + "..."
                found.append({"file": rel, "line": line, "text": text, "kind": kind_of(sentence)})
    return found


def docstrings(tree: ast.Module) -> Iterator[tuple[int, str]]:
    """(first line, text) of the module, class and function docstrings."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                yield first.lineno, first.value.value


# ---------------------------------------------------------------------------- python helpers


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return ""


def const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def literal_text(node: ast.AST) -> str:
    """The constant text of a string or f-string, the formatted parts left out."""
    if isinstance(node, ast.JoinedStr):
        return "".join(const_str(part) or " " for part in node.values)
    return const_str(node) or ""


def local_nodes(nodes: Iterable[ast.AST]) -> Iterator[ast.AST]:
    """These nodes and everything under them, without entering nested functions, classes or lambdas."""
    stack = list(nodes)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, SCOPES):
            stack.extend(ast.iter_child_nodes(node))


def target_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            names.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            names.add(sub.attr)
    return names


def comments(text: str) -> Iterator[tuple[int, str]]:
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                yield token.start[0], token.string
    except (tokenize.TokenError, SyntaxError):
        return


class Source:
    """One file's lines, for building hits."""

    def __init__(self, rel: str, text: str) -> None:
        self.rel = rel
        self.lines = text.splitlines()

    def hit(self, rule: str, line: int, why: str, **extra: Any) -> dict[str, Any]:
        code = self.lines[line - 1].strip() if 0 < line <= len(self.lines) else ""
        return {"rule": rule, "file": self.rel, "line": line, "code": code[:CODE_CHARS], "why": why, **extra}


# ---------------------------------------------------------------------------- orphan keys


def written_keys(tree: ast.AST) -> set[str]:
    """Every name this module could write a key under."""
    keys: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys.update(key for key in (const_str(k) for k in node.keys) if key)
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            key = const_str(node.slice)
            if key:
                keys.add(key)
        elif isinstance(node, ast.Call):
            keys.update(k.arg for k in node.keywords if k.arg)
            if call_name(node) == "setdefault" and node.args:
                key = const_str(node.args[0])
                if key:
                    keys.add(key)
        elif isinstance(node, ast.arguments):
            every = [*node.posonlyargs, *node.args, *node.kwonlyargs, node.vararg, node.kwarg]
            keys.update(arg.arg for arg in every if arg)
        elif isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    keys.add(stmt.target.id)
                elif isinstance(stmt, ast.Assign):
                    keys.update(t.id for t in stmt.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if SQL_TEXT.search(node.value):
                keys.update(WORD.findall(node.value))
            keys.update(REGEX_GROUP.findall(node.value))
    return keys


def config_keys(text: str, suffix: str) -> set[str]:
    if suffix == ".sql":
        return set(WORD.findall(text))
    keys = {quoted or bare for quoted, bare in CONFIG_KEY.findall(text)}
    if suffix == ".toml":
        for table in TOML_TABLE.findall(text):
            keys.update(part.strip().strip('"') for part in table.split("."))
    return keys


def outside_input(node: ast.AST) -> bool:
    """os.environ, request headers and the like: their keys come from outside the code."""
    name = dotted(node)
    return bool(name) and name.rsplit(".", 1)[-1] in OUTSIDE_INPUT


def key_reads(tree: ast.AST) -> Iterator[tuple[str, int]]:
    for node in ast.walk(tree):
        key: str | None = None
        line = 0
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            if node.args and not outside_input(node.func.value):
                key, line = const_str(node.args[0]), node.lineno
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            receiver = dotted(node.value).rsplit(".", 1)[-1]
            if receiver not in TYPE_FORMS and not outside_input(node.value):
                key, line = const_str(node.slice), node.lineno
        if key and IDENT.match(key):
            yield key, line


# ---------------------------------------------------------------------------- python rules


def broad_catch(handler: ast.ExceptHandler) -> str | None:
    if handler.type is None:
        return "bare except"
    types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    for node in types:
        name = dotted(node).rsplit(".", 1)[-1]
        if name in BROAD:
            return f"except {name}"
    return None


def is_log_call(call: ast.Call) -> bool:
    """log.warning(...), print(...), traceback.print_exc() and the like."""
    name = call_name(call)
    return name in LOG_CALLS or name.startswith("print_")


def only_swallows(body: list[ast.stmt], did: list[str]) -> bool:
    """True when the statements only pass, return, continue, assign or log; what they do goes into did."""

    def note(what: str) -> None:
        if what not in did:
            did.append(what)

    for stmt in body:
        if isinstance(stmt, ast.Pass):
            note("passes")
        elif isinstance(stmt, ast.Return):
            value = ast.unparse(stmt.value) if stmt.value else "None"
            note(f"returns {value[:40]}")
        elif isinstance(stmt, ast.Continue):
            note("continues")
        elif isinstance(stmt, ast.Break):
            note("breaks")
        elif isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            note("assigns")
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) and is_log_call(stmt.value):
            note("logs")
        elif isinstance(stmt, ast.If):
            if not (only_swallows(stmt.body, did) and only_swallows(stmt.orelse, did)):
                return False
        else:
            return False
    return True


def missing_timeout(call: ast.Call) -> str | None:
    """Why this outbound call needs a timeout, or None when it has one or is not an outbound call."""
    keywords = {k.arg for k in call.keywords}
    if None in keywords or "timeout" in keywords:
        return None
    name = dotted(call.func) or call_name(call)
    base, _, last = name.rpartition(".")
    if last == "urlopen":
        if len(call.args) >= 3:
            return None
        return "urlopen without a timeout waits for ever on a server that accepts the connection and never answers"
    if base == "requests" and last in HTTP_VERBS:
        return "requests has no default timeout: this call can hang for ever"
    if base == "httpx" and last in HTTP_VERBS:
        return "httpx falls back to its 5 s default; the call sets no timeout of its own"
    if name in {"httpx.Client", "httpx.AsyncClient"}:
        return "httpx client without a timeout of its own (the library default is 5 s)"
    if last == "create_connection" and base in {"socket", ""}:
        if len(call.args) >= 2:
            return None
        return "socket.create_connection without a timeout blocks for as long as the operating system allows"
    return None


def is_mutable(node: ast.AST) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
        return True
    return isinstance(node, ast.Call) and call_name(node) in MUTABLE_CALLS


def module_binds(tree: ast.Module, name: str) -> bool:
    """Whether the module defines or imports name at its top level."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return True
        if isinstance(node, (ast.Import, ast.ImportFrom)) and any(
            (alias.asname or alias.name.split(".")[0]) == name for alias in node.names
        ):
            return True
        if isinstance(node, ast.Assign) and any(name in target_names(t) for t in node.targets):
            return True
    return False


def exit_counts(body: Iterable[ast.AST]) -> Counter[str]:
    """break (of this loop, not of a nested one), return and raise statements in body."""
    counts: Counter[str] = Counter()

    def visit(node: ast.AST, nested_loop: bool) -> None:
        if isinstance(node, SCOPES):
            return
        if isinstance(node, ast.Return):
            counts["return"] += 1
        elif isinstance(node, ast.Raise):
            counts["raise"] += 1
        elif isinstance(node, ast.Break) and not nested_loop:
            counts["break"] += 1
        elif isinstance(node, ast.Call) and dotted(node.func) in {"sys.exit", "os._exit"}:
            counts["raise"] += 1
        inner = nested_loop or isinstance(node, LOOPS)
        for child in ast.iter_child_nodes(node):
            visit(child, inner)

    for node in body:
        visit(node, False)
    return counts


def is_limit(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        node = node.operand
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (int, float)) and not isinstance(node.value, bool)
    name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""
    return bool(UPPER.match(name))


def is_clock(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and call_name(sub) in CLOCK_CALLS:
            return True
        if isinstance(sub, (ast.Name, ast.Attribute)) and "deadline" in dotted(sub).lower():
            return True
    return False


def assigns_to(nodes: Iterable[ast.AST], names: set[str]) -> bool:
    for node in nodes:
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        if any(target_names(t) & names for t in targets):
            return True
    return False


def own_tries(loop: ast.While) -> list[ast.Try | ast.TryStar]:
    """The try statements of this loop with except handlers, not those of a nested loop or function."""
    found: list[ast.Try | ast.TryStar] = []
    stack: list[ast.AST] = list(loop.body)
    while stack:
        node = stack.pop()
        if isinstance(node, TRIES) and node.handlers:
            found.append(node)
        if not isinstance(node, (*SCOPES, *LOOPS)):
            stack.extend(ast.iter_child_nodes(node))
    return sorted(found, key=lambda t: t.lineno)


def retry_loop(source: Source, loop: ast.While) -> dict[str, Any] | None:
    test = loop.test
    if not (isinstance(test, ast.Constant) and (test.value is True or (type(test.value) is int and test.value == 1))):
        return None
    tries = own_tries(loop)
    if not tries:
        return None
    exits = exit_counts(loop.body)
    counters: set[str] = set()
    limit_check = clock = False
    for node in local_nodes(loop.body):
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            clock = clock or any(is_clock(o) for o in operands)
            if any(is_limit(o) for o in operands):
                limit_check = True
                for operand in operands:
                    if not is_limit(operand):
                        counters |= target_names(operand)
    every_pass = assigns_to(loop.body, counters) or any(
        assigns_to(stmt.body, counters) for stmt in loop.body if isinstance(stmt, TRIES)
    )
    open_handlers = [
        handler
        for t in tries
        for handler in t.handlers
        if not sum(exit_counts(handler.body).values()) and not assigns_to(local_nodes(handler.body), counters)
    ]
    bounded = not open_handlers or clock or every_pass
    exit_text = ", ".join(f"{exits[k]} {k}" for k in ("break", "return", "raise") if exits[k]) or "no exit"
    limit_text = "compares against a number or an UPPER_CASE limit" if limit_check else "compares nothing to a limit"
    if bounded:
        if not open_handlers:
            reason = "every except handler leaves the loop or advances a counter that is checked against a limit"
        elif clock:
            reason = "a clock or a deadline is checked"
        else:
            reason = "a counter that is checked against a limit advances on every pass"
        why = f"while True around try/except ({exit_text}; {limit_text}): bounded, {reason}"
    else:
        where = ", ".join(
            f"line {h.lineno} ({'except ' + ast.unparse(h.type) if h.type else 'bare except'})" for h in open_handlers
        )
        why = (
            f"while True around try/except ({exit_text}; {limit_text}): unbounded, the handler at {where} neither "
            "leaves the loop nor advances a counter that is checked against a limit, so that error retries for ever"
        )
    return source.hit(
        "retry-loop",
        loop.lineno,
        why,
        exits={k: exits[k] for k in ("break", "return", "raise")},
        limit_check=limit_check,
        bounded=bounded,
        open_handlers=[h.lineno for h in open_handlers],
    )


def call_kind(call: ast.Call) -> tuple[str, str] | None:
    """('delete' or 'write', a label) for a call that deletes or writes, else None."""
    name = call_name(call)
    if name in SQL_METHODS:
        sql = literal_text(call.args[0]).strip() if call.args else ""
        verb = sql.split(None, 1)[0].upper() if sql else ""
        if verb in SQL_DELETE:
            return "delete", f"{name}({verb})"
        if verb in SQL_WRITE:
            return "write", f"{name}({verb})"
        return None
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower().split("_")
    parts = {word.removesuffix("s") for word in words if word}
    deletes, writes = bool(parts & DELETE_WORDS), bool(parts & WRITE_WORDS)
    if deletes and not writes:
        return "delete", f"{name}()"
    if writes and not deletes:
        return "write", f"{name}()"
    return None


def local_calls(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[ast.Call, frozenset[int]]]:
    """The calls of one function, each with the `with` blocks around it, in source order."""
    found: list[tuple[ast.Call, frozenset[int]]] = []

    def visit(node: ast.AST, withs: frozenset[int]) -> None:
        if isinstance(node, SCOPES):
            return
        if isinstance(node, ast.Call):
            found.append((node, withs))
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                visit(item, withs)
            for stmt in node.body:
                visit(stmt, withs | {node.lineno})
            return
        for child in ast.iter_child_nodes(node):
            visit(child, withs)

    for stmt in func.body:
        visit(stmt, frozenset())
    return sorted(found, key=lambda pair: (pair[0].lineno, pair[0].col_offset))


def delete_then_write(source: Source, func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict[str, Any]]:
    calls = local_calls(func)
    kinds = [call_kind(call) for call, _ in calls]
    found: list[dict[str, Any]] = []
    for i, (call, withs) in enumerate(calls):
        kind = kinds[i]
        if not kind or kind[0] != "delete":
            continue
        for j in range(i + 1, len(calls)):
            other = kinds[j]
            if not other or other[0] != "write":
                continue
            write, write_withs = calls[j]
            between: list[str] = []
            for middle, _ in calls[i + 1 : j]:
                name = call_name(middle)
                if name and name not in between:
                    between.append(name)
            shared = sorted(withs & write_withs)
            same_with = bool(shared)
            pair = f"{kind[1]} at line {call.lineno} then {other[1]} at line {write.lineno}"
            if same_with:
                why = f"{pair}, both in the `with` block at line {shared[-1]}: atomic if that block is one transaction"
            else:
                middle_text = f"; called in between: {', '.join(between[:6])}" if between else ""
                why = (
                    f"{pair}, not inside one `with` block{middle_text}: if anything between them fails, the delete "
                    "stays and the write never happens"
                )
            found.append(
                source.hit(
                    "delete-then-write",
                    call.lineno,
                    why,
                    write_line=write.lineno,
                    same_with=same_with,
                    between=between[:6],
                )
            )
            break
    return found


def python_hits(source: Source, text: str, tree: ast.Module, written: set[str]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    shadowed_hash = module_binds(tree, "hash")
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            catch = broad_catch(node)
            did: list[str] = []
            if catch and only_swallows(node.body, did):
                what = ", ".join(did) or "does nothing"
                why = f"{catch} that only {what}: the error never reaches the caller"
                hits.append(source.hit("swallowed-exception", node.lineno, why))
        elif isinstance(node, ast.Call):
            name = dotted(node.func) or call_name(node)
            if name.rsplit(".", 1)[-1] == "suppress":
                broad = [dotted(a) for a in node.args if dotted(a).rsplit(".", 1)[-1] in BROAD]
                if broad:
                    why = f"suppress({broad[0]}) hides every error raised in its block"
                    hits.append(source.hit("suppress-all", node.lineno, why))
            reason = missing_timeout(node)
            if reason:
                hits.append(source.hit("no-timeout", node.lineno, reason))
            for extra in (sql_concat(source, node), shell_input(source, node), unsafe_load(source, node)):
                if extra:
                    hits.append(extra)
            hits.extend(secret_hits(source, node))
            if isinstance(node.func, ast.Name) and node.func.id == "hash" and not shadowed_hash:
                why = (
                    "built-in hash() of str and bytes is salted per process (PYTHONHASHSEED): the value changes "
                    "between runs, so it must not be stored, sent or used as an id"
                )
                hits.append(source.hit("builtin-hash", node.lineno, why))
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.Dict)):
            hits.extend(secret_hits(source, node))
        elif isinstance(node, ast.Assert):
            why = "assert is removed under python -O; a check that guards data or input should raise"
            hits.append(source.hit("assert-in-code", node.lineno, why))
        elif isinstance(node, ast.While):
            loop = retry_loop(source, node)
            if loop:
                hits.append(loop)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            defaults = [*node.args.defaults, *(d for d in node.args.kw_defaults if d is not None)]
            for default in defaults:
                if is_mutable(default):
                    why = "a mutable default is made once and shared by every call that leaves the argument out"
                    hits.append(source.hit("mutable-default", default.lineno, why))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            hits.extend(delete_then_write(source, node))
            hits.extend(function_hits(source, node))
    for key, line in key_reads(tree):
        if key not in written:
            hits.append(source.hit("orphan-key", line, "", key=key))
    for line, comment in comments(text):
        if TYPE_IGNORE.search(comment):
            hits.append(source.hit("type-ignore", line, "silences the type checker on this line; check what it hides"))
        marker = TODO.search(comment)
        if marker:
            hits.append(source.hit("todo", line, f"{marker.group(1)} comment: work the authors knew was left"))
    return hits


# ---------------------------------------------------------------------------- input, secrets, loops, resources


def built_text(node: ast.AST) -> str | None:
    """How a string is built from values, or None when it is a literal or something else."""
    if isinstance(node, ast.JoinedStr):
        return "an f-string"
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        sides = (node.left, node.right)
        if any(const_str(side) is not None or isinstance(side, ast.JoinedStr) for side in sides):
            return "+ or %"
    if isinstance(node, ast.Call) and call_name(node) == "format" and isinstance(node.func, ast.Attribute):
        receiver = node.func.value
        if const_str(receiver) is not None or isinstance(receiver, ast.JoinedStr):
            return ".format()"
    return None


def sql_concat(source: Source, call: ast.Call) -> dict[str, Any] | None:
    name = call_name(call)
    full = dotted(call.func) or name
    if name not in SQL_METHODS and full.rsplit(".", 1)[-1] != "text":
        return None
    if not call.args:
        return None
    how = built_text(call.args[0])
    if how is None:
        return None
    if name not in SQL_METHODS and not SQL_TEXT.search(literal_text(call.args[0])):
        return None
    why = f"SQL built with {how}: a value in it becomes part of the query; pass values as parameters"
    return source.hit("sql-concat", call.lineno, why)


def shell_input(source: Source, call: ast.Call) -> dict[str, Any] | None:
    full = dotted(call.func) or call_name(call)
    last = full.rsplit(".", 1)[-1]
    if not call.args or isinstance(call.args[0], ast.Constant):
        return None
    if full in {"os.system", "os.popen"}:
        return source.hit(
            "shell-input", call.lineno, f"{full} with a command that is not a literal: a value in it is shell syntax"
        )
    shell = any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is True for k in call.keywords)
    if last in SHELL_CALLS and shell:
        why = f"{last}(..., shell=True) with a command that is not a literal: a value in it is shell syntax"
        return source.hit("shell-input", call.lineno, why)
    return None


def unsafe_load(source: Source, call: ast.Call) -> dict[str, Any] | None:
    full = dotted(call.func) or call_name(call)
    if full in UNSAFE_LOADS:
        return source.hit(
            "unsafe-load", call.lineno, f"{full} runs code from the data it reads; never on data from outside"
        )
    if full in {"yaml.load", "yaml.load_all"}:
        loader = next(
            (k.value for k in call.keywords if k.arg == "Loader"), call.args[1] if len(call.args) > 1 else None
        )
        loader_name = dotted(loader).rsplit(".", 1)[-1] if loader is not None else ""
        if loader_name not in SAFE_LOADERS:
            why = (
                f"{full} with {loader_name or 'no'} Loader: Loader and FullLoader build Python objects from tags; "
                "use safe_load or SafeLoader"
            )
            return source.hit("unsafe-load", call.lineno, why)
    if full in {"eval", "exec"} and call.args and not isinstance(call.args[0], ast.Constant):
        return source.hit(
            "unsafe-load", call.lineno, f"{full}() of something that is not a literal runs whatever reaches it"
        )
    return None


def looks_secret(name: str, value: ast.AST) -> str | None:
    text = const_str(value)
    if text is None:
        return None
    if SECRET_VALUE.search(text):
        return "a literal shaped like a real key"
    if SECRET_NAME.search(name) and len(text) >= 8 and " " not in text and not PLACEHOLDER.match(text):
        return f"a literal of {len(text)} characters under the name {name}"
    return None


def secret_hits(source: Source, node: ast.AST) -> list[dict[str, Any]]:
    pairs: list[tuple[str, ast.AST]] = []
    if isinstance(node, ast.Assign):
        pairs = [(dotted(target).rsplit(".", 1)[-1], node.value) for target in node.targets]
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        pairs = [(dotted(node.target).rsplit(".", 1)[-1], node.value)]
    elif isinstance(node, ast.Call):
        pairs = [(keyword.arg, keyword.value) for keyword in node.keywords if keyword.arg]
    elif isinstance(node, ast.Dict):
        pairs = [(name, value) for key, value in zip(node.keys, node.values, strict=True) if (name := const_str(key))]
    hits = []
    for name, value in pairs:
        reason = looks_secret(name or "", value)
        if reason:
            hit = source.hit(
                "secret-literal",
                getattr(value, "lineno", 0),
                f"{reason}: a secret in code is in every clone and log of the repository; read it from settings",
                name=name,
            )
            hit["code"] = "(line not shown)"
            hits.append(hit)
    return hits


def names_in(node: ast.AST) -> set[str]:
    return {sub.id for sub in ast.walk(node) if isinstance(sub, ast.Name)}


def function_hits(source: Source, func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict[str, Any]]:
    """Rules that need the function around a call: its parameters, its loops, its with blocks."""
    hits: list[dict[str, Any]] = []
    params = {a.arg for a in [*func.args.posonlyargs, *func.args.args, *func.args.kwonlyargs]} - {"self", "cls"}
    local = list(local_nodes(func.body))
    calls = [node for node in local if isinstance(node, ast.Call)]
    safety = any(call_name(call) in PATH_SAFETY for call in calls)
    for call in calls:
        name = call_name(call)
        full = dotted(call.func) or name
        base, _, last = full.rpartition(".")
        if (base in {"requests", "httpx"} and last in HTTP_VERBS) or last == "urlopen":
            url = call.args[0] if call.args else next((k.value for k in call.keywords if k.arg == "url"), None)
            used = sorted(names_in(url) & params) if url is not None else []
            if used:
                why = (
                    f"the URL comes from parameter {used[0]}: if a request can set it, this server can be made to "
                    "call any host (SSRF)"
                )
                hits.append(source.hit("url-from-input", call.lineno, why, parameter=used[0]))
        if name == "open" and call.args and not safety:
            used = sorted(names_in(call.args[0]) & params)
            if used:
                why = (
                    f"opens a path built from parameter {used[0]} and the function never resolves it against a root: "
                    "a '../' in that value reaches any file the process can read"
                )
                hits.append(source.hit("path-from-input", call.lineno, why, parameter=used[0]))
        if name in SQL_METHODS and call.args:
            sql = literal_text(call.args[0])
            upper = sql.upper()
            if SQL_SELECT.match(sql) and "WHERE" not in upper and "LIMIT" not in upper:
                why = "SELECT with no WHERE and no LIMIT reads the whole table: fine for a batch job, not for a request"
                hits.append(source.hit("unbounded-read", call.lineno, why))
    for loop in local:
        if not isinstance(loop, (*LOOPS, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            continue
        body = loop.body if isinstance(loop, LOOPS) else [loop.elt if hasattr(loop, "elt") else loop.value]
        for node in local_nodes(body):
            if not isinstance(node, ast.Call):
                continue
            full = dotted(node.func) or call_name(node)
            base, _, last = full.rpartition(".")
            if last in LOOP_CALLS or (base in {"requests", "httpx"} and last in HTTP_VERBS):
                why = (
                    f"{full}() once per pass of the loop at line {loop.lineno}: one round trip per element (N+1); "
                    "fetch or write in one batch when the count can grow"
                )
                hits.append(source.hit("call-in-loop", node.lineno, why, loop_line=loop.lineno))
    closed = {
        dotted(call.func.value) for call in calls if isinstance(call.func, ast.Attribute) and call.func.attr == "close"
    }
    returned = set()
    for node in local:
        if isinstance(node, ast.Return) and node.value is not None:
            returned |= names_in(node.value)
    inside_with: set[int] = set()
    for node in local:
        if isinstance(node, (ast.With, ast.AsyncWith)):
            inside_with |= {sub.lineno for sub in ast.walk(node) if hasattr(sub, "lineno")}
    for node in local:
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and len(node.targets) == 1):
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        last = (dotted(node.value.func) or call_name(node.value)).rsplit(".", 1)[-1]
        if last not in RESOURCE_CALLS or node.lineno in inside_with:
            continue
        if target.id in closed or target.id in returned:
            continue
        why = (
            f"{target.id} = {last}() is never closed in this function and is not in a with block: the handle leaks "
            "on every call and on every error path"
        )
        hits.append(source.hit("unclosed-resource", node.lineno, why, name=target.id))
    return hits


# ---------------------------------------------------------------------------- shallow rules


def block_body(text: str, brace: int) -> str:
    """The text between the brace at index brace and its match (strings are not understood)."""
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[brace + 1 : index]
    return text[brace + 1 :]


def catches_all(lang: str, param: str | None, guard: str | None) -> bool:
    if guard:
        return False
    if lang == "csharp":
        return param is None or bool(re.match(r"\s*(System\.)?Exception\b", param))
    if lang == "java":
        return bool(param and re.search(r"(?<![\w.])(java\.lang\.)?(Exception|Throwable|RuntimeException)\b", param))
    return lang in {"typescript", "javascript"}


def shallow_hits(source: Source, text: str, lang: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    if lang == "go":
        for match in GO_EMPTY_ERROR.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            hits.append(source.hit("catch-all", line, "empty `if err != nil {}`: the error is dropped"))
    else:
        for match in CATCH.finditer(text):
            body = COMMENTS.sub("", block_body(text, match.end() - 1)).strip()
            line = text.count("\n", 0, match.start()) + 1
            if not body:
                hits.append(source.hit("catch-all", line, "empty catch block: the error disappears"))
            elif catches_all(lang, match.group(1), match.group(2)) and not re.search(r"\bthrow\b", body):
                why = "catch-all without a throw: check that the caller learns about the error"
                hits.append(source.hit("catch-all", line, why))
    for number, line_text in enumerate(source.lines, start=1):
        comment = LINE_COMMENT.search(line_text)
        marker = TODO.search(comment.group(2)) if comment else None
        if marker:
            hits.append(source.hit("todo", number, f"{marker.group(1)} comment: work the authors knew was left"))
        if SHALLOW_SQL_CONCAT.search(line_text):
            hits.append(
                source.hit(
                    "sql-concat", number, "SQL built from a template or joined strings: pass values as parameters"
                )
            )
        if SHALLOW_SHELL.search(line_text):
            hits.append(
                source.hit(
                    "shell-input", number, "a shell command that is not a literal: a value in it is shell syntax"
                )
            )
        if SHALLOW_UNSAFE.search(line_text):
            hits.append(source.hit("unsafe-load", number, "runs code or builds objects from the data it reads"))
        if SECRET_VALUE.search(line_text):
            hit = source.hit("secret-literal", number, "a literal shaped like a real key: read it from settings")
            hit["code"] = "(line not shown)"
            hits.append(hit)
    return hits


# ---------------------------------------------------------------------------- the scan


def explain_orphans(hits: list[dict[str, Any]], written: set[str]) -> None:
    pool = sorted(written)
    for hit in hits:
        key = hit["key"]
        similar = difflib.get_close_matches(key, pool, n=3, cutoff=0.75)
        hit["similar"] = similar
        close = f"; written keys with a close name: {', '.join(similar)}" if similar else ""
        hit["why"] = (
            f'key "{key}" is read here but nothing in the repository writes it (no dict literal, assignment, '
            f"keyword, parameter, class field, SQL column or config key){close}"
        )


def scan(repo: Path, path: str | None = None, max_per_rule: int = 50) -> dict[str, Any]:
    """The scan of repo, or of the folder or file path inside it, as a JSON-ready dict."""
    repo = repo.resolve()
    scope = "" if not path else (repo / path).resolve().relative_to(repo).as_posix()
    scope = "" if scope == "." else scope
    files = list_files(repo)
    scoped = [rel for rel in files if in_scope(rel, scope)]
    code = [rel for rel in scoped if language(rel) in CODE]
    tests = [rel for rel in code if is_test(rel)]

    texts: dict[str, str] = {}
    trees: dict[str, ast.Module] = {}
    unparsed: list[str] = []
    written: set[str] = set()
    for rel in files:
        suffix = PurePosixPath(rel).suffix.lower()
        if suffix != ".py" and suffix not in CONFIG_SUFFIXES and suffix != ".sql":
            continue
        text = read_text(repo / rel)
        if text is None:
            if in_scope(rel, scope) and suffix == ".py":
                unparsed.append(f"{rel}: not read (over {MAX_BYTES} bytes or unreadable)")
            continue
        if suffix != ".py":
            written |= config_keys(text, suffix)
            continue
        try:
            tree = ast.parse(text, filename=rel)
        except (SyntaxError, ValueError) as exc:
            if in_scope(rel, scope):
                unparsed.append(f"{rel}: {type(exc).__name__} {getattr(exc, 'lineno', '') or ''}".rstrip())
            continue
        texts[rel], trees[rel] = text, tree
        written |= written_keys(tree)

    hits: list[dict[str, Any]] = []
    for rel in code:
        if rel in tests:
            continue
        lang = language(rel)
        if lang == "python":
            if rel in trees:
                hits.extend(python_hits(Source(rel, texts[rel]), texts[rel], trees[rel], written))
            continue
        text = read_text(repo / rel)
        if text is not None:
            hits.extend(shallow_hits(Source(rel, text), text, lang))
    hits.sort(key=lambda h: (RULES.index(h["rule"]), h["file"], h["line"]))
    counts: dict[str, int] = {rule: 0 for rule in RULES}
    kept: list[dict[str, Any]] = []
    for hit in hits:
        counts[hit["rule"]] += 1
        if counts[hit["rule"]] <= max_per_rule:
            kept.append(hit)
    explain_orphans([h for h in kept if h["rule"] == "orphan-key"], written)

    promises: list[dict[str, Any]] = []
    for rel in files:
        if is_doc(rel) and (in_scope(rel, scope) or is_top_doc(rel)):
            text = read_text(repo / rel)
            if text is not None:
                markdown = PurePosixPath(rel).suffix.lower() in {".md", ".markdown", ""}
                promises.extend(promises_in(rel, enumerate(text.splitlines(), start=1), markdown))
    for rel in code:
        if rel in trees and rel not in tests:
            for start, doc in docstrings(trees[rel]):
                lines = [(start + offset, line) for offset, line in enumerate(doc.split("\n"))]
                promises.extend(promises_in(rel, lines, markdown=False))

    counts["promises"] = len(promises)
    counts["test_files_skipped"] = len(tests)
    return {
        "repo": repo.name,
        "scope": scope or ".",
        "files": dict(sorted(Counter(language(rel) for rel in scoped).items())),
        "languages_deep": ["python"],
        "languages_shallow": sorted({language(rel) for rel in code} & set(SHALLOW)),
        "promises": promises[:MAX_PROMISES],
        "hits": kept,
        "counts": counts,
        "unparsed": unparsed,
        "note": NOTE,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List the promises of a repository and the places a bug review reads.")
    parser.add_argument("repo", nargs="?", default=".", type=Path)
    parser.add_argument("--path", help="a folder or file inside REPO; the top-level docs are read as well")
    parser.add_argument("--max-per-rule", type=int, default=50, help="hits kept per rule (counts keep the total)")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if not repo.is_dir():
        print(f"{args.repo} is not a directory", file=sys.stderr)
        return 2
    if args.path:
        target = (repo / args.path).resolve()
        if not target.is_relative_to(repo) or not target.exists():
            print(f"{args.path} is not inside {args.repo}", file=sys.stderr)
            return 2
    json.dump(scan(repo, args.path, max(args.max_per_rule, 0)), sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
