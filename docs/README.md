# Documentation

claude-role-skills is a Claude Code marketplace of skill packs by role, each skill counting with its own scripts and
ending in one self-contained page. Read in this order:

| # | Document | What it answers | Status | Last checked |
|---|---|---|---|---|
| 1 | [product/vision.md](product/vision.md) | the problem the skills solve and how, why this way, for whom, what they are not, how we know they work | current | 2026-11-16 |
| 2 | [product/features/README.md](product/features/README.md) | the feature catalogue: every pack, what every skill shares, the tools, with status and where each lives in the code | current | 2026-11-16 |
| 3 | [product/features/software-engineering.md](product/features/software-engineering.md) | what each software-engineering skill is for and writes | current | 2026-11-16 |
| 4 | [product/features/ai-architect.md](product/features/ai-architect.md) | the same for the ai-architect pack | current | 2026-11-16 |
| 5 | [product/features/data-architect.md](product/features/data-architect.md) | the same for the data-architect pack | current | 2026-11-16 |
| 6 | [product/features/data-engineer.md](product/features/data-engineer.md) | the same for the data-engineer pack | current | 2026-11-16 |
| 7 | [product/features/data-analyst.md](product/features/data-analyst.md) | the same for the data-analyst pack | current | 2026-11-16 |
| 8 | [product/features/data-scientist.md](product/features/data-scientist.md) | the same for the data-scientist pack | current | 2026-11-16 |
| 9 | [product/features/software-architect.md](product/features/software-architect.md) | the same for the software-architect pack | current | 2026-11-16 |
| 10 | [product/features/cloud-architect.md](product/features/cloud-architect.md) | the same for the cloud-architect pack | current | 2026-11-16 |
| 11 | [product/features/solutions-architect.md](product/features/solutions-architect.md) | the same for the solutions-architect pack | current | 2026-11-16 |
| 12 | [product/features/workflows.md](product/features/workflows.md) | the process chains and the skills each one runs | current | 2026-11-16 |
| 13 | [guides/setup.md](guides/setup.md) | how to install the packs or copy the skills, and where pages go | current | 2026-11-16 |
| 14 | [roadmap.md](roadmap.md) | the status of each pack, what comes next in priority order, the open decisions | current | 2026-11-16 |
| 15 | [architecture/overview.md](architecture/overview.md) | how packs, skills, shared files, the renderer, the guard and the evals fit together | current | 2026-11-16 |
| 16 | [diagrams/context.md](diagrams/context.md) | who uses the skills, what they run in and what they reach | current | 2026-11-16 |
| 17 | [diagrams/container.md](diagrams/container.md) | the parts of the repository and how they connect | current | 2026-11-16 |
| 18 | [diagrams/skill-run.md](diagrams/skill-run.md) | a skill run from the request to the page | current | 2026-11-16 |
| 19 | [diagrams/workflow-chain.md](diagrams/workflow-chain.md) | how a workflow runs its steps | current | 2026-11-16 |
| 20 | [architecture/crosscutting.md](architecture/crosscutting.md) | the guard hook, paths, errors, untrusted text | current | 2026-11-16 |
| 21 | [design/page-design.md](design/page-design.md) | the look of every page and what the reader can do on it | current | 2026-11-16 |
| 22 | [reference/codebase.md](reference/codebase.md) | what is where in the repository | current | 2026-11-16 |
| 23 | [reference/skills.md](reference/skills.md) | every pack and skill, generated from the manifests and the SKILL.md files | current, regenerated | 2026-11-16 |
| 24 | [guides/development.md](guides/development.md) | the checks, shared files, adding a skill, a provider or a fixture | current | 2026-11-16 |
| 25 | [guides/testing.md](guides/testing.md) | unit tests, evals and the selection check | current | 2026-11-16 |

The page JSON format every skill writes is [shared/page-format.md](../shared/page-format.md), and the rules for agents
working in the repository are in [CLAUDE.md](../CLAUDE.md).

## Decisions

One decision per record, in the Nygard form, written down from the plans that record their reasons. A record is not
edited once accepted; a new one supersedes it.

