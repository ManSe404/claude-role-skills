"""The code-audit scanner, on the acme-index fixture and on small cases of its own.

On the fixture, every planted bug but P6 is hit by its rule at its line. P6 (the answer stream that can stop
without its final event) has no rule: the generator catches URLError but not the JSONDecodeError of a malformed
line, and telling which exceptions can escape a loop needs reading, not a pattern. The scan lists the promise P6
breaks, and the model finds the bug by holding the generator's except clauses against it.
"""

from __future__ import annotations

import builtins
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import build_fixture
import pytest
from conftest import SKILLS, load, make_repo, run_json
from test_fixture_acme_index import DECOYS_AT, PARSE, PLANTED_AT, PROMISES, PROMISES_AT, WORKER, where

SCAN = SKILLS / "code-audit" / "scripts" / "audit_scan.py"
audit = load(SCAN)


@pytest.fixture(scope="module")
def index_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-index fixture, built once for this module. Tests must not change it."""
    target = tmp_path_factory.mktemp("fixture") / "acme-index"
    build_fixture.build("acme-index", target)
    return target


@pytest.fixture(scope="module")
def scan(index_repo: Path) -> dict[str, Any]:
    result: dict[str, Any] = run_json(SCAN, str(index_repo))
    return result


def at(hit: dict[str, Any]) -> str:
    return f"{hit['file']}:{hit['line']}"


def of_rule(result: dict[str, Any], rule: str) -> list[dict[str, Any]]:
    return [h for h in result["hits"] if h["rule"] == rule]


def one(result: dict[str, Any], rule: str, place: str) -> dict[str, Any]:
    found = [h for h in of_rule(result, rule) if at(h) == place]
    assert len(found) == 1, f"{rule} at {place}: {[at(h) for h in of_rule(result, rule)]}"
    return found[0]


# ---------------------------------------------------------------------------- the fixture


def test_p1_delete_then_write_spans_the_embedder_call(scan: dict[str, Any]) -> None:
    hit = one(scan, "delete-then-write", PLANTED_AT["P1"])
    assert hit["same_with"] is False
    assert hit["between"] == ["embed"]
    assert hit["write_line"] > hit["line"]


def test_p2_the_orphan_key_is_the_private_digest(scan: dict[str, Any]) -> None:
    orphans = of_rule(scan, "orphan-key")
    assert [(at(h), h["key"]) for h in orphans] == [(PLANTED_AT["P2"], "_digest")]
    assert orphans[0]["similar"] == ["digest"]
    assert not [h for h in orphans if h["key"] == "digest"]


def test_p3_builtin_hash(scan: dict[str, Any]) -> None:
    hit = one(scan, "builtin-hash", PLANTED_AT["P3"])
    assert "PYTHONHASHSEED" in hit["why"]


def test_p4_swallowed_parse_error(scan: dict[str, Any]) -> None:
    hit = one(scan, "swallowed-exception", PLANTED_AT["P4"])
    assert "returns []" in hit["why"]


def test_p5_no_timeout_only_at_the_planted_call(scan: dict[str, Any]) -> None:
    assert [at(h) for h in of_rule(scan, "no-timeout")] == [PLANTED_AT["P5"]]


def test_p6_has_no_rule_and_its_promise_is_listed(scan: dict[str, Any]) -> None:
    assert not [h for h in scan["hits"] if at(h) == PLANTED_AT["P6"]]
    found = [p for p in scan["promises"] if f"{p['file']}:{p['line']}" == PROMISES_AT["P6"]]
    assert [p["kind"] for p in found] == ["ordering"]


def test_p7_retry_loop_is_unbounded_at_the_generic_handler(scan: dict[str, Any]) -> None:
    hit = one(scan, "retry-loop", PLANTED_AT["P7"])
    assert hit["bounded"] is False and hit["limit_check"] is True
    assert hit["exits"] == {"break": 0, "return": 2, "raise": 0}
    assert [f"{WORKER}:{line}" for line in hit["open_handlers"]] == [where(WORKER, r"^\s+except Exception as exc:$")]
    assert "unbounded" in hit["why"]


def test_decoys_are_not_flagged_as_bugs(scan: dict[str, Any]) -> None:
    assert not [h for h in scan["hits"] if at(h) == DECOYS_AT["D1"]]
    assert not [h for h in scan["hits"] if at(h) == DECOYS_AT["D2"]]
    assert one(scan, "retry-loop", DECOYS_AT["D3"])["bounded"] is True
    assert one(scan, "delete-then-write", DECOYS_AT["D4"])["same_with"] is True


def test_these_are_all_the_hits_on_the_fixture(scan: dict[str, Any]) -> None:
    expected = {
        ("delete-then-write", PLANTED_AT["P1"]),
        ("orphan-key", PLANTED_AT["P2"]),
        ("builtin-hash", PLANTED_AT["P3"]),
        ("swallowed-exception", PLANTED_AT["P4"]),
        ("no-timeout", PLANTED_AT["P5"]),
        ("retry-loop", PLANTED_AT["P7"]),
        ("retry-loop", DECOYS_AT["D3"]),
        ("delete-then-write", DECOYS_AT["D4"]),
        ("type-ignore", where(PARSE, r"# type: ignore")),
        ("todo", where(PARSE, r"# TODO")),
    }
    assert {(h["rule"], at(h)) for h in scan["hits"]} == expected
    assert len(scan["hits"]) == len(expected)


@pytest.mark.parametrize(("pid", "rel", "pattern"), PROMISES, ids=[p[0] for p in PROMISES])
def test_every_broken_promise_is_listed(scan: dict[str, Any], pid: str, rel: str, pattern: str) -> None:
    found = [p for p in scan["promises"] if p["file"] == rel and re.search(pattern, p["text"])]
    assert [f"{p['file']}:{p['line']}" for p in found] == [PROMISES_AT[pid]]


def test_promise_kinds(scan: dict[str, Any]) -> None:
    kinds = {f"{p['file']}:{p['line']}": p["kind"] for p in scan["promises"] if p["file"].endswith(".md")}
    expected = {
        "P1": "data-loss",
        "P2": "general",
        "P3": "determinism",
        "P4": "error-handling",
        "P5": "timeout",
        "P6": "ordering",
        "P7": "retry",
    }
    assert {pid: kinds[PROMISES_AT[pid]] for pid in expected} == expected


def test_the_summary_of_the_fixture(scan: dict[str, Any], index_repo: Path) -> None:
    assert scan["repo"] == index_repo.name and scan["scope"] == "."
    assert scan["files"] == {"markdown": 5, "other": 1, "python": 10, "toml": 1}
    assert scan["languages_deep"] == ["python"] and scan["languages_shallow"] == []
    assert scan["counts"]["test_files_skipped"] == 2
    assert sum(scan["counts"][rule] for rule in audit.RULES) == len(scan["hits"])
    assert scan["counts"]["promises"] == len(scan["promises"])
    assert not [h for h in scan["hits"] if h["file"].startswith("tests/")]
    assert scan["unparsed"] == []
    assert "place to look, not a finding" in scan["note"]


def test_the_docstring_says_a_hit_is_not_a_finding() -> None:
    assert audit.__doc__ and "A hit is a place to look, not a finding." in audit.__doc__


# ---------------------------------------------------------------------------- small cases


def write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def scan_of(tmp_path: Path, files: dict[str, str], path: str | None = None, max_per_rule: int = 50) -> dict[str, Any]:
    result: dict[str, Any] = audit.scan(write(tmp_path / "repo", files), path, max_per_rule)
    return result


def marked(text: str, mark: str = "# hit") -> list[int]:
    return [n for n, line in enumerate(text.splitlines(), start=1) if line.rstrip().endswith(mark)]


def lines(result: dict[str, Any], rule: str, rel: str = "src/app.py") -> list[int]:
    return sorted(h["line"] for h in result["hits"] if h["rule"] == rule and h["file"] == rel)


SWALLOWED = """import logging

