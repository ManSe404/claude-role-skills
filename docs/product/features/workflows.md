# Workflows

Process chains over the skills of the other packs. Each step is one of those skills, each step reads the previous step's page, and the chain ends in one page that says what was found and whether the chain is done. Install it as `workflows@claude-role-skills`; the skills are called as `/workflows:<skill>`.

| Workflow | Use it when | It runs, in order |
|---|---|---|
| [take-over](../../../plugins/workflows/skills/take-over/SKILL.md) | a repository arrives that the team must own | codebase-map, code-audit, dependency-audit, test-gap, docs-draft |
| [ship-change](../../../plugins/workflows/skills/ship-change/SKILL.md) | a branch is ready to be checked, fixed and documented | impact, change-review, bug-hunt when a test fails, docs-draft |
| [incident-run](../../../plugins/workflows/skills/incident-run/SKILL.md) | an alert fires and the team wants triage, cause, fix and write-up | incident-triage, bug-hunt, change-review, postmortem |
| [data-incident](../../../plugins/workflows/skills/data-incident/SKILL.md) | a scheduled load failed | pipeline-incident, source-contract when the source changed, data-quality after the rerun |
| [new-solution](../../../plugins/workflows/skills/new-solution/SKILL.md) | a brief spans several areas and must end in one reviewed solution | solution-brief, the specialists it names, solution-blueprint, the reviews |
| [platform-month](../../../plugins/workflows/skills/platform-month/SKILL.md) | a month closes on a data platform | data-quality, data-cost, data-product |
| [model-build](../../../plugins/workflows/skills/model-build/SKILL.md) | someone asks for a prediction | ds-frame, ds-explore, ds-dataset, ds-evaluate, ds-experiment |

A workflow is a recipe, not a new kind of skill: each step is one of the skills above, run with the Skill tool, and
the next step reads the previous step's page JSON, never its prose. `chain_status.py` says which steps already have
a page from today, so a chain resumes where it stopped, and the chain ends in one page and note: each step's
verdict, what was found, what is still open, and whether the chain is done by the rule written in the skill.
Installing the pack installs every other pack. The plan behind it, with two other ways to run the same chains, is in
[roadmap/workflows.md](../../roadmap/workflows.md).

## More

- Each skill's scripts, shared copies and guard: [reference/skills.md](../../reference/skills.md#workflows).
- [roadmap/workflows.md](../../roadmap/workflows.md): the plan, with the two other ways to run the same chains.
