#!/usr/bin/env python3
"""Enforce a skill's Never rules while the skill is working. Claude Code runs this as a hook.

Usage, from the `hooks:` block of a SKILL.md:
    python3 guard.py pre SKILL [personal]     on PreToolUse
    python3 guard.py post SKILL personal      on PostToolUse

It reads the hook's JSON on stdin and prints a decision as JSON, or prints nothing and lets the call through.

Only during the turn in which Claude invoked the skill:
- Changes need the user's click. A Write, Edit or NotebookEdit outside the pages folder, a temp folder or the skill's
  own page file, and a shell command that changes files, git or the installed packages, make Claude Code ask the user.
- Going online needs the user's click: WebFetch, WebSearch, and shell commands that reach the network (curl, wget, git
  fetch, pull or clone, az, aws, gcloud, terraform init or plan, dependency audits, any `--online` flag).
- With `personal` (the data skills): reading a data file whose header names a personal column with Read, cat, head and
  the like is refused, because the skill's scripts print counts instead; e-mail addresses, IBANs and JMBGs are removed
  from shell and Read output before Claude sees them; a Write or Edit that would put one on a page is refused.

After the user's next message the guard steps aside, so what a skill does "after the yes" runs under the normal
permission rules. The skill's turn is recorded per session in a small state file in the temp folder, and it is set
again when Claude invokes the skill again. In a run with `claude -p` nobody can answer a question, so "ask" works as
"no".

It catches the usual ways, not every way: code run by an interpreter (a Python heredoc that writes a file or opens a
socket) is not parsed, and personal values that no pattern recognises, such as names, are only kept out by refusing
the raw reads. On an error of its own it lets the call through: exit 1 shows the error and blocks nothing.

Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Any

DATA_SUFFIXES = {".csv", ".tsv", ".jsonl", ".ndjson"}
EDIT_TOOLS = {"Write", "Edit", "NotebookEdit", "MultiEdit"}
WEB_TOOLS = {"WebFetch", "WebSearch"}
SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "\n"}
REDIRECTS = {">", ">>", ">|", "&>", "&>>"}
DUPLICATES = {">&", "<&", "<<", "<<<", "<<-"}
VIEWERS = {
    "cat", "head", "tail", "less", "more", "sed", "awk", "gawk", "mawk", "cut", "grep", "egrep", "fgrep", "rg",
    "sort", "uniq", "column", "csvlook", "csvcut", "csvgrep", "xsv", "qsv", "mlr", "jq", "bat", "nl", "tac", "paste",
    "shuf", "strings", "xxd", "od",
}  # fmt: skip
PATH_CHANGERS = {"rm", "rmdir", "mv", "cp", "touch", "mkdir", "ln", "chmod", "chown", "truncate", "tee", "install"}
NETWORK_COMMANDS = {
    "curl", "wget", "http", "https", "httpie", "nc", "ncat", "netcat", "telnet", "ssh", "scp", "sftp", "ftp",
    "az", "aws", "gcloud", "gsutil", "bq", "kubectl", "pip-audit", "safety", "osv-scanner", "trivy", "snyk",
}  # fmt: skip
GIT_CHANGES = {
    "commit", "push", "reset", "checkout", "switch", "restore", "clean", "rebase", "merge", "cherry-pick", "revert",
    "am", "apply", "rm", "mv", "add", "init", "pull", "fetch", "clone", "submodule", "worktree", "tag", "branch",
}  # fmt: skip
GIT_ONLINE = {"push", "pull", "fetch", "clone", "ls-remote", "submodule"}
GIT_READ_FORMS = {
    "stash": {"list", "show"},
    "tag": {"-l", "--list"},
    "branch": {"-a", "-r", "-l", "--list", "-v", "-vv"},
}
INSTALLERS = {
    ("pip", "install"), ("pip3", "install"), ("pip", "uninstall"), ("uv", "add"), ("uv", "remove"), ("uv", "sync"),
    ("npm", "install"), ("npm", "i"), ("npm", "ci"), ("npm", "uninstall"),
    ("yarn", "add"), ("pnpm", "add"), ("pnpm", "install"), ("apt", "install"), ("apt-get", "install"),
    ("brew", "install"), ("cargo", "install"), ("go", "install"), ("go", "get"), ("dotnet", "add"),
}  # fmt: skip
TERRAFORM_ONLINE = {"init", "plan", "apply", "refresh", "import", "destroy", "get", "providers"}
NETWORK_CODE = re.compile(r"\burllib\.request\b|\brequests\.(get|post|put|head|Session)\b|\bhttp\.client\b|\bsocket\.")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.([A-Za-z]{2,24})\b")
FILE_ENDINGS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "js", "ts", "css", "py", "md", "json", "html", "txt"}
IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b")
JMBG = re.compile(r"(?<!\d)\d{13}(?!\d)")
VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}|\$([A-Za-z_][A-Za-z0-9_]*)")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
STATE_DIR = Path(tempfile.gettempdir()) / "claude-role-skills-guard"
STATE_DAYS = 2


# ---------------------------------------------------------------------------- the skill's turn


def state_file(session: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session) or "unknown"
    return STATE_DIR / f"{safe}.json"


def load_state(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def save_state(path: Path, state: dict[str, str]) -> None:
    """Write the session's state, and drop the state of sessions untouched for two days."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(".part")
        part.write_text(json.dumps(state), "utf-8")
        part.replace(path)
        for old in path.parent.glob("*.json"):
            if path.stat().st_mtime - old.stat().st_mtime > STATE_DAYS * 86400:
                old.unlink(missing_ok=True)
    except OSError:
        pass