log = logging.getLogger(__name__)


def a():
    try:
        work()
    except Exception:  # hit
        pass


def b():
    try:
        work()
    except:  # hit
        return None


def c():
    try:
        work()
    except (ValueError, BaseException) as exc:  # hit
        log.warning("failed: %s", exc)
        result = None


def d():
    try:
        work()
    except Exception as exc:
        raise RuntimeError("wrapped") from exc


def e():
    try:
        work()
    except ValueError:
        pass


def f():
    try:
        work()
    except Exception:
        cleanup()


def g():
    try:
        work()
    except Exception as exc:
        if retryable(exc):
            return None
        raise
"""


def test_swallowed_exception(tmp_path: Path) -> None:
    result = scan_of(tmp_path, {"src/app.py": SWALLOWED})
    assert lines(result, "swallowed-exception") == marked(SWALLOWED)
    why = {h["line"]: h["why"] for h in result["hits"]}
    assert why[marked(SWALLOWED)[0]] == "except Exception that only passes: the error never reaches the caller"
    assert "bare except that only returns None" in why[marked(SWALLOWED)[1]]
    assert "except BaseException that only logs, assigns" in why[marked(SWALLOWED)[2]]


SUPPRESS = """import contextlib
from contextlib import suppress


def a():
    with contextlib.suppress(Exception):  # hit
        work()
    with suppress(BaseException):  # hit
        work()
    with suppress(KeyError):
        work()
