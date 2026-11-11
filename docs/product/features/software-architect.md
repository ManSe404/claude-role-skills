# Software architect

For software architects. The skills decide what shape a system should have, draw it in C4 from a brief or from the code, review a design before it is built, and plan the way to a target in safe steps. Install it as `software-architect@claude-role-skills`; the skills are called as `/software-architect:<skill>`.

| Skill | Use it when | It writes |
|---|---|---|
| [arch-style](../../../plugins/software-architect/skills/arch-style/SKILL.md) | a brief arrives or someone proposes microservices | what shape the system should have (one deployable, modular monolith, serverless, a few services, an event backbone, microservices), decided by elimination, with fitness rules and an ADR draft |
| [arch-c4](../../../plugins/software-architect/skills/arch-c4/SKILL.md) | a system must be drawn and explained | context, containers and components as boxes inside boxes, with zoom between levels and requests traced hop by hop |
| [arch-review](../../../plugins/software-architect/skills/arch-review/SKILL.md) | a design document, proposal or set of ADRs must be reviewed before it is approved or built | waiting chains checked against their latency goals, data written by two parts, promises with no mechanism, goals without numbers, dependencies with no failure plan, documents that contradict each other, open decisions; each shown from the documents, with what to decide first |
| [arch-evolve](../../../plugins/software-architect/skills/arch-evolve/SKILL.md) | a system must move to a new structure | steps that each leave the system working, with how each is verified and undone, and where to stop |

`arch-review` reads documents, not code. The structure of code that exists (cycles, layer breaks, hidden coupling) is
part of `code-audit`.

## More

- Each skill's scripts, shared copies and guard: [reference/skills.md](../../reference/skills.md#software-architect).
- [roadmap/software-architect.md](../../roadmap/software-architect.md): the plan of the pack.
- [roadmap/code-audit.md](../../roadmap/code-audit.md): why arch-review reviews designs only.
- [roadmap/architect-packs.md](../../roadmap/architect-packs.md): the series of architect packs.
