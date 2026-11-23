# Roadmap

What is built, what comes next in priority order, and what is still open. Each pack had its own plan before it was
built; the plans are kept in [roadmap/](roadmap/) for their reasoning and their open decisions, and the decisions
that shape the code are in [adr/](adr/). A plan describes the state when it was written: the code,
[reference/skills.md](reference/skills.md) and the [feature catalogue](product/features/README.md) are the current
truth.

## Goal

One pack per role whose work keeps coming back. For architecture, one specialist pack per area that answers the
same four questions for its area (what should it be, what is there now, what does it look like, what is wrong with
it), and one small pack on top that joins their work. Then processes that chain the skills, so a repeated piece of
work runs the same way every time.

## Packs

| Pack | Status | Plan |
|---|---|---|
| [software-engineering](product/features/software-engineering.md) | built: the first round, and phase 1 of the second round (change-review, docs-draft, incident-triage, postmortem, the security and performance rules of code-audit); phases 2 and 3 are plans | [engineering-pack-v2.md](roadmap/engineering-pack-v2.md), [code-audit.md](roadmap/code-audit.md) |
| [ai-architect](product/features/ai-architect.md) | built | [ai-architect.md](roadmap/ai-architect.md) |
| [data-architect](product/features/data-architect.md) | built | [data-architect.md](roadmap/data-architect.md) |
| [software-architect](product/features/software-architect.md) | built | [software-architect.md](roadmap/software-architect.md) |
| [cloud-architect](product/features/cloud-architect.md) | built for Azure and AWS; Google Cloud is a plan | [cloud-architect.md](roadmap/cloud-architect.md) |
| [solutions-architect](product/features/solutions-architect.md) | built | [solutions-architect.md](roadmap/solutions-architect.md) |
| [data-engineer](product/features/data-engineer.md) | built | [data-engineer.md](roadmap/data-engineer.md) |
| [data-analyst](product/features/data-analyst.md) | built | [data-analyst.md](roadmap/data-analyst.md) |
| [data-scientist](product/features/data-scientist.md) | built | [data-scientist.md](roadmap/data-scientist.md) |
| [workflows](product/features/workflows.md) | built as one workflow skill per process (the first of three ways in its plan); the hand-over of open items is partial (item 2 below); the other two ways are plans | [workflows.md](roadmap/workflows.md) |

The order of the architect packs, and the decisions taken early because they are expensive to change later, are in
[architect-packs.md](roadmap/architect-packs.md) and in [adr/](adr/).

## Next, in priority order

1. **The guard asks before `gh`.** Open. `change-review` takes a PR number "when `gh` is available (fetching it goes
   online, so the guard asks)", but `gh` is not in `NETWORK_COMMANDS` in `shared/guard.py`, so `gh pr diff 123` runs
   without a prompt during the skill's turn. Touches `shared/guard.py`, `tests/test_guard.py`, the sync, a patch
   version of every pack. Open: whether every `gh` call asks, or only the ones that reach the network.