"""


def test_suppress_all(tmp_path: Path) -> None:
    assert lines(scan_of(tmp_path, {"src/app.py": SUPPRESS}), "suppress-all") == marked(SUPPRESS)


ORPHANS = """import os
import re
from dataclasses import dataclass

PATTERN = re.compile(r"(?P<year>[0-9]{4})")
SQL = "SELECT chunk_text FROM chunks WHERE id = ?"


@dataclass
class Settings:
    region: str


def build(name, **options):
    run = {"digest": "abc", "status": "new"}
    run["owner"] = "milica"
    run.setdefault("attempts", 0)
    payload = dict(tenant="t")
    return run, payload


def read(run, row, conf, match, request):
    first = run.get("_digest")  # hit
    values = [run["digest"], run["owner"], run.get("attempts"), run["tenant"], conf["region"], conf.get("name")]
    values += [conf["options"], row["chunk_text"], match["year"], conf.get("timeout_seconds"), conf["retries"]]
    values += [conf["queue_name"], conf["from_test"], conf.get("not-an-identifier")]
    values += [os.environ.get("ACME_TOKEN"), os.environ["ACME_HOME"], request.headers.get("Authorization")]
    last = conf["never_written"]  # hit
    return first, values, last
"""


def test_orphan_key(tmp_path: Path) -> None:
    files = {
        "src/app.py": ORPHANS,
        "config/settings.json": '{"timeout_seconds": 5}\n',
        "config/app.toml": "retries = 3\n",
        "deploy/app.yaml": "queue_name: jobs\n",
        "tests/test_app.py": 'conf = {"from_test": 1}\nvalue = conf["only_read_in_a_test"]\n',
    }
    result = scan_of(tmp_path, files)
    orphans = [h for h in result["hits"] if h["rule"] == "orphan-key"]
    assert [(h["file"], h["line"], h["key"]) for h in orphans] == [
        ("src/app.py", marked(ORPHANS)[0], "_digest"),
        ("src/app.py", marked(ORPHANS)[1], "never_written"),
    ]
    assert orphans[0]["similar"] == ["digest"] and orphans[1]["similar"] == []
    assert 'key "_digest" is read here but nothing in the repository writes it' in orphans[0]["why"]
    assert "close name: digest" in orphans[0]["why"]


TIMEOUTS = """import socket
import urllib.request
from urllib.request import urlopen

import httpx
import requests


