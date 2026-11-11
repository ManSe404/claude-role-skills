# Roadmap

What is built, what is planned and what is still open. Each step had its own plan before it was built; the plans
are kept in [roadmap/](roadmap/) for their reasoning and their open decisions. A plan describes the state when it was
written: the code and [reference/skills.md](reference/skills.md) are the current truth, and each pack's
[feature page](product/features/) says what it does today.

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
| [workflows](product/features/workflows.md) | built as one workflow skill per process (the first of three ways in its plan); the other two ways are plans | [workflows.md](roadmap/workflows.md) |

The order of the architect packs, and the decisions taken early because they are expensive to change later (the
`facts` section on every page, descriptions that name their subject, the guard hooks), are in
[architect-packs.md](roadmap/architect-packs.md).

## Planned, not built

- **software-engineering, phase 2:** an `engineering-lead` orchestrator; it starts only when phase 1 has run on a real
  repository. **Phase 3:** connectors, reading first and posting last. See
  [engineering-pack-v2.md](roadmap/engineering-pack-v2.md#phase-2-engineering-lead-the-orchestrator).
- **workflows, ways 2 and 3:** Claude Code `Workflow` scripts for the new solution and the take-over, and Mission
  Control missions as the "done" layer for ship-change and the incident; and the list of what the skills need before
  a workflow can use them. See [workflows.md](roadmap/workflows.md#three-ways-to-run-them).
- **cloud-architect, Google Cloud:** a provider is one pair of files in `shared/cloud/`.
- **ai-engineering:** a later pack for LLM evals, error analysis, retrieval tuning and trace review, named in
  [ai-architect.md](roadmap/ai-architect.md) and [architect-packs.md](roadmap/architect-packs.md); not planned in
  detail.
- **Versions and release channels:** a proposal for pack versions people can pull, a stable channel and a regression
  gate, not agreed and not built.

## Open decisions

Each plan lists its own at the end. The ones that shape what comes next:

- [engineering-pack-v2.md](roadmap/engineering-pack-v2.md#open-decisions): among them, whether the orchestrator is a
  separate pack or routing lines in each SKILL.md are enough.
- [workflows.md](roadmap/workflows.md#open-questions): where the workflow definitions live, who says "done", and
  whether a workflow may change code.
