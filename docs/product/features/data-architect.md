# Data architect

For data architects. The skills decide what a data platform should be and size it, design the model with its grain and keys, map what exists from the code, and review it. Install it as `data-architect@claude-role-skills`; the skills are called as `/data-architect:<skill>`.

| Skill | Use it when | It writes |
|---|---|---|
| [data-platform](../../../plugins/data-architect/skills/data-platform/SKILL.md) | a brief or a list of sources arrives, before anything is built | what the platform should be (reports on the source, one database, a warehouse, a lakehouse, a streaming path, a mesh), decided by elimination, sized, with the layers, where personal data goes and an ADR draft |
| [data-model](../../../plugins/data-architect/skills/data-model/SKILL.md) | a subject area must be modelled | the approach, the grain of every fact checked against the data, keys, history, personal data, a clickable model and DDL drafts |
| [data-map](../../../plugins/data-architect/skills/data-map/SKILL.md) | you inherit a data platform or must explain one | layers, table lineage read from the code, owners, tables nobody reads, dynamic SQL, where personal data travels |
| [data-review](../../../plugins/data-architect/skills/data-review/SKILL.md) | before a release, a take-over or a hand-over | the models and loads against the common failures, with file:line findings, what the data shows and the order of the fixes |

Prices are not part of this pack: it sizes a platform in GB and rows, and what it costs in a cloud is
`cloud-design` in the `cloud-architect` pack.

## More

- Each skill's scripts, shared copies and guard: [reference/skills.md](../../reference/skills.md#data-architect).
- [roadmap/data-architect.md](../../roadmap/data-architect.md): the plan of the pack, including the `facts` format.
- [roadmap/architect-packs.md](../../roadmap/architect-packs.md): the series of architect packs.