def calls(url, req, session, **kw):
    urllib.request.urlopen(req)  # hit
    urlopen(req, None, 5)
    urlopen(req, timeout=5)
    requests.get(url)  # hit
    requests.post(url, timeout=3)
    requests.request("GET", url, **kw)
    httpx.Client()  # hit
    httpx.AsyncClient(timeout=5)
    httpx.post(url)  # hit
    socket.create_connection(("db", 5432))  # hit
    socket.create_connection(("db", 5432), 3)
    session.get(url)
"""


def test_no_timeout(tmp_path: Path) -> None:
    result = scan_of(tmp_path, {"src/app.py": TIMEOUTS})
    assert lines(result, "no-timeout") == marked(TIMEOUTS)


RETRIES = """import time

MAX = 3


def forever(job):
    while True:  # unbounded
        try:
            return job()
        except OSError:
            continue


def counted(job):
    attempt = 0
    while True:  # bounded
        attempt += 1
        try:
            return job()
        except OSError:
            if attempt >= MAX:
                raise


def one_error_type_counted(job):
    tries = 0
    while True:  # unbounded
        try:
            job()
            return
        except TimeoutError:
            tries += 1
            if tries > 5:
                return
        except Exception:
            time.sleep(1)


def clocked(job, deadline):
    while True:  # bounded
        if time.monotonic() > deadline:
            raise TimeoutError
        try:
            return job()
        except OSError:
            time.sleep(1)


def counted_every_pass(job):
    attempt = 0
    while True:  # bounded
        attempt += 1
        if attempt > MAX:
            break
        try:
            return job()
        except OSError:
            time.sleep(1)


def no_try():
    while True:
        work()


def nested_loop_try(items):
    while True:
        for item in items:
            try:
                item()
            except OSError:
                continue
"""


def test_retry_loop(tmp_path: Path) -> None:
    result = scan_of(tmp_path, {"src/app.py": RETRIES})
    loops = {h["line"]: h for h in result["hits"] if h["rule"] == "retry-loop"}
    assert sorted(loops) == sorted(marked(RETRIES, "# bounded") + marked(RETRIES, "# unbounded"))
    assert [n for n, h in sorted(loops.items()) if h["bounded"]] == marked(RETRIES, "# bounded")
    forever = loops[marked(RETRIES, "# unbounded")[0]]
    assert forever["exits"] == {"break": 0, "return": 1, "raise": 0} and forever["limit_check"] is False
    assert "compares nothing to a limit" in forever["why"]
    mixed = loops[marked(RETRIES, "# unbounded")[1]]
    assert mixed["limit_check"] is True and "(except Exception)" in mixed["why"]
    assert "a clock or a deadline is checked" in loops[marked(RETRIES, "# bounded")[1]]["why"]
    assert "advances on every pass" in loops[marked(RETRIES, "# bounded")[2]]["why"]


DELETES = """def replace(store, doc, client):
    store.delete_chunks(doc)  # hit
    vectors = client.embed(doc)
    store.insert_chunks(doc, vectors)


def atomic(conn, doc):
    with conn:
        conn.execute("DELETE FROM meta WHERE doc = ?", (doc,))  # hit
        conn.execute(f"INSERT INTO meta VALUES ({doc!r})")


def write_first(store, doc):
    store.save(doc)
    store.remove_old(doc)


def unrelated(items):
    items.clear()
    items.append(1)


def camel(repo, doc):
    repo.removeAll(doc)  # hit
    repo.addAll(doc)
