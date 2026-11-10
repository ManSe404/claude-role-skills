# Reading the conflicts

`join_facts.py` lists places to read, not verdicts. Every conflict has `type`, `pages`, `values` and `read`.
Read the pages it names, and the brief, before you call it real or not.

| Type | What it means | Real when | Not real when | Severity |
|---|---|---|---|---|
| `region_forbidden` | something sits in a region a data rule rules out | the component handles the data the rule protects, or the rule covers the whole solution | it holds nothing covered by the rule: say why, with the page that shows it | high |
| `regions_disagree` | pages name regions with nothing in common | they are one deployment | they are separate deployments on purpose, or one page compares clouds | medium |
| `decision_differs` | one title, different choices | both pages decide the same thing | the titles match by accident; say what each one decides | high when it changes what is built, medium otherwise |
| `stale_cost` | a price is older than the threshold | it is used for a decision, or in a total a budget depends on | it is not used anywhere that matters; say so | medium, low when small |
| `mixed_currencies` | totals are in more than one currency | always a fact to report | | low on its own |
| `over_budget` | a group total is over the stated budget | the items are meant to be paid together | the group adds alternatives, or two pages priced the same thing: say so and which | high |
| `budget_other_currency` | a total could not be compared with the budget | always say it was not compared | | medium, because the budget check is incomplete |
| `budgets_differ` | pages state different budgets | always one must be chosen | | high |
| `component_technology` | the same component, different technologies | it is one component and the choice matters | the two are at different levels of detail or are different components with the same id | high for a data store, medium otherwise |
| `assumption_numbers` | two pages assume different numbers for the same thing | it changes a decision, for example a team of 5 against a team of 12 ruling on what the team can run | the numbers count different things | high when it drives a decision, medium otherwise |

## Recommending a side

- Prefer the side that keeps a rule the brief calls not negotiable, then the side with the fewer moving
  parts or lower running cost, then the side that keeps the option to change later.
- Say what changes and on which page: "cloud-design must change backups to an EU region" is a recommendation
  someone can act on; "this conflicts" is not.
- Never pick a side only because a page is newer. A specialist's reason beats a date.
- When only the client can settle it (a budget, a deadline, whether a rule applies) it is an open question, not a
  recommendation.

## Findings

One `findings` item per real conflict: severity, a title, `where` naming the pages, `evidence` saying which page
says what with the numbers, `fix` saying the side recommended and what must change. A conflict that turned out not
to be real stays on the page as `status: declined` with its `reason`. Keep every number as the page states it; add
`[high]`, `[med]` or `[guess]` to anything no page or script gave you.