def bare(skill: str) -> str:
    """`data-scientist:ds-explore` and `ds-explore` are the same skill."""
    return skill.rsplit(":", 1)[-1].strip()


def in_skill_turn(event: dict[str, Any], skill: str, record: bool) -> bool:
    """Whether this call belongs to the turn that invoked the skill.

    The first call the guard sees comes right after the skill was invoked, so its prompt id is the skill's turn. A
    call of the Skill tool for this skill sets it again. Without a prompt id there is no way to tell, so it guards.
    """
    prompt = event.get("prompt_id")
    if not prompt:
        return True
    path = state_file(str(event.get("session_id") or ""))
    state = load_state(path)
    invoked = event.get("tool_name") == "Skill" and bare(str((event.get("tool_input") or {}).get("skill", ""))) == skill
    if record and (invoked or skill not in state):
        state[skill] = str(prompt)
        save_state(path, state)
    return state.get(skill, str(prompt)) == str(prompt)


# ---------------------------------------------------------------------------- paths


def expand(word: str, env: dict[str, str]) -> str:
    """`$NAME`, `${NAME}`, `${NAME:-default}` and a leading `~`, from the environment Claude's shell inherits."""

    def one(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(3)
        value = env.get(name)
        if value:
            return value
        default = match.group(2)
        return expand(default, env) if default is not None else match.group(0)

    text = VAR.sub(one, word)
    return str(Path(text).expanduser()) if text.startswith("~") else text


def pages_dir(env: dict[str, str], cwd: Path) -> Path:
    raw = env.get("CLAUDE_PAGES_DIR") or str(Path(env.get("HOME") or Path.home()) / "claude-pages")
    path = Path(expand(raw, env)).expanduser()
    return (path if path.is_absolute() else cwd / path).resolve()


def temp_roots(env: dict[str, str]) -> list[Path]:
    roots = {Path(tempfile.gettempdir()), Path("/tmp"), Path("/var/tmp")}
    if env.get("TMPDIR"):
        roots.add(Path(env["TMPDIR"]))
    return [r.resolve() for r in roots]


def inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def resolve(word: str, cwd: Path | None, env: dict[str, str]) -> Path | None:
    """The absolute path a shell word names, or None when the guard cannot know it (a variable, an unknown folder)."""
    text = expand(word, env)
    if not text or "$" in text or "`" in text:
        return None
    path = Path(text)
    if not path.is_absolute():
        if cwd is None:
            return None
        path = cwd / path
    return path.resolve()


def page_file(path: Path, skill: str) -> bool:
    """The skill's own page: `<skill>-...<date>....json` or `.html`, wherever the user asked for it."""
    name = path.name
    return name.startswith(f"{skill}-") and path.suffix in (".json", ".html") and DATE.search(name) is not None


def may_write(path: Path | None, skill: str, cwd: Path, env: dict[str, str]) -> bool:
    if path is None or str(path).startswith("/dev/"):
        return True
    if page_file(path, skill):
        return True
    return any(inside(path, root) for root in [pages_dir(env, cwd), *temp_roots(env)])


# ---------------------------------------------------------------------------- shell commands

Simple = tuple[list[str], Path | None]  # the words of one command, and the folder it runs in


def without_heredocs(command: str) -> tuple[str, str]:
    """The command with heredoc bodies taken out, and the bodies. A body is code or data, not shell."""
    lines = command.replace("\\\n", " ").split("\n")
    kept: list[str] = []
    bodies: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        kept.append(line)
        i += 1
        for match in HEREDOC.finditer(line):
            end = match.group(2)
            body: list[str] = []
            while i < len(lines) and lines[i].strip() != end:
                body.append(lines[i])
                i += 1
            i += 1
            bodies.append("\n".join(body))
    joined = ""
    for line in kept:
        tail = joined.rstrip()
        joined += (" " if not tail or tail.endswith(("|", "&&", "||", "(", "{")) else " ; ") + line
    return joined, "\n".join(bodies)


def tokens(command: str) -> list[str] | None:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>")
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        return list(lexer)
    except ValueError:
        return None


def pipelines_of(words: list[str], cwd: Path) -> list[list[Simple]]:
    """Pipelines of simple commands, each with the folder it runs in, following `cd` along the way."""
    raw: list[list[list[str]]] = [[[]]]
    for word in words:
        if word == "|":
            raw[-1].append([])
        elif word in SEPARATORS or (set(word) <= set(";&|()") and word not in REDIRECTS):
            raw.append([[]])
        else:
            raw[-1][-1].append(word)
    here: Path | None = cwd
    result: list[list[Simple]] = []
    for pipeline in raw:
        commands = [c for c in pipeline if c]
        if not commands:
            continue
        result.append([(c, here) for c in commands])
        name, args = command_name(commands[-1])
        if name == "cd" and len(commands) == 1:
            here = resolve(args[0], here, {}) if args else None
    return result


def command_name(words: list[str]) -> tuple[str, list[str]]:
    """The program and its arguments, past `VAR=value` assignments, `sudo`, `env`, `command` and `time`."""
    i = 0
    while i < len(words) and (
        re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[i]) or words[i] in ("sudo", "env", "command", "time", "nohup")
    ):
        i += 1
    if i >= len(words):
        return "", []
    return Path(words[i]).name, words[i + 1 :]