"""


def test_delete_then_write(tmp_path: Path) -> None:
    result = scan_of(tmp_path, {"src/app.py": DELETES})
    hits = [h for h in result["hits"] if h["rule"] == "delete-then-write"]
    assert [h["line"] for h in hits] == marked(DELETES)
    replace, atomic, camel = hits
    assert (replace["same_with"], replace["between"], replace["write_line"]) == (False, ["embed"], 4)
    assert atomic["same_with"] is True and "execute(DELETE) at line 9 then execute(INSERT) at line 10" in atomic["why"]
    assert (camel["same_with"], camel["between"]) == (False, [])


def test_builtin_hash_unless_the_module_defines_its_own(tmp_path: Path) -> None:
    files = {
        "src/app.py": "def ident(text):\n    return hash(text)  # hit\n",
        "src/own.py": "from mylib import hash\n\n\ndef ident(text):\n    return hash(text)\n",
    }
    result = scan_of(tmp_path, files)
    assert [(h["file"], h["line"]) for h in result["hits"] if h["rule"] == "builtin-hash"] == [("src/app.py", 2)]


def test_assert_in_code_but_not_in_tests(tmp_path: Path) -> None:
    files = {
        "src/app.py": "def check(x):\n    assert x > 0  # hit\n",
        "tests/test_app.py": "def test_it():\n    assert True\n",
        "src/thing_test.py": "assert 1\n",
        "web/app.spec.ts": "try { run(); } catch (e) { }\n",
    }
    result = scan_of(tmp_path, files)
    assert [(h["file"], h["line"]) for h in result["hits"]] == [("src/app.py", 2)]
    assert result["counts"]["test_files_skipped"] == 3


TYPE_IGNORES = """from lib import thing  # type: ignore[import-not-found]  # hit
value = thing()  # type:ignore  # hit
text = "# type: ignore"
"""


def test_type_ignore_in_comments_only(tmp_path: Path) -> None:
    assert lines(scan_of(tmp_path, {"src/app.py": TYPE_IGNORES}), "type-ignore") == marked(TYPE_IGNORES)


MUTABLE = """def a(x=[]):  # hit
    return x


def b(x={}):  # hit
    return x


def c(*, x=set()):  # hit
    return x


def d(x=None, y=()):
    return x, y


f = lambda x=[]: x  # hit
"""


def test_mutable_default(tmp_path: Path) -> None:
    assert lines(scan_of(tmp_path, {"src/app.py": MUTABLE}), "mutable-default") == marked(MUTABLE)


TODOS = """# TODO: split this module  # hit
x = "TODO in a string"
# FIXME later  # hit
# todo in lower case is a note, not a marker
y = 1  # HACK around the parser  # hit
"""


def test_todo_in_python_comments(tmp_path: Path) -> None:
    assert lines(scan_of(tmp_path, {"src/app.py": TODOS}), "todo") == marked(TODOS)


CSHARP = """class Worker {
    void A() { try { Run(); } catch (Exception ex) { } }  // hit
    void B() { try { Run(); } catch { Log(); } }  // hit
    void C() { try { Run(); } catch (IOException ex) { Log(ex); } }
    void D() { try { Run(); } catch (Exception ex) { Log(ex); throw; } }
    void E() { try { Run(); } catch (Exception ex) when (ex is TimeoutException) { Log(ex); } }
}
"""

TYPESCRIPT = """try { run(); } catch (e) { }  // hit
try { run(); } catch (e) { console.error(e); }  // hit
try { run(); } catch (e) { throw new AppError(e); }
try { run(); } catch {
  // nothing to do
}  // the catch above is empty: hit on its first line
"""

JAVA = """class Main {
  void a() { try { run(); } catch (Exception e) { log(e); } }  // hit
  void b() { try { run(); } catch (IOException e) { log(e); } }
  void c() { try { run(); } catch (Throwable t) { throw new RuntimeException(t); } }
}
"""

GO = """package main

