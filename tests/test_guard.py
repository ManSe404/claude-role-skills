"""The hook guard: what it asks about, refuses and lets through, in the skill's turn and after it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from conftest import ROOT, load

sys.path.insert(0, str(ROOT / "shared"))
guard = load(ROOT / "shared" / "guard.py")
SKILL = "ds-explore"


def jmbg(first_twelve: str) -> str:
    d = [int(c) for c in first_twelve]
    m = 11 - (sum((7 - i) * (d[i] + d[i + 6]) for i in range(6)) % 11)
    return first_twelve + str(0 if m > 9 else m)


@pytest.fixture(autouse=True)
def own_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test keeps the guard's per-session state in its own folder, not in the shared temp folder."""
    monkeypatch.setattr(guard, "STATE_DIR", tmp_path / "state")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A project folder outside the temp roots the guard allows, so writes into it count as changes."""
    root = Path.home() / ".cache" / "claude-role-skills-tests" / uuid.uuid4().hex
    root.mkdir(parents=True)
    (root / "people.csv").write_text("customer_id,full_name,email,plan\nC1,Ana Lipić,ana@example.com,basic\n")
    (root / "numbers.csv").write_text("day,orders\n2026-01-01,4\n")
    (root / "people.jsonl").write_text('{"id": 1, "email": "x@example.com"}\n')
    yield root
    for path in sorted(root.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    root.rmdir()


def env(**extra: str) -> dict[str, str]:
    return {"HOME": str(Path.home()), **extra}


def event(
    cwd: Path, tool: str, prompt: str = "turn-1", session: str | None = None, **tool_input: Any
) -> dict[str, Any]:
    return {
        "session_id": session or uuid.uuid4().hex,
        "prompt_id": prompt,
        "cwd": str(cwd),
        "tool_name": tool,
        "tool_input": tool_input,
    }


def pre(cwd: Path, tool: str, personal: bool = False, environ: dict[str, str] | None = None, **tool_input: Any) -> Any:
    return guard.pre(event(cwd, tool, **tool_input), SKILL, personal, environ or env())


def kind(result: Any) -> str | None:
    return None if result is None else result["hookSpecificOutput"]["permissionDecision"]


def bash(cwd: Path, command: str, personal: bool = False, environ: dict[str, str] | None = None) -> str | None:
    return kind(pre(cwd, "Bash", personal, environ, command=command))


# ---------------------------------------------------------------------------- the skill's turn


def test_the_guard_steps_aside_after_the_users_next_message(repo: Path) -> None:
    session = uuid.uuid4().hex
    first = event(repo, "Write", "turn-1", session, file_path=str(repo / "fix.py"), content="x")
    assert kind(guard.pre(first, SKILL, False, env())) == "ask"
    later = event(repo, "Write", "turn-2", session, file_path=str(repo / "fix.py"), content="x")
    assert guard.pre(later, SKILL, False, env()) is None


def test_invoking_the_skill_again_guards_that_turn(repo: Path) -> None:
    session = uuid.uuid4().hex
    guard.pre(event(repo, "Read", "turn-1", session, file_path="x"), SKILL, False, env())
    again = event(repo, "Skill", "turn-3", session, skill=f"data-scientist:{SKILL}")
    assert guard.pre(again, SKILL, False, env()) is None
    write = event(repo, "Write", "turn-3", session, file_path=str(repo / "a.py"), content="x")
    assert kind(guard.pre(write, SKILL, False, env())) == "ask"


def test_another_skill_being_invoked_does_not_move_this_ones_turn(repo: Path) -> None:
    session = uuid.uuid4().hex
    guard.pre(event(repo, "Read", "turn-1", session, file_path="x"), SKILL, False, env())
    guard.pre(event(repo, "Skill", "turn-2", session, skill="ds-dataset"), SKILL, False, env())
    write = event(repo, "Write", "turn-2", session, file_path=str(repo / "a.py"), content="x")
    assert guard.pre(write, SKILL, False, env()) is None


def test_old_state_is_dropped() -> None:
    old = guard.STATE_DIR / "old-session.json"
    old.parent.mkdir(parents=True)
    old.write_text("{}")
    os.utime(old, (1, 1))
    guard.save_state(guard.state_file("new-session"), {"x": "y"})
    assert not old.exists()
    assert guard.load_state(guard.state_file("new-session")) == {"x": "y"}


def test_without_a_prompt_id_it_guards(repo: Path) -> None:
    call = event(repo, "Write", file_path=str(repo / "a.py"), content="x")
    del call["prompt_id"]
    assert kind(guard.pre(call, SKILL, False, env())) == "ask"


# ---------------------------------------------------------------------------- writes


def test_a_write_into_the_project_asks(repo: Path) -> None:
    result = pre(repo, "Write", file_path=str(repo / "src" / "app.py"), content="x")
    assert kind(result) == "ask"
    assert "until the user says yes" in result["hookSpecificOutput"]["permissionDecisionReason"]
    assert kind(pre(repo, "Edit", file_path="src/app.py", old_string="a", new_string="b")) == "ask"


def test_the_page_and_temp_files_are_written_freely(repo: Path) -> None:
    pages = Path.home() / "claude-pages" / "acme" / "ds-explore-2026-11-10.json"
    assert pre(repo, "Write", file_path=str(pages), content="{}") is None
    assert pre(repo, "Write", file_path="/tmp/scratch/profile.json", content="{}") is None
    custom = env(CLAUDE_PAGES_DIR="pages")
    assert pre(repo, "Write", environ=custom, file_path=str(repo / "pages" / "x" / "notes.json"), content="{}") is None


def test_the_skills_own_page_file_may_go_where_the_user_asked(repo: Path) -> None:
    assert pre(repo, "Write", file_path=str(repo / "docs" / "ds-explore-2026-11-10.html"), content="x") is None
    assert kind(pre(repo, "Write", file_path=str(repo / "docs" / "ds-dataset-2026-11-10.html"), content="x")) == "ask"
    assert kind(pre(repo, "Write", file_path=str(repo / "ds-explore-notes.json"), content="x")) == "ask"


@pytest.mark.parametrize(
    "command",
    [
        "git commit -am 'fix'",
        "git push origin main",
        "git checkout -- src/app.py",
        "git stash",
        "git branch feature/x",
        "rm -rf build",
        "mv a.py b.py",
        "echo hi > notes.txt",
        "printf x >> src/app.py",
        "sed -i 's/a/b/' src/app.py",
        "perl -pi -e 's/a/b/' src/app.py",
        "pip install requests",
        "uv add pandas",
        "uv pip install pandas",
        "python3 -m pip install pandas",
        "npm install",
        "touch src/new.py",
        "mkdir docs/adr",
        "cat > notes.md <<'EOF'\nhello\nEOF",
        "python3 report.py | tee out.txt",
        "cd src && rm app.py",
    ],
)
def test_shell_changes_ask(repo: Path, command: str) -> None:
    assert bash(repo, command) == "ask", command


@pytest.mark.parametrize(
    "command",
    [
        "git log --oneline -20",
        "git status --short",
        "git diff HEAD~1 -- src",
        "git show 49bc16d:src/app.py",
        "git stash list",
        "git branch",
        "git branch -a",
        "git -C /tmp/fixture init -q",
        "python3 scripts/data_profile.py data/people.csv > /tmp/scratch/profile.json 2>/dev/null",
        "python3 scripts/explore_target.py --data a.csv --label y 2>&1 | head -50",
        'mkdir -p "${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/acme"',
        'python3 render_page.py p.json -o "${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/acme/ds-explore-2026-11-10.html"',
        "rm -f /tmp/scratch/old.json",
        'rm -f "$SCRATCH/old.json"',
        "cd /tmp/work && rm -rf out",
        "python3 - <<'EOF'\nimport json\nif 3 > 2: print('x')\nEOF",
        "sed -n '1,40p' src/app.py",
        "uv run pytest -q",
        "uv pip list",
        "ls -la src | wc -l",
        "python3 s.py >&2",
        "find . -name '*.py' |\n  xargs wc -l",
        "chmod +x /tmp/scratch/run.sh",
        "terraform fmt -check",
    ],
)
def test_reading_and_temp_work_pass(repo: Path, command: str) -> None:
    assert bash(repo, command, environ=env(SCRATCH="/tmp/scratch")) is None, command


def test_a_command_the_guard_cannot_parse_passes(repo: Path) -> None:
    assert bash(repo, "echo 'unbalanced") is None


# ---------------------------------------------------------------------------- online


@pytest.mark.parametrize(
    "command",
    [
        "curl -s https://prices.azure.com/api/retail/prices",
        "wget https://example.com/x",
        "python3 scripts/deps.py --online",
        "python3 scripts/cloud_prices.py --online=azure",
        "git fetch origin",
        "git -C repo pull",
        "az account show",
        "aws sts get-caller-identity",
        "terraform plan",
        "npm audit",
        "pip-audit -r requirements.txt",
        "python3 -c 'import urllib.request; urllib.request.urlopen(\"https://x\")'",
        "python3 - <<'EOF'\nimport requests\nrequests.get('https://x')\nEOF",
    ],
)
def test_going_online_asks(repo: Path, command: str) -> None:
    assert bash(repo, command) == "ask", command


def test_web_tools_ask(repo: Path) -> None:
    assert kind(pre(repo, "WebFetch", url="https://x", prompt="p")) == "ask"
    assert kind(pre(repo, "WebSearch", query="q")) == "ask"


# ---------------------------------------------------------------------------- personal data


def test_reading_a_file_with_personal_columns_is_refused(repo: Path) -> None:
    result = pre(repo, "Read", personal=True, file_path=str(repo / "people.csv"))
    assert kind(result) == "deny"
    assert "full_name, email" in result["hookSpecificOutput"]["permissionDecisionReason"]
    assert kind(pre(repo, "Read", personal=True, file_path=str(repo / "people.jsonl"))) == "deny"
    assert pre(repo, "Read", personal=True, file_path=str(repo / "numbers.csv")) is None
    assert pre(repo, "Read", personal=False, file_path=str(repo / "people.csv")) is None


@pytest.mark.parametrize(
    "command",
    [
        "head -5 people.csv",
        "cat people.csv",
        "tail -n 20 people.jsonl",
        "awk -F, '{print $2}' people.csv | sort | uniq -c",
        "grep ana people.csv",
        "cut -d, -f2,3 people.csv | head",
        "python3 -c \"import csv\nfor row in csv.reader(open('people.csv')): print(row)\"",
    ],
)
def test_printing_rows_with_personal_columns_is_refused(repo: Path, command: str) -> None:
    assert bash(repo, command, personal=True) == "deny", command


@pytest.mark.parametrize(
    "command",
    [
        "head -1 people.csv",
        "head -n 1 people.csv",
        "wc -l people.csv",
        "head -5 people.csv | wc -l",
        "grep -c ana people.csv",
        "cat people.csv | python3 scripts/measure.py",
        "head -50 numbers.csv",
        "head -5 people.csv > /tmp/scratch/sample.csv",
        "python3 scripts/data_profile.py people.csv",
    ],
)
def test_counting_and_headers_pass(repo: Path, command: str) -> None:
    assert bash(repo, command, personal=True) is None, command


def test_raw_reads_are_only_refused_for_data_skills(repo: Path) -> None:
    assert bash(repo, "head -5 people.csv", personal=False) is None


def test_a_page_with_a_personal_value_is_refused(repo: Path) -> None:
    page = str(Path.home() / "claude-pages" / "acme" / "ds-explore-2026-11-10.json")
    result = pre(repo, "Write", personal=True, file_path=page, content='{"text": "ask ana@example.com"}')
    assert kind(result) == "deny"
    assert "1 e-mail" in result["hookSpecificOutput"]["permissionDecisionReason"]
    assert pre(repo, "Write", personal=True, file_path=page, content='{"text": "3 e-mail columns"}') is None
    edit = pre(repo, "Edit", personal=True, file_path=page, old_string="a", new_string=f"id {jmbg('010199071000')}")
    assert kind(edit) == "deny"


# ---------------------------------------------------------------------------- redaction


def test_redaction_of_values() -> None:
    iban = "GB82 WEST 1234 5698 7654 32"
    number = jmbg("010199071000")
    text, found = guard.redact(f"a ana@example.com b {iban} c {number} d")
    assert text == "a [e-mail removed] b [IBAN removed] c [JMBG removed] d"
    assert found == {"e-mail": 1, "IBAN": 1, "JMBG": 1}


def test_what_is_not_redacted() -> None:
    text = "icon@2x.png 2026-11-10 1234567890123 GB00 WEST 1234 5698 7654 32 order 4500"
    assert guard.redact(text) == (text, {})


def test_output_is_cleaned_before_claude_sees_it(repo: Path) -> None:
    session = uuid.uuid4().hex
    guard.pre(event(repo, "Bash", "t1", session, command="ls"), SKILL, True, env())
    call = event(repo, "Bash", "t1", session, command="x")
    call["tool_response"] = {"stdout": "row: ana@example.com", "stderr": "", "interrupted": False}
    result = guard.post(call, SKILL)["hookSpecificOutput"]
    assert result["updatedToolOutput"] == {"stdout": "row: [e-mail removed]", "stderr": "", "interrupted": False}
    assert "1 e-mail" in result["additionalContext"]
    read = event(repo, "Read", "t1", session, file_path="notes.txt")
    read["tool_response"] = {"type": "text", "file": {"filePath": "notes.txt", "content": "ana@example.com\n"}}
    assert guard.post(read, SKILL)["hookSpecificOutput"]["updatedToolOutput"]["file"]["content"] == "[e-mail removed]\n"
    clean = event(repo, "Bash", "t1", session, command="x")
    clean["tool_response"] = {"stdout": "12 rows", "stderr": ""}
    assert guard.post(clean, SKILL) is None
    later = event(repo, "Bash", "t2", session, command="x")
    later["tool_response"] = {"stdout": "ana@example.com", "stderr": ""}
    assert guard.post(later, SKILL) is None


# ---------------------------------------------------------------------------- as Claude Code runs it


def run(args: list[str], payload: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "shared" / "guard.py"), *args],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        env={**os.environ, "TMPDIR": str(guard.STATE_DIR.parent)},
    )


def test_main_prints_a_decision(repo: Path) -> None:
    done = run(["pre", f"data-scientist:{SKILL}"], json.dumps(event(repo, "Bash", command="git push")))
    assert done.returncode == 0
    assert json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"
    quiet = run(["pre", SKILL], json.dumps(event(repo, "Bash", command="git status")))
    assert (quiet.returncode, quiet.stdout) == (0, "")


def test_an_error_of_its_own_never_blocks() -> None:
    """Exit 2 would block the call; a broken guard must exit 1, which only shows the error."""
    broken = run(["pre", SKILL], "not json")
    assert broken.returncode == 1
    assert broken.stdout == ""
    assert run(["sideways"], "{}").returncode == 1