def redirect_targets(words: list[str]) -> list[str]:
    return [words[i + 1] for i, word in enumerate(words[:-1]) if word in REDIRECTS]


def plain_args(args: list[str]) -> list[str]:
    """Arguments that are not options, redirections or their targets, or a file descriptor."""
    kept: list[str] = []
    skip = False
    for word in args:
        if skip:
            skip = False
            continue
        if word in REDIRECTS or word in DUPLICATES or word == "<":
            skip = True
            continue
        if word.startswith("-") or re.fullmatch(r"\d", word):
            continue
        kept.append(word)
    return kept


def subcommand(args: list[str]) -> tuple[str, list[str], str | None]:
    """git's subcommand, what follows it, and the folder named by `-C`."""
    i = 0
    folder = None
    while i < len(args) and args[i].startswith("-"):
        if args[i] in ("-C", "-c", "--git-dir", "--work-tree") and i + 1 < len(args):
            folder = args[i + 1] if args[i] == "-C" else folder
            i += 2
            continue
        i += 1
    return (args[i], args[i + 1 :], folder) if i < len(args) else ("", [], folder)


def change_in(simple: Simple, skill: str, cwd: Path, env: dict[str, str]) -> str | None:
    """Why this simple command changes something outside the page and temp folders, or None."""
    words, here = simple
    for target in redirect_targets(words):
        if not may_write(resolve(target, here, env), skill, cwd, env):
            return f"it writes to {target}"
    name, args = command_name(words)
    first = next((a for a in args if not a.startswith("-")), "")
    if name == "git":
        sub, rest, folder = subcommand(args)
        if folder is not None and may_write(resolve(folder, here, env), skill, cwd, env):
            return None
        # A bare `git tag` or `git branch` lists, a bare `git stash` saves.
        if sub in GIT_READ_FORMS and ((not rest and sub != "stash") or (rest and rest[0] in GIT_READ_FORMS[sub])):
            return None
        return f"it runs git {sub}" if sub in GIT_CHANGES or sub == "stash" else None
    if (name, first) in INSTALLERS or (name == "uv" and first == "pip" and "install" in args):
        return f"it runs {name} {first}"
    if name in ("python", "python3") and args[:3] in (["-m", "pip", "install"], ["-m", "pip", "uninstall"]):
        return "it installs packages"
    if name in ("sed", "perl") and any(re.fullmatch(r"-[a-zA-Z]*i.*", a) or a.startswith("--in-place") for a in args):
        for target in plain_args(args)[1:]:
            if not may_write(resolve(target, here, env), skill, cwd, env):
                return f"it edits {target} in place"
        return None
    if name in PATH_CHANGERS:
        targets = plain_args(args)
        if name in ("cp", "install", "ln") and targets:
            targets = targets[-1:]
        if name in ("chmod", "chown") and targets:
            targets = targets[1:]
        for target in targets:
            if not may_write(resolve(target, here, env), skill, cwd, env):
                return f"it runs {name} on {target}"
    return None