func a() error {
	if err != nil { }  // hit
	if err != nil { return err }
	// TODO: wrap the error
	return nil
}
"""


def test_catch_all_in_the_shallow_languages(tmp_path: Path) -> None:
    files = {"src/Worker.cs": CSHARP, "web/app.ts": TYPESCRIPT, "src/Main.java": JAVA, "cmd/main.go": GO}
    result = scan_of(tmp_path, files)
    assert lines(result, "catch-all", "src/Worker.cs") == marked(CSHARP, "// hit")
    assert lines(result, "catch-all", "web/app.ts") == [*marked(TYPESCRIPT, "// hit"), 4]
    assert lines(result, "catch-all", "src/Main.java") == marked(JAVA, "// hit")
    assert lines(result, "catch-all", "cmd/main.go") == marked(GO, "// hit")
    assert lines(result, "todo", "cmd/main.go") == [6]
    assert result["languages_shallow"] == ["csharp", "go", "java", "typescript"]
    assert result["files"] == {"csharp": 1, "go": 1, "java": 1, "typescript": 1}
    empty = next(h for h in result["hits"] if h["file"] == "src/Worker.cs")
    assert empty["why"] == "empty catch block: the error disappears"


README = """# Orders

The service never loses an order. It is fast.

- Every request has a timeout of 5 s.
- Requests are retried at most 3 times
  and then dropped.

    every line of this indented block is code

```python
# Always skipped, it is code.
```

| key | meaning |
|---|---|
| `retries` | a request is retried at most 3 times |
"""

MODULE = '''"""Orders.