| # | Decision | Status | Last checked |
|---|---|---|---|
| 26 | [0001 Scripts count, Claude reads and tags](adr/0001-scripts-count-claude-reads-and-tags.md) | accepted | 2026-11-16 |
| 27 | [0002 Shared files are copied into each skill](adr/0002-shared-files-are-copied-into-each-skill.md) | accepted | 2026-11-16 |
| 28 | [0003 A `facts` section on every page](adr/0003-a-facts-section-on-every-page.md) | accepted | 2026-11-16 |
| 29 | [0004 A guard hook enforces the Never rules](adr/0004-a-guard-hook-enforces-the-never-rules.md) | accepted | 2026-11-16 |
| 30 | [0005 code-audit reviews code, arch-review reviews designs](adr/0005-code-audit-reviews-code-arch-review-reviews-designs.md) | accepted | 2026-11-16 |
| 31 | [0006 One cloud pack, with a pair of files per provider](adr/0006-one-cloud-pack-with-a-pair-of-files-per-provider.md) | accepted | 2026-11-16 |
| 32 | [0007 Deciding skills rule options out and never choose](adr/0007-deciding-skills-rule-options-out-and-never-choose.md) | accepted | 2026-11-16 |
| 33 | [0008 Descriptions name their subject, checked with every pack loaded](adr/0008-descriptions-name-their-subject.md) | accepted | 2026-11-16 |
| 34 | [0009 Pages declare an archetype, checked against a schema](adr/0009-pages-declare-an-archetype-checked-against-a-schema.md) | accepted | 2026-11-23 |

## Plans

The plan behind each step, kept for its reasoning and its open decisions. Each describes the state when it was
written; the documents above are the current truth, and what is still to do is in [roadmap.md](roadmap.md).

| # | Document | What it planned | Status | Last checked |
|---|---|---|---|---|
| 34 | [roadmap/architect-packs.md](roadmap/architect-packs.md) | the series of architect packs and the decisions taken early | plan, built | 2026-11-16 |
| 35 | [roadmap/ai-architect.md](roadmap/ai-architect.md) | the ai-architect pack | plan, built | 2026-11-16 |
| 36 | [roadmap/data-architect.md](roadmap/data-architect.md) | the data-architect pack and the `facts` format | plan, built | 2026-11-16 |
| 37 | [roadmap/software-architect.md](roadmap/software-architect.md) | the software-architect pack | plan, built | 2026-11-16 |
| 38 | [roadmap/cloud-architect.md](roadmap/cloud-architect.md) | the cloud-architect pack, Azure and AWS | plan, built except Google Cloud | 2026-11-16 |
| 39 | [roadmap/solutions-architect.md](roadmap/solutions-architect.md) | the solutions-architect pack | plan, built | 2026-11-16 |
| 40 | [roadmap/code-audit.md](roadmap/code-audit.md) | code-audit, and arch-review as a design review only | plan, built; its routing of pull requests predates change-review | 2026-11-16 |
| 41 | [roadmap/engineering-pack-v2.md](roadmap/engineering-pack-v2.md) | the second round of software-engineering | plan, phase 1 built, phases 2 and 3 not | 2026-11-16 |
| 42 | [roadmap/data-engineer.md](roadmap/data-engineer.md) | the data-engineer pack | plan, built | 2026-11-16 |
| 43 | [roadmap/data-analyst.md](roadmap/data-analyst.md) | the data-analyst pack | plan, built | 2026-11-16 |
| 44 | [roadmap/data-scientist.md](roadmap/data-scientist.md) | the data-scientist pack | plan, built | 2026-11-16 |
| 45 | [roadmap/workflows.md](roadmap/workflows.md) | process workflows over the skills, three ways to run them | plan, first way built; the rest is in roadmap.md | 2026-11-16 |

## Open decisions

- **Versions and release channels:** the design is proposed, not agreed, and not in the repository. Once agreed it goes
  to `roadmap/` with the other plans and gets a row in this index.
- **[reference/skills.md](reference/skills.md)** is regenerated by a script kept at the end of the file itself, and
  nothing checks that it is current. The script can become a tool in `tools/` with a test
  ([roadmap.md](roadmap.md#next-in-priority-order), item 4).
- **The plans in `roadmap/`:** eleven of the twelve describe packs that are built, so the folder is a record of how
  each pack was planned rather than a roadmap. The decisions in them whose reasons are recorded are now in `adr/`;
  whether the built plans stay in `roadmap/`, move to a folder named for what they are, or leave the repository is the
  owner's call.

## Layout

`product/` holds why and what (`product/features/README.md` is the catalogue), `roadmap.md` what comes next and
`roadmap/` the plan behind each pack, `adr/` the decisions, `design/` the look of the pages, `architecture/` how it is
built, `diagrams/` the Mermaid drawings, `reference/` what exists, checkable against the code, and `guides/` how to set
up, develop and test. Eval and selection-check results are not kept in the repository. A change updates the documents
it makes wrong in the same commit.