def online_in(simple: Simple) -> str | None:
    name, args = command_name(simple[0])
    first = next((a for a in args if not a.startswith("-")), "")
    if "--online" in args or any(a.startswith("--online=") for a in args):
        return f"it runs {name} --online"
    if name in NETWORK_COMMANDS:
        return f"it runs {name}"
    if name == "git" and subcommand(args)[0] in GIT_ONLINE:
        return f"it runs git {subcommand(args)[0]}"
    if name == "terraform" and first in TERRAFORM_ONLINE:
        return f"it runs terraform {first}"
    if name in ("npm", "pnpm", "yarn") and first in ("audit", "view", "outdated"):
        return f"it runs {name} {first}"
    code = args[args.index("-c") + 1] if "-c" in args and args.index("-c") + 1 < len(args) else ""
    if name in ("python", "python3") and NETWORK_CODE.search(code):
        return "its Python code opens a network connection"
    return None


# ---------------------------------------------------------------------------- personal data


def personal_columns(path: Path) -> list[str]:
    """Columns whose names say they hold personal data, read from the first line only."""
    if path.suffix.lower() not in DATA_SUFFIXES or not path.is_file():
        return []
    import data_profile  # a copy in the same folder, in every skill that is given `personal`

    try:
        with path.open(encoding="utf-8-sig", errors="replace") as handle:
            first = handle.readline()
    except OSError:
        return []
    if path.suffix.lower() in (".jsonl", ".ndjson"):
        try:
            record = json.loads(first)
        except ValueError:
            return []
        names = [str(k) for k in record] if isinstance(record, dict) else []
    else:
        delimiter = "\t" if path.suffix.lower() == ".tsv" else max(",;\t|", key=first.count)
        names = [n.strip().strip('"') for n in first.rstrip("\r\n").split(delimiter)]
    patterns = [pattern for _, pattern in data_profile.PERSONAL_NAMES]
    return [name for name in names if any(re.search(pattern, name, re.I) for pattern in patterns)]


def header_only(name: str, args: list[str]) -> bool:
    if name == "head":
        return args[:1] in (["-1"], ["-n1"]) or args[:2] == ["-n", "1"]
    if name == "sed":
        return "-n" in args and any(a in ("1p", "1q") for a in args)
    if name in ("grep", "egrep", "fgrep", "rg"):
        return any(a in ("-c", "--count", "-l", "-L", "--files-with-matches") for a in args)
    return False