Results are always sorted by id.
"""


def place(order):
    """Place an order. It must be paid first."""
'''


def test_promises_from_docs_and_docstrings(tmp_path: Path) -> None:
    files = {
        "README.md": README,
        "CONTRIBUTING.md": "You must sign every commit.\n",
        "docs/design/storage.md": "Writes are idempotent.\n",
        "adr/0001-queue.rst": "Messages are delivered exactly once.\n",
        "notes/ideas.md": "This must not be read: notes/ is not a doc folder.\n",
        "src/orders.py": MODULE,
        "tests/test_orders.py": '"""Tests must always pass."""\n',
    }
    found = [(p["file"], p["line"], p["text"], p["kind"]) for p in scan_of(tmp_path, files)["promises"]]
    assert found == [
        ("CONTRIBUTING.md", 1, "You must sign every commit.", "general"),
        ("README.md", 3, "The service never loses an order.", "data-loss"),
        ("README.md", 5, "Every request has a timeout of 5 s.", "timeout"),
        ("README.md", 6, "Requests are retried at most 3 times and then dropped.", "retry"),
        ("README.md", 17, "`retries` | a request is retried at most 3 times", "retry"),
        ("adr/0001-queue.rst", 1, "Messages are delivered exactly once.", "idempotency"),
        ("docs/design/storage.md", 1, "Writes are idempotent.", "idempotency"),
        ("src/orders.py", 3, "Results are always sorted by id.", "general"),
        ("src/orders.py", 8, "It must be paid first.", "ordering"),
    ]


def test_long_promises_are_trimmed(tmp_path: Path) -> None:
    long = "Every " + "very " * 80 + "long sentence ends here."
    text = scan_of(tmp_path, {"README.md": long + "\n"})["promises"][0]["text"]
    assert len(text) == audit.PROMISE_CHARS and text.endswith("...")


def test_path_limits_hits_but_keeps_top_level_docs_and_repo_wide_writes(tmp_path: Path) -> None:
    files = {
        "README.md": "Ids are always stable.\n",
        "docs/rules.md": "Every call has a timeout.\n",
        "src/a/x.py": 'def f(run):\n    return hash(run["written_in_b"])\n',
        "src/a/README.md": "Module a never blocks.\n",
        "src/b/y.py": 'def g():\n    hash(1)\n    return {"written_in_b": 1}\n',
        "src/b/README.md": "Module b must not be listed.\n",
    }
    result = scan_of(tmp_path, files, path="src/a")
    assert result["scope"] == "src/a"
    assert [(h["rule"], h["file"]) for h in result["hits"]] == [("builtin-hash", "src/a/x.py")]
    assert [p["file"] for p in result["promises"]] == ["README.md", "docs/rules.md", "src/a/README.md"]
    assert result["files"] == {"markdown": 1, "python": 1}


def test_max_per_rule_caps_hits_but_counts_keep_the_total(tmp_path: Path) -> None:
    code = "".join(f"a{n} = hash({n})\n" for n in range(5))
    result = scan_of(tmp_path, {"src/app.py": code}, max_per_rule=2)
    assert [h["line"] for h in result["hits"]] == [1, 2]
    assert result["counts"]["builtin-hash"] == 5


def test_skipped_folders_and_unparsable_files(tmp_path: Path) -> None:
    files = {
        "node_modules/lib/index.js": "try { a(); } catch (e) { }\n",
        ".venv/lib/site.py": "x = hash(1)\n",
        "build/gen.py": "x = hash(1)\n",
        "src/broken.py": "def broken(:\n",
        "src/ok.py": "x = hash(1)\n",
    }
    result = scan_of(tmp_path, files)
    assert [(h["rule"], h["file"]) for h in result["hits"]] == [("builtin-hash", "src/ok.py")]
    assert result["unparsed"] == ["src/broken.py: SyntaxError 1"]


SENTINEL = "SENTINEL-6f1c-never-shown"


@pytest.mark.parametrize("with_git", [True, False], ids=["git", "no-git"])
def test_env_files_are_never_opened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_git: bool) -> None:
    files = {
        ".env": f"ACME_TOKEN={SENTINEL}\n",
        ".env.production": f"ACME_TOKEN={SENTINEL}\n",
        "config/.env.local": f'{{"{SENTINEL}": 1}}\n',
        ".env.d/settings.py": f'TOKEN = "{SENTINEL}"\nx = hash(TOKEN)\n',
        "README.md": "Every secret stays in .env.\n",
        "src/app.py": 'import os\n\nTOKEN = os.environ.get("ACME_TOKEN")\n',
    }
    repo = make_repo(tmp_path / "repo", files) if with_git else write(tmp_path / "repo", files)
    opened: list[str] = []
    real_read_text, real_read_bytes, real_path_open, real_open = Path.read_text, Path.read_bytes, Path.open, open

    def spy_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        opened.append(self.name)
        return real_read_text(self, *args, **kwargs)

    def spy_read_bytes(self: Path) -> bytes:
        opened.append(self.name)
        return real_read_bytes(self)

    def spy_path_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        opened.append(self.name)
        return real_path_open(self, *args, **kwargs)

    def spy_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(Path(str(file)).name)
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy_read_text)
    monkeypatch.setattr(Path, "read_bytes", spy_read_bytes)
    monkeypatch.setattr(Path, "open", spy_path_open)
    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(io, "open", spy_open)
    result = audit.scan(repo)
    monkeypatch.undo()
    assert "app.py" in opened and "README.md" in opened
    assert not [name for name in opened if audit.is_secret(name)]
    assert "settings.py" not in opened and result["hits"] == []
    assert SENTINEL not in json.dumps(result)
    output = subprocess.run(
        [sys.executable, str(SCAN), str(repo)], capture_output=True, text=True, check=True, timeout=60
    ).stdout
    assert SENTINEL not in output and ".env" not in json.dumps(json.loads(output)["hits"])


def test_command_line(tmp_path: Path) -> None:
    repo = write(tmp_path / "repo", {"src/app.py": "x = hash(1)\ny = hash(2)\n", "README.md": "It never fails.\n"})
    result = run_json(SCAN, str(repo), "--path", "src", "--max-per-rule", "1")
    assert result["scope"] == "src" and len(result["hits"]) == 1 and result["counts"]["builtin-hash"] == 2
    assert [p["file"] for p in result["promises"]] == ["README.md"]
    for args in (["--path", "missing"], ["--path", ".."]):
        done = subprocess.run([sys.executable, str(SCAN), str(repo), *args], capture_output=True, text=True, timeout=60)
        assert done.returncode == 2 and done.stdout == ""
    done = subprocess.run([sys.executable, str(SCAN), str(tmp_path / "nowhere")], capture_output=True, timeout=60)
    assert done.returncode == 2
