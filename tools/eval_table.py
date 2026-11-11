#!/usr/bin/env python3
"""Sum up the eval results `claude plugin eval` wrote under plugins/<pack>/evals/results/ into one Markdown page.

Only the graders that judge what was produced count ("outcome"); graders that check which tool or skill ran
("tool_used", "tool_order") cannot be passed by plain Claude, so they are listed separately. A run that ended
in an error says nothing and is left out. Runs made with a case filter cover part of a pack and are marked.
Standard library only; read-only.

Usage: python3 tools/eval_table.py [--root .] [-o docs/evals.md]
"""

from __future__ import annotations

import argparse
import contextlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PROCESS_GRADERS = frozenset({"tool_used", "tool_order"})


@dataclass
class Arm:
    runs: int = 0
    errors: int = 0
    outcome_passed: int = 0
    outcome_total: int = 0
    process_passed: int = 0
    process_total: int = 0
    cost: float = 0.0
    missed: list[str] = field(default_factory=list)

    @property
    def rate(self) -> float | None:
        return self.outcome_passed / self.outcome_total if self.outcome_total else None


@dataclass
class Case:
    name: str
    arms: dict[str, Arm]


@dataclass
class Run:
    pack: str
    started: str
    version: str
    ablation: str
    case_filter: str | None
    cost: float
    cases: list[Case]

    def arm(self, name: str) -> Arm:
        total = Arm()
        for case in self.cases:
            arm = case.arms.get(name)
            if arm is None:
                continue
            total.runs += arm.runs
            total.errors += arm.errors
            total.outcome_passed += arm.outcome_passed
            total.outcome_total += arm.outcome_total
            total.process_passed += arm.process_passed
            total.process_total += arm.process_total
            total.cost += arm.cost
        return total


def _arm(runs: object, grader_types: dict[str, str]) -> Arm:
    arm = Arm()
    for run in runs if isinstance(runs, list) else []:
        if not isinstance(run, dict):
            continue
        if run.get("error"):
            arm.errors += 1
            continue
        arm.runs += 1
        cost = run.get("costUsd")
        arm.cost += float(cost) if isinstance(cost, (int, float)) else 0.0
        for grader in run.get("graders") or []:
            if not isinstance(grader, dict):
                continue
            name, passed = str(grader.get("name")), bool(grader.get("passed"))
            if grader_types.get(name) in PROCESS_GRADERS:
                arm.process_total += 1
                arm.process_passed += passed
            else:
                arm.outcome_total += 1
                arm.outcome_passed += passed
                if not passed:
                    arm.missed.append(name)
    return arm


def load(path: Path) -> Run | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    suite = data.get("suite") or {}
    plugins = [p for p in suite.get("plugins") or [] if isinstance(p, dict)]
    pack = path.parents[3].name  # plugins/<pack>/evals/results/<stamp>/aggregate-result.json
    version = next((str(p.get("version")) for p in plugins if p.get("name") == pack), "?")
    started = str(data.get("startedAt", ""))
    with contextlib.suppress(ValueError):
        started = datetime.fromisoformat(started.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    cases: list[Case] = []
    for case in data.get("cases") or []:
        if not isinstance(case, dict):
            continue
        types = {str(g.get("name")): str(g.get("type")) for g in case.get("graders") or [] if isinstance(g, dict)}
        arms = {str(name): _arm(runs, types) for name, runs in (case.get("arms") or {}).items()}
        cases.append(Case(name=str(case.get("name")), arms=arms))
    cost = data.get("costUsd")
    return Run(
        pack=pack,
        started=started,
        version=version,
        ablation=str(suite.get("ablation", "none")),
        case_filter=suite.get("caseFilter"),
        cost=float(cost) if isinstance(cost, (int, float)) else 0.0,
        cases=cases,
    )


def pct(arm: Arm) -> str:
    return "—" if arm.rate is None else f"{arm.outcome_passed} / {arm.outcome_total} ({arm.rate:.0%})"


def render(runs: list[Run]) -> str:
    out = [
        "# Eval results",
        "",
        "Written by `python3 tools/eval_table.py` from `plugins/<pack>/evals/results/*/aggregate-result.json`.",
        "A case passes a grader or not; **outcome** graders judge what was produced, **process** graders only",
        "whether the skill fired (plain Claude cannot pass those, so they are not compared). Runs that ended in an",
        'error are left out. "with skill" is the plugin loaded; "plain" is the ablation arm without it, '
        "when a run had one.",
        "One run per case is a hint, not a result; the evals cost money and are run by hand.",
        "",
    ]
    by_pack: dict[str, list[Run]] = {}
    for run in runs:
        by_pack.setdefault(run.pack, []).append(run)
    out += [
        "## Latest full run per pack",
        "",
        "| Pack | Version | Run (UTC) | Cases | Outcome, with skill | Outcome, plain | Skill fired | Cost |",
        "|---|---|---|--:|---|---|---|--:|",
    ]
    latest: dict[str, Run] = {}
    for pack, pack_runs in sorted(by_pack.items()):
        full = [r for r in pack_runs if not r.case_filter] or pack_runs
        run = max(full, key=lambda r: r.started)
        latest[pack] = run
        with_arm, plain = run.arm("with"), run.arm("without")
        fired = f"{with_arm.process_passed} / {with_arm.process_total}" if with_arm.process_total else "—"
        note = "" if not run.case_filter else f" (filter: `{run.case_filter}`)"
        out.append(
            f"| {pack} | {run.version} | {run.started}{note} | {len(run.cases)} | {pct(with_arm)} | {pct(plain)} "
            f"| {fired} | ${run.cost:.2f} |"
        )
    out.append("")
    for pack, run in sorted(latest.items()):
        out += [
            f"## {pack}",
            "",
            f"Run {run.started} UTC, version {run.version}, ablation `{run.ablation}`, ${run.cost:.2f}.",
            "",
            "| Case | Outcome, with skill | Outcome, plain | Missed (with skill) |",
            "|---|---|---|---|",
        ]
        for case in run.cases:
            with_arm, plain = case.arms.get("with", Arm()), case.arms.get("without", Arm())
            missed = ", ".join(sorted(set(with_arm.missed))) or "—"
            if with_arm.errors and not with_arm.runs:
                missed = f"run ended in an error ({with_arm.errors})"
            out.append(f"| {case.name} | {pct(with_arm)} | {pct(plain)} | {missed} |")
        out.append("")
    out += [
        "## Every run",
        "",
        "| Pack | Run (UTC) | Version | Ablation | Filter | Cases | Outcome, with skill | Cost |",
        "|---|---|---|---|---|--:|---|--:|",
    ]
    for run in sorted(runs, key=lambda r: (r.pack, r.started)):
        out.append(
            f"| {run.pack} | {run.started} | {run.version} | {run.ablation} | {run.case_filter or '—'} "
            f"| {len(run.cases)} | {pct(run.arm('with'))} | ${run.cost:.2f} |"
        )
    out.append("")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="repository root")
    parser.add_argument("-o", "--output", default=None, help="write the Markdown here instead of stdout")
    args = parser.parse_args()
    root = Path(args.root)
    files = sorted(root.glob("plugins/*/evals/results/*/aggregate-result.json"))
    runs = [run for run in (load(path) for path in files) if run is not None]
    text = render(runs)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"{len(runs)} runs -> {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