def raw_read_in(pipeline: list[Simple], env: dict[str, str]) -> str | None:
    """A pipeline that ends in a viewer printing to the screen, over a data file with personal columns."""
    last_words, _ = pipeline[-1]
    last, _ = command_name(last_words)
    if last not in VIEWERS or any(not t.startswith("/dev/") for t in redirect_targets(last_words)):
        return None
    for words, here in pipeline:
        name, args = command_name(words)
        if name not in VIEWERS or header_only(name, args):
            continue
        for word in plain_args(args):
            path = resolve(word, here, env)
            columns = personal_columns(path) if path is not None else []
            if columns:
                return f"{name} would print rows of {word}, which has personal columns ({', '.join(columns[:4])})"
    return None


def code_reads_personal(code: str, cwd: Path | None, env: dict[str, str]) -> str | None:
    """Python code that names a data file with personal columns and prints its rows."""
    if not re.search(r"print\s*\(\s*(row|rows|r|line|record|records|df)\b|\.head\(|\.sample\(|\.to_string\(", code):
        return None
    for word in re.findall(r"[\w./~${}:-]+\.(?:csv|tsv|jsonl|ndjson)\b", code):
        path = resolve(word, cwd, env)
        if path is not None and personal_columns(path):
            return f"the code prints rows of {word}, which has personal columns"
    return None


def iban_ok(value: str) -> bool:
    text = value.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", text):
        return False
    return int("".join(str(int(c, 36)) for c in text[4:] + text[:4])) % 97 == 1


def jmbg_ok(value: str) -> bool:
    """Thirteen digits with a day, a month and a valid check digit, as `data_profile.is_jmbg` checks a whole cell."""
    if not (1 <= int(value[:2]) <= 31 and 1 <= int(value[2:4]) <= 12):
        return False
    d = [int(c) for c in value]
    m = 11 - (sum((7 - i) * (d[i] + d[i + 6]) for i in range(6)) % 11)
    return (0 if m > 9 else m) == d[12]


def redact(text: str) -> tuple[str, dict[str, int]]:
    """Text with e-mail addresses, valid IBANs and valid JMBGs replaced, and how many of each."""
    found = {"e-mail": 0, "IBAN": 0, "JMBG": 0}

    def email(match: re.Match[str]) -> str:
        if match.group(1).lower() in FILE_ENDINGS:
            return match.group(0)
        found["e-mail"] += 1
        return "[e-mail removed]"

    def iban(match: re.Match[str]) -> str:
        if not iban_ok(match.group(0)):
            return match.group(0)
        found["IBAN"] += 1
        return "[IBAN removed]"

    def jmbg(match: re.Match[str]) -> str:
        if not jmbg_ok(match.group(0)):
            return match.group(0)
        found["JMBG"] += 1
        return "[JMBG removed]"

    text = EMAIL.sub(email, text)
    text = IBAN.sub(iban, text)
    text = JMBG.sub(jmbg, text)
    return text, {k: v for k, v in found.items() if v}


def counted(found: dict[str, int]) -> str:
    return ", ".join(f"{n} {kind}" for kind, n in found.items())


# ---------------------------------------------------------------------------- decisions


def decision(kind: str, reason: str) -> dict[str, Any]:
    output = {"hookEventName": "PreToolUse", "permissionDecision": kind, "permissionDecisionReason": reason}
    return {"hookSpecificOutput": output}


