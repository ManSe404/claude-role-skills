# Data analyst

For data analysts. The skills write the one definition of a metric, explain why a number changed in effects that add up exactly, account for the whole gap between two numbers, and check a report's counting before it goes out. Install it as `data-analyst@claude-role-skills`; the skills are called as `/data-analyst:<skill>`.

| Skill | Use it when | It writes |
|---|---|---|
| [metric-spec](../../../plugins/data-analyst/skills/metric-spec/SKILL.md) | two teams or reports show different numbers for what should be one metric | where it is defined today, how far those definitions differ on sample data, step by step, and one definition: grain, filters, formula, window, currency, owner, what it leaves out |
| [number-moved](../../../plugins/data-analyst/skills/number-moved/SKILL.md) | a reported number changed between two periods and someone asks why | checks that the data did not fake the change, then volume, mix and rate effects that add up exactly, ranked, with what is left unexplained and what the data cannot show |
| [number-reconcile](../../../plugins/data-analyst/skills/number-reconcile/SKILL.md) | two numbers that should agree do not | the whole gap accounted for row by row (only in one, filters, duplicates, time zones, timing, rounding), adding up exactly, or the exact amount left unexplained |
| [report-review](../../../plugins/data-analyst/skills/report-review/SKILL.md) | before a report with its SQL or notebook goes out | the counting checked against its data: double counting, wrong denominators, dropped rows, partial periods, averages of averages, small samples, a Simpson's reversal, misleading charts, each with file:line and the corrected number |

These skills do the repeated jobs that need the counting done by a script and a page someone can trust; general
questions, exploring a table and dashboards are left to the Anthropic `data` plugin. Sums are exact and read-only: a
personal value never reaches the output.

## More

- Each skill's scripts, shared copies and guard: [reference/skills.md](../../reference/skills.md#data-analyst).
- [roadmap/data-analyst.md](../../roadmap/data-analyst.md): the plan of the pack.
