#!/usr/bin/env python3
"""Which skill does Claude pick when every pack is loaded at once?

Usage: uv run python tools/selection_check.py [--out DIR] [--budget USD] [-j N] [--model MODEL] [--only TEXT] [--runs N]

`claude plugin eval` loads one plugin at a time, so its skill-fired grader only chooses among that pack's own skills.
This loads every pack, gives Claude one prompt from tools/selection_cases.json, and offers it no tool but Skill for one
turn, so each case is one model call: the first decision and nothing after it. `expect` lists the skills that are a
right answer; an empty list means none of ours should fire, and a skill from elsewhere is then still a pass.

Offering only Skill pushes Claude towards a skill, so `--all-tools` offers its ordinary tools as well. Then a first call
to Read or Grep is counted as `looked_first`: the case neither picked a skill nor refused one, and it fails only if a
skill was expected, because one turn cannot show what it would have done next.

Real calls, real money: the run stops when --budget is reached. Results go to --out; nothing in the repository changes.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "tools" / "selection_cases.json"
TIMEOUT_SECONDS = 180
PER_CASE_BUDGET_USD = "1"


@dataclass
class Outcome:
    case: str
    run: int
    expect: list[str]
    picked: str | None = None
    cost: float = 0.0
    model: str | None = None
    skills_listed: int | None = None
    first_tool: str | None = None
    text: str = ""
    error: str | None = None
    passed: bool = field(default=False)


def our_skills() -> set[str]:
    return {p.parent.name for p in ROOT.glob("plugins/*/skills/*/SKILL.md")}


def bare_name(skill: str) -> str:
    """`data-scientist:ds-explore` and `ds-explore` are the same skill."""
    return skill.rsplit(":", 1)[-1]


def parse_stream(lines: list[str]) -> dict[str, Any]:
    """The first Skill call of a stream-json transcript, its cost, its model and how many skills it could see."""
    found: dict[str, Any] = {
        "picked": None,
        "first_tool": None,
        "cost": 0.0,
        "model": None,
        "skills_listed": None,
        "text": "",
    }
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            found["model"] = event.get("model")
            found["skills_listed"] = len(event.get("skills", []))
        elif kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text" and not found["text"]:
                    found["text"] = str(block.get("text", ""))[:200]
                if block.get("type") != "tool_use":
                    continue
                if found["first_tool"] is None:
                    found["first_tool"] = block.get("name")
                if block.get("name") == "Skill" and found["picked"] is None:
                    found["picked"] = bare_name(str(block.get("input", {}).get("skill", "")))
        elif kind == "result":
            found["cost"] = float(event.get("total_cost_usd") or 0.0)
    return found


def judge(picked: str | None, expect: list[str], ours: set[str]) -> bool:
    """A case with expected skills needs one of them; a case with none passes unless one of our skills fired."""
    if expect:
        return picked in expect
    return picked is None or picked not in ours


def run_case(
    case: dict[str, Any], run: int, plugins: list[Path], model: str | None, ours: set[str], all_tools: bool
) -> Outcome:
    outcome = Outcome(case["id"], run, case["expect"])
    command = ["claude", "-p", case["prompt"], "--output-format", "stream-json", "--verbose"]
    command += ["--tools", "default" if all_tools else "Skill", "--allowedTools", "Skill", "--max-turns", "1"]
    command += ["--max-budget-usd", PER_CASE_BUDGET_USD, "--no-session-persistence", "--strict-mcp-config"]
    for plugin in plugins:
        command += ["--plugin-dir", str(plugin)]
    if model:
        command += ["--model", model]
    with tempfile.TemporaryDirectory(prefix="selection-") as empty:
        try:
            done = subprocess.run(
                command, cwd=empty, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=TIMEOUT_SECONDS
            )
        except subprocess.TimeoutExpired:
            outcome.error = f"timed out after {TIMEOUT_SECONDS}s"
            return outcome
    found = parse_stream(done.stdout.splitlines())
    outcome.picked, outcome.cost, outcome.model = found["picked"], found["cost"], found["model"]
    outcome.skills_listed, outcome.text = found["skills_listed"], found["text"]
    outcome.first_tool = found["first_tool"]
    if found["model"] is None:
        outcome.error = (done.stderr or done.stdout)[-300:]
        return outcome
    outcome.passed = judge(outcome.picked, outcome.expect, ours)
    return outcome


def summarise(outcomes: list[Outcome]) -> dict[str, Any]:
    finished = [o for o in outcomes if o.error is None]
    should_fire = [o for o in finished if o.expect]
    should_not = [o for o in finished if not o.expect]
    wrong_skill = [o for o in should_fire if not o.passed and o.picked is not None]
    silent = [o for o in should_fire if o.picked is None]
    return {
        "cases_run": len(outcomes),
        "errors": len(outcomes) - len(finished),
        "passed": sum(o.passed for o in finished),
        "should_fire": len(should_fire),
        "should_fire_passed": sum(o.passed for o in should_fire),
        "should_not_fire": len(should_not),
        "should_not_fire_passed": sum(o.passed for o in should_not),
        "wrong_skill": len(wrong_skill),
        "no_skill_when_one_was_expected": len(silent),
        "looked_first": sum(1 for o in finished if o.first_tool not in (None, "Skill")),
        "cost_usd": round(sum(o.cost for o in outcomes), 4),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("selection-results"))
    parser.add_argument("--budget", type=float, default=25.0)
    parser.add_argument("-j", "--concurrency", type=int, default=4)
    parser.add_argument("--model")
    parser.add_argument("--only", help="run only the cases whose id contains this text")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--all-tools", action="store_true", help="offer Claude's ordinary tools, not only Skill")
    args = parser.parse_args(argv)
    cases: list[dict[str, Any]] = json.loads(CASES.read_text("utf-8"))
    if args.only:
        cases = [c for c in cases if args.only in c["id"]]
    plugins = sorted(p for p in (ROOT / "plugins").iterdir() if (p / ".claude-plugin" / "plugin.json").is_file())
    ours = our_skills()
    jobs = [(case, run) for case in cases for run in range(1, args.runs + 1)]
    outcomes: list[Outcome] = []
    spent = 0.0
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        pending = iter(jobs)
        running = set()
        for _ in range(args.concurrency):
            job = next(pending, None)
            if job is not None:
                running.add(pool.submit(run_case, job[0], job[1], plugins, args.model, ours, args.all_tools))
        while running:
            done_now = next(as_completed(running))
            running.remove(done_now)
            outcome = done_now.result()
            outcomes.append(outcome)
            spent += outcome.cost
            mark = "ok  " if outcome.passed else ("ERR " if outcome.error else "MISS")
            print(f"{mark} {outcome.case:26} picked={outcome.picked}  first={outcome.first_tool}", flush=True)
            if spent < args.budget:
                job = next(pending, None)
                if job is not None:
                    running.add(pool.submit(run_case, job[0], job[1], plugins, args.model, ours, args.all_tools))
            else:
                print(f"budget of {args.budget} reached, stopping", flush=True)
    order = {c["id"]: i for i, c in enumerate(cases)}
    outcomes.sort(key=lambda o: (order[o.case], o.run))
    summary = summarise(outcomes)
    summary["seconds"] = round(time.monotonic() - started)
    summary["model"] = next((o.model for o in outcomes if o.model), None)
    summary["skills_listed"] = next((o.skills_listed for o in outcomes if o.skills_listed), None)
    summary["our_skills"] = len(ours)
    args.out.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "outcomes": [o.__dict__ for o in outcomes]}
    (args.out / "selection.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False), "utf-8")
    json.dump(summary, sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
