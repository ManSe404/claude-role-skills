# Data engineer

For data engineers who run a platform: a new source, the contract with it, a failed run, the checks, the money, an old estate to move and the tables served to consumers. Install it as `data-engineer@claude-role-skills`; the skills are called as `/data-engineer:<skill>`.

| Skill | Use it when | It writes |
|---|---|---|
| [source-profile](../../../plugins/data-engineer/skills/source-profile/SKILL.md) | a new source, feed or file set arrives | its format, schema drift between deliveries, null tokens, placeholder dates, duplicate keys, orphans, gaps and personal data, counted, and where it disagrees with the vendor's document |
| [source-contract](../../../plugins/data-engineer/skills/source-contract/SKILL.md) | a contract with a source system is to be written, agreed or checked | the contract's clauses against the files, the metadata and the delivery log: late deliveries, types the data breaks, columns that left, owners still to be named |
| [pipeline-incident](../../../plugins/data-engineer/skills/pipeline-incident/SKILL.md) | a scheduled data load or transformation failed | the run layer by layer, what changed in the delivery, the root cause, the same weakness in other tables, the consumers hit, a workaround, two fixes, e-mail drafts and the incident-log entry |
| [data-quality](../../../plugins/data-engineer/skills/data-quality/SKILL.md) | someone asks which tables are safe to use today | every check over a period, the quarantine by rule and day, freshness against each table's service level, checks that warn every day or can never fail, and a verdict per table |
| [data-cost](../../../plugins/data-engineer/skills/data-cost/SKILL.md) | the platform bill grows, or before a budget review | compute and storage per cluster, job and table, adding up to the cent, and the spending with no use behind it: unread tables, needless full reloads, schedules faster than the reads, idle clusters |
| [data-migration](../../../plugins/data-engineer/skills/data-migration/SKILL.md) | an old estate of jobs must move to a new platform | the inventory read from the scripts: dead jobs, duplicates, hidden file dependencies, outside consumers, clashing writers; each job rated keep, rebuild or retire, and waves with acceptance numbers, a parallel run and a rollback |
| [data-product](../../../plugins/data-engineer/skills/data-product/SKILL.md) | a served table gets new consumers or its document is in doubt | the consumer guide: real grain from the data, metric definitions from every document with their conflicts, freshness, the checks behind it, personal columns, starter queries |

These skills run a platform that exists. Deciding or reviewing its design is `data-architect`, a number that moved
or disagrees is `data-analyst`, a live outage of an application is `incident-triage` and the runbook is `docs-draft`
(both software-engineering). A quick look at a table, one-off SQL and dashboards are left to the Anthropic `data`
plugin. Read-only: a contract, an incident-log entry or an e-mail is a draft on the page until the yes.

## More

- Each skill's scripts, shared copies and guard: [reference/skills.md](../../reference/skills.md#data-engineer).
- [roadmap/data-engineer.md](../../roadmap/data-engineer.md): the plan of the pack.
