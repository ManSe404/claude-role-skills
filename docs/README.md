# Documentation

claude-role-skills is a Claude Code marketplace of skill packs by role, each skill counting with its own scripts and
ending in one self-contained page. Read in this order:

| # | Document | What it answers | Status | Last checked |
|---|---|---|---|---|
| 1 | [product/vision.md](product/vision.md) | why the skills exist, for whom, what they are not | current | 2026-11-11 |
| 2 | [product/features/software-engineering.md](product/features/software-engineering.md) | what each software-engineering skill is for and writes | current | 2026-11-11 |
| 3 | [product/features/ai-architect.md](product/features/ai-architect.md) | the same for the ai-architect pack | current | 2026-11-11 |
| 4 | [product/features/data-architect.md](product/features/data-architect.md) | the same for the data-architect pack | current | 2026-11-11 |
| 5 | [product/features/data-engineer.md](product/features/data-engineer.md) | the same for the data-engineer pack | current | 2026-11-11 |
| 6 | [product/features/data-analyst.md](product/features/data-analyst.md) | the same for the data-analyst pack | current | 2026-11-11 |
| 7 | [product/features/data-scientist.md](product/features/data-scientist.md) | the same for the data-scientist pack | current | 2026-11-11 |
| 8 | [product/features/software-architect.md](product/features/software-architect.md) | the same for the software-architect pack | current | 2026-11-11 |
| 9 | [product/features/cloud-architect.md](product/features/cloud-architect.md) | the same for the cloud-architect pack | current | 2026-11-11 |
| 10 | [product/features/solutions-architect.md](product/features/solutions-architect.md) | the same for the solutions-architect pack | current | 2026-11-11 |
| 11 | [product/features/workflows.md](product/features/workflows.md) | the process chains and the skills each one runs | current | 2026-11-11 |
| 12 | [guides/setup.md](guides/setup.md) | how to install the packs or copy the skills, and where pages go | current | 2026-11-11 |
| 13 | [roadmap.md](roadmap.md) | what is built, what is planned, what is open | current | 2026-11-11 |
| 14 | [architecture/overview.md](architecture/overview.md) | how packs, skills, shared files, the renderer, the guard and the evals fit together | current | 2026-11-11 |
| 15 | [diagrams/container.md](diagrams/container.md) | the parts of the repository and how they connect | current | 2026-11-11 |
| 16 | [diagrams/skill-run.md](diagrams/skill-run.md) | a skill run from the request to the page | current | 2026-11-11 |
| 17 | [diagrams/workflow-chain.md](diagrams/workflow-chain.md) | how a workflow runs its steps | current | 2026-11-11 |
| 18 | [architecture/crosscutting.md](architecture/crosscutting.md) | the guard hook, paths, errors, untrusted text | current | 2026-11-11 |
| 19 | [design/page-design.md](design/page-design.md) | the look of every page and what the reader can do on it | current | 2026-11-11 |
| 20 | [reference/codebase.md](reference/codebase.md) | what is where in the repository | current | 2026-11-11 |
| 21 | [reference/skills.md](reference/skills.md) | every pack and skill, generated from the manifests and the SKILL.md files | current | 2026-11-11 |
| 22 | [guides/development.md](guides/development.md) | the checks, shared files, adding a skill, a provider or a fixture | current | 2026-11-11 |
| 23 | [guides/testing.md](guides/testing.md) | unit tests, evals and the selection check | current | 2026-11-11 |

The page JSON format every skill writes is [shared/page-format.md](../shared/page-format.md), and the rules for agents
working in the repository are in [CLAUDE.md](../CLAUDE.md).

## Plans

The plan behind each step, kept for its reasoning and its open decisions. Each describes the state when it was
written; the documents above are the current truth.

| # | Document | What it planned | Status | Last checked |
|---|---|---|---|---|
| 24 | [roadmap/architect-packs.md](roadmap/architect-packs.md) | the series of architect packs and the decisions taken early | plan, built | 2026-11-11 |
| 25 | [roadmap/ai-architect.md](roadmap/ai-architect.md) | the ai-architect pack | plan, built | 2026-11-11 |
| 26 | [roadmap/data-architect.md](roadmap/data-architect.md) | the data-architect pack and the `facts` format | plan, built | 2026-11-11 |
| 27 | [roadmap/software-architect.md](roadmap/software-architect.md) | the software-architect pack | plan, built | 2026-11-11 |
| 28 | [roadmap/cloud-architect.md](roadmap/cloud-architect.md) | the cloud-architect pack, Azure and AWS | plan, built except Google Cloud | 2026-11-11 |
| 29 | [roadmap/solutions-architect.md](roadmap/solutions-architect.md) | the solutions-architect pack | plan, built | 2026-11-11 |
| 30 | [roadmap/code-audit.md](roadmap/code-audit.md) | code-audit, and arch-review as a design review only | plan, built | 2026-11-11 |
| 31 | [roadmap/engineering-pack-v2.md](roadmap/engineering-pack-v2.md) | the second round of software-engineering | plan, phase 1 built, phases 2 and 3 not | 2026-11-11 |
| 32 | [roadmap/data-engineer.md](roadmap/data-engineer.md) | the data-engineer pack | plan, built | 2026-11-11 |
| 33 | [roadmap/data-analyst.md](roadmap/data-analyst.md) | the data-analyst pack | plan, built | 2026-11-11 |
| 34 | [roadmap/data-scientist.md](roadmap/data-scientist.md) | the data-scientist pack | plan, built | 2026-11-11 |
| 35 | [roadmap/workflows.md](roadmap/workflows.md) | process workflows over the skills, three ways to run them | plan, first way built | 2026-11-11 |

## Open decisions

- **[evals.md](evals.md)** holds eval results (pass rates and costs per pack and case), written by
  `tools/eval_table.py`. Results belong outside the repository by the documentation rule, but the file is public and
  linked from the testing guide; whether it stays, moves out, or `eval_table.py` writes elsewhere is the owner's
  call. Status: open decision.
- **Versions and release channels:** the design is proposed, not agreed, and not in the repository. Once agreed it goes
  to `roadmap/` with the other plans and gets a row in this index.
- **[reference/skills.md](reference/skills.md)** is regenerated by a script kept at the end of the file itself. If the
  owner prefers, the script can become a tool in `tools/` with a test that the file is up to date.

## Layout

`product/` holds why and what, `roadmap.md` and `roadmap/` what is built and planned, `design/` the look of the pages,
`architecture/` how it is built, `diagrams/` the Mermaid drawings, `reference/` what exists, checkable against the
code, and `guides/` how to set up, develop and test. A change updates the documents it makes wrong in the same commit.