2. **`facts` on the pages a workflow reads.** Partly done: `incident-triage`, `docs-draft` and `postmortem` write
   `facts`, and `change-review`'s example page has it although its `SKILL.md` does not ask for it. Still missing on
   `codebase-map`, `impact`, `bug-hunt`, `test-gap`, `dependency-audit` and `code-audit` (and `ai-review`).
   `chain_status.py` takes a step's open items only from `facts.open`, so `take-over`, `ship-change` and
   `incident-run` show none of those steps' open questions. Touches each skill's `SKILL.md` Output section and
   `references/example.json`, and the pack versions. From [roadmap/workflows.md](roadmap/workflows.md#what-the-skills-need-before-a-workflow-can-use-them).
3. **What the archetypes recommend.** Open. `render_page.py --check` warns where a page holds less than its kind
   asks: the review pages of `ai-review`, `bug-hunt`, `code-audit`, `dependency-audit`, `impact` and `test-gap` have no
   `facts.open` (the same gap as item 2), `codebase-map` has no `facts.components`, and the decision pages of
   `ai-stack`, `metric-spec`, `data-migration`, `ds-experiment` and `arch-evolve` have no `decision` block. Touches
   those skills' Output sections and examples ([ADR 0009](adr/0009-pages-declare-an-archetype-checked-against-a-schema.md)).
4. **A test that `reference/skills.md` is current.** Open. The generator lives at the end of the file and nothing
   runs it in CI; the file still said software-engineering 0.4.4 after two pull requests had moved it to 0.4.6.
   Touches `tools/` (the generator as a tool), `tests/`, [guides/development.md](guides/development.md).
5. **The selection check writes outside the repository by default.** Open. `tools/selection_check.py` defaults
   `--out` to `selection-results` in the current folder, which `.gitignore` does not list, so a run from the root
   leaves results and costs in the working tree for the next `git add`. Touches `tools/selection_check.py` or
   `.gitignore`.
6. **The `workflows` evals load their pack.** Unverified. Each case loads `workflows` and only some of the packs it
   depends on (`take-over` loads software-engineering alone), while [guides/setup.md](guides/setup.md) says Claude
   Code drops a pack whose dependencies are missing under `--plugin-dir`. Running one case settles it (it costs
   money); then document the command in [guides/testing.md](guides/testing.md). Touches
   `plugins/workflows/evals/*/case.yaml`.
7. **What the skills need for workflows, the rest.** Open: `render_page.py --latest SKILL FOLDER`; `Reads` sections
   that name the earlier pages a step takes (`solution-blueprint`, `postmortem` and the workflow skills do, the steps
   they call do not); one fixture per process with a problem only the chain finds (the `workflows` eval cases reuse
   the single-skill fixtures). Done: the cost line before a run, in all seven workflow skills.
8. **workflows, ways 2 and 3.** Plans: Claude Code `Workflow` scripts for the new solution and the take-over, and
   Mission Control missions as the "done" layer for ship-change and the incident. See
   [roadmap/workflows.md](roadmap/workflows.md#three-ways-to-run-them).
9. **software-engineering, phase 2:** an `engineering-lead` orchestrator, started only when phase 1 has run on a real
   repository. **Phase 3:** connectors, reading first and posting last. See
   [engineering-pack-v2.md](roadmap/engineering-pack-v2.md#phase-2-engineering-lead-the-orchestrator).
10. **cloud-architect, Google Cloud:** a provider is one pair of files in `shared/cloud/`; its price API needs a key.
11. **ai-engineering:** a later pack for LLM evals, error analysis, retrieval tuning and trace review, named in
    [ai-architect.md](roadmap/ai-architect.md) and [architect-packs.md](roadmap/architect-packs.md); not planned in
    detail.
12. **Small fixes.** The `cloud-architect` `plugin.json` description still ends in "Azure first" although AWS is
    built. Eleven of the fourteen shared scripts lack the "Single source ... never edit a copy" line that
    `render_page.py`, `chain_status.py` and `ai_inventory.py` carry. `pyproject.toml` leaves
    `plugins/workflows/skills` out of mypy (it holds only shared copies today). The copy command in
    [guides/setup.md](guides/setup.md) leaves out the workflow skills, and whether they are meant to be copied is not
    stated.

**Versions and release channels:** a proposal for pack versions people can pull, a stable channel and a regression
gate, not agreed and not built.

## Open decisions

Each plan lists its own at the end. The ones that shape what comes next:

- [engineering-pack-v2.md](roadmap/engineering-pack-v2.md#open-decisions): whether the orchestrator is a separate pack
  or routing lines in each SKILL.md are enough. Its other open decisions were settled by what was built: the four
  names, two incident skills, `audit_scan.py` in `shared/`.
- [workflows.md](roadmap/workflows.md#open-questions): where the workflow definitions live, who says "done", and
  whether a workflow may change code.