def pre(event: dict[str, Any], skill: str, personal: bool, env: dict[str, str]) -> dict[str, Any] | None:
    if not in_skill_turn(event, skill, record=True):
        return None
    tool = str(event.get("tool_name") or "")
    data = event.get("tool_input") or {}
    cwd = Path(str(event.get("cwd") or os.getcwd()))
    yes = f"{skill} changes nothing and stays offline until the user says yes, in their next message"
    if tool in WEB_TOOLS:
        return decision("ask", f"{yes}. Allow {tool} now?")
    if tool in EDIT_TOOLS:
        target = str(data.get("file_path") or data.get("notebook_path") or "")
        if personal:
            text = str(data.get("content") or "") + str(data.get("new_string") or "")
            for edit in data.get("edits") or []:
                text += str(edit.get("new_string") or "") if isinstance(edit, dict) else ""
            _, found = redact(text)
            if found:
                return decision(
                    "deny",
                    f"{skill} never puts personal values on a page: this {tool} would write {counted(found)}. "
                    "Use counts and column names instead.",
                )
        path = resolve(target, cwd, env) if target else None
        if not may_write(path, skill, cwd, env):
            return decision(
                "ask",
                f"{yes}. It writes only its page, under {pages_dir(env, cwd)}, and scratch files in a temp folder. "
                f"Allow {tool} on {target}?",
            )
        return None
    if tool == "Read" and personal:
        path = resolve(str(data.get("file_path") or ""), cwd, env)
        columns = personal_columns(path) if path is not None else []
        if columns:
            return decision(
                "deny",
                f"{skill} never shows rows with personal columns ({', '.join(columns[:4])}). Use the skill's scripts, "
                "which print columns and counts.",
            )
        return None
    if tool != "Bash":
        return None
    command, bodies = without_heredocs(str(data.get("command") or ""))
    words = tokens(command)
    if words is None:
        return None
    pipelines = pipelines_of(words, cwd)
    if personal:
        for pipeline in pipelines:
            why = raw_read_in(pipeline, env)
            if why:
                return decision("deny", f"{skill} never shows rows with personal columns: {why}. Use its scripts.")
            for words_here, here in pipeline:
                name, args = command_name(words_here)
                if name in ("python", "python3") and "-c" in args and args.index("-c") + 1 < len(args):
                    why = code_reads_personal(args[args.index("-c") + 1], here, env)
                    if why:
                        return decision("deny", f"{skill} never shows rows with personal columns: {why}.")
    for pipeline in pipelines:
        for simple in pipeline:
            why = online_in(simple)
            if why:
                return decision("ask", f"{yes}: {why}. Allow it now?")
    if NETWORK_CODE.search(bodies):
        return decision("ask", f"{yes}: the code in this command opens a network connection. Allow it now?")
    for pipeline in pipelines:
        for simple in pipeline:
            why = change_in(simple, skill, cwd, env)
            if why:
                return decision("ask", f"{yes}: {why}. Allow it now?")
    return None


def post(event: dict[str, Any], skill: str) -> dict[str, Any] | None:
    if not in_skill_turn(event, skill, record=False):
        return None
    tool = event.get("tool_name")
    response = event.get("tool_response")
    if not isinstance(response, dict):
        return None
    new: dict[str, Any] = json.loads(json.dumps(response))
    found: dict[str, int] = {}
    if tool == "Bash":
        for key in ("stdout", "stderr"):
            if isinstance(new.get(key), str):
                new[key], hits = redact(new[key])
                for kind, n in hits.items():
                    found[kind] = found.get(kind, 0) + n
    elif tool == "Read" and isinstance(new.get("file"), dict) and isinstance(new["file"].get("content"), str):
        new["file"]["content"], found = redact(new["file"]["content"])
    if not found:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedToolOutput": new,
            "additionalContext": (
                f"The {skill} guard removed {counted(found)} from this output. Do not try to recover them, and never "
                "put such values on the page or in the reply."
            ),
        }
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2 or args[0] not in ("pre", "post"):
        print("usage: guard.py pre|post SKILL [personal]", file=sys.stderr)
        return 1
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        event = json.loads(sys.stdin.read() or "{}")
        env = dict(os.environ)
        skill = bare(args[1])
        personal = "personal" in args[2:]
        result = pre(event, skill, personal, env) if args[0] == "pre" else post(event, skill) if personal else None
    except Exception as error:  # a guard that crashes must not block the user's work
        print(f"guard.py: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    if result is not None:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
