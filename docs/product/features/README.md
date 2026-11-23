# Feature catalogue

Everything the repository offers, in one table: the ten packs and their skills, what every skill shares, what a
project that uses the skills gets, and the tools for working on the repository. Each pack's page says what each of
its skills is for and writes; this page does not repeat it.

| Feature | What you can do | Status | Where in code | Doc |
|---|---|---|---|---|
| **Packs** | | | | |
| software-engineering | map an unknown repository, find what a change reaches, trace a failure to its cause, pick the tests to write first, audit dependencies and code, review a change, draft documents from the code, triage an incident and write the postmortem (codebase-map, impact, bug-hunt, test-gap, dependency-audit, code-audit, change-review, docs-draft, incident-triage, postmortem) | shipped; an orchestrator and connectors are planned | `plugins/software-engineering/` | [software-engineering.md](software-engineering.md) |
| ai-architect | decide what an AI solution should be, pick and price its stack, draw it as an interactive page, review one that exists (ai-pattern, ai-stack, ai-architecture, ai-review) | shipped | `plugins/ai-architect/` | [ai-architect.md](ai-architect.md) |
| data-architect | decide and size a data platform, model a subject area, map what exists from its code, review it (data-platform, data-model, data-map, data-review) | shipped | `plugins/data-architect/` | [data-architect.md](data-architect.md) |
| data-engineer | profile a new source, write or check its contract, trace a failed run, summarise the checks, break down the cost, plan a migration, write a served table's consumer guide (source-profile, source-contract, pipeline-incident, data-quality, data-cost, data-migration, data-product) | shipped | `plugins/data-engineer/` | [data-engineer.md](data-engineer.md) |
| software-architect | decide a system's shape, draw it in C4, review a design before it is built, plan the way to a target in safe steps (arch-style, arch-c4, arch-review, arch-evolve) | shipped | `plugins/software-architect/` | [software-architect.md](software-architect.md) |
| cloud-architect | draw cloud infrastructure from its code, compare a design across options or clouds with list prices, review it against the provider's Well-Architected pillars (cloud-map, cloud-design, cloud-review) | shipped for Azure and AWS; Google Cloud is planned | `plugins/cloud-architect/`, `shared/cloud/` | [cloud-architect.md](cloud-architect.md) |
| solutions-architect | frame a brief that spans several areas and say which specialist skills to run, in which order, with shared facts, then join their pages into one solution with every conflict named (solution-brief, solution-blueprint); installs the four specialist packs | shipped | `plugins/solutions-architect/` | [solutions-architect.md](solutions-architect.md) |
| data-analyst | write the one definition of a metric, explain why a number moved, account for the gap between two numbers, check a report's counting (metric-spec, number-moved, number-reconcile, report-review) | shipped | `plugins/data-analyst/` | [data-analyst.md](data-analyst.md) |
| data-scientist | decide whether a model is worth building, explore a target, audit a training set for leakage, compare models so noise is called noise, size or read an A/B test (ds-frame, ds-explore, ds-dataset, ds-evaluate, ds-experiment) | shipped | `plugins/data-scientist/` | [data-scientist.md](data-scientist.md) |
| workflows | run a process as one chain of the skills above, resuming where it stopped and ending in one page (take-over, ship-change, incident-run, data-incident, new-solution, platform-month, model-build); installs every other pack | partial: the chains run, but the open items of six steps do not reach the chain page (see below) | `plugins/workflows/`, `shared/chain_status.py` | [workflows.md](workflows.md) |
| **What every skill shares** | | | | |
| The page | get one self-contained HTML page per run, with its JSON beside it; a text-only skill writes a Markdown note first (`--md`); refresh an index of a pages folder (`--index`); write a set of pages with one header (`--site`); validate a page without writing it (`--check`), against a JSON Schema and the page's archetype (`decision`, `map`, `review`, `incident`, `chain`, `report`) | shipped | `shared/render_page.py`, copied into every skill | [page-format.md](../../../shared/page-format.md), [design/page-design.md](../../design/page-design.md), [ADR 0009](../../adr/0009-pages-declare-an-archetype-checked-against-a-schema.md) |
| The guard | have Claude Code ask before a skill changes anything or goes online, and keep personal data out of what the data skills read and write, during the turn that invoked the skill | shipped | `shared/guard.py`, the `hooks:` block of every `SKILL.md` | [architecture/crosscutting.md](../../architecture/crosscutting.md) |
| Pages that join | let a later skill read an earlier page's `facts` instead of its prose: `solution-blueprint` joins the specialists' pages, a workflow step reads the previous step's | partial: seven skills write no `facts` yet | `facts` in each skill's page JSON, `plugins/solutions-architect/skills/solution-blueprint/scripts/join_facts.py`, `shared/chain_status.py` | [architecture/overview.md](../../architecture/overview.md#the-page-and-its-json) |
| **For a project that uses the skills** | | | | |
| Install | install one pack, or all of them through `workflows`, from the marketplace; or copy the skills into one project | shipped | `.claude-plugin/marketplace.json`, `plugins/*/.claude-plugin/plugin.json` | [guides/setup.md](../../guides/setup.md) |
| Role starters | copy a CLAUDE.md starter that sets how Claude works with one role's skills (nine roles; none for `workflows`) | shipped | `roles/` | [guides/setup.md](../../guides/setup.md#a-claudemd-for-your-project) |
| **For working on the repository** | | | | |
| Shared-file sync | edit a shared script once and copy it into every skill that names it; `--check` fails CI when a copy differs | shipped | `tools/sync_shared.py` | [guides/development.md](../../guides/development.md#changing-a-shared-file) |
| Fixtures | build one of twelve made-up projects with planted problems, and its git history, into an empty folder | shipped | `fixtures/build_fixture.py`, `fixtures/acme-*/` | [reference/codebase.md](../../reference/codebase.md#fixtures) |
| Eval cases | run a pack's cases with `claude plugin eval` on a built fixture (64 cases, at least one per skill; they cost money) | shipped; no documented command for the `workflows` cases | `plugins/*/evals/` | [guides/testing.md](../../guides/testing.md#evals) |
| Eval summary | sum up the results of an eval run into one Markdown table, pack by pack and case by case | shipped | `tools/eval_table.py` | [guides/testing.md](../../guides/testing.md#summing-up-the-results) |
| Selection check | load every pack at once and see which skill Claude picks for each of the prompts in `tools/selection_cases.json` (real model calls) | shipped | `tools/selection_check.py` | [guides/testing.md](../../guides/testing.md#selection-check) |
| Skills reference | regenerate the list of every pack and skill from the manifests and the `SKILL.md` files | shipped; nothing checks that the file is current | the script at the end of `docs/reference/skills.md` | [reference/skills.md](../../reference/skills.md) |
| **Planned** | | | | |
| Google Cloud | the cloud skills on a third provider: one `shared/cloud/` pair of files | planned | | [roadmap.md](../../roadmap.md) |
| Workflows, ways 2 and 3 | the same chains as Claude Code `Workflow` scripts, and Mission Control missions as the "done" layer | planned | | [roadmap/workflows.md](../../roadmap/workflows.md#three-ways-to-run-them) |
| engineering-lead, connectors | an orchestrator over software-engineering, then connectors that read first and post last | planned | | [roadmap/engineering-pack-v2.md](../../roadmap/engineering-pack-v2.md#phase-2-engineering-lead-the-orchestrator) |
| ai-engineering | a pack for LLM evals, error analysis, retrieval tuning and trace review | planned, not in detail | | [roadmap.md](../../roadmap.md) |

## Packs

Each pack is one Claude Code plugin with its own manifest and version, installed as `PACK@claude-role-skills` and
called as `/PACK:SKILL`. Every skill in it has a `SKILL.md` in the fixed sections, its own scripts or copies of the
shared ones, an example page made by running it on a fixture, at least one eval case and tests for its scripts. Each
pack's page lists what each skill is for and what it writes; the scripts and the guard of every skill are in
[reference/skills.md](../../reference/skills.md). `solutions-architect` and `workflows` declare `dependencies`, so
installing them installs the packs they build on.

`workflows` is partial because of the hand-over. `chain_status.py` takes a step's open items only from its page's
`facts.open`, and `codebase-map`, `impact`, `bug-hunt`, `test-gap`, `dependency-audit` and `code-audit` write no
`facts`. So the "still open" list of `take-over`, `ship-change` and `incident-run` holds those steps' open high
findings but none of their open questions. Adding `facts` to those skills is on the [roadmap](../../roadmap.md).

## What every skill shares

The renderer, the page format, the fonts and the guard are copied into every skill, because an installed plugin has
nothing outside its own folder. A page is JSON that `render_page.py` validates and draws, so every page has the same
layout and fetches nothing. Every skill names its page's archetype in SKILL.md (17 review, 11 decision, 8 map,
7 chain, 4 report, 3 incident; the list is in [reference/skills.md](../../reference/skills.md)) and runs
`render_page.py --check` before the page is done, so pages of one kind have the same structure. The guard runs as a hook only while the skill's turn lasts and steps aside after the
person's next message. `facts` is the part of a page meant for other skills rather than for people; `ai-review` is
the seventh skill without it.

## For a project that uses the skills

The packs install from this repository as a marketplace. `roles/` holds one CLAUDE.md starter per role, to copy into a
project and adapt; `workflows` has none, because its skills only chain the others.

## For working on the repository

Shared scripts live in `shared/` and reach the skills only through `tools/sync_shared.py`. The fixtures back the
scripts' tests, the example pages and the evals. The evals and the selection check start real Claude sessions and are
run by hand; their results are kept outside the repository.
