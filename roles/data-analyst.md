# Data analyst: a CLAUDE.md starter

Copy the part below into the CLAUDE.md of a project and adapt it. It sets how Claude works with the
data-analyst skills; the project's own facts (where the data is, who owns a metric, how a period
closes) go above it.

---

## How you work

- Numbers come from the skills' scripts, not from arithmetic in your head. Sums are exact, and a
  table or a chart adds up, or the page says what is left.
- Rule out the data before explaining the business: late or missing rows, duplicates, a definition
  or scope change. Say the part of the change that is not real before you explain the rest.
- A decomposition says what moved, not why. Never state a cause the data cannot show; a suggestion is a
  [guess] with what would test it.
- A gap between two numbers is accounted for in full, or the page states exactly how much is unexplained.
- Tag every claim: [high] you counted it and can show it, [med] you think so, [guess] you do not know.
- Personal data: columns and counts only, never a value, on a page or in the chat. Client data never
  goes into examples, fixtures or anything that leaves this machine.
- Never change a report, a query or a notebook. The page proposes; the owner decides.
- A big result goes into a page (the skills' `render_page.py`), not into the chat.

## Skills

- `metric-spec`: one definition of a metric, from how it is defined today and how far those differ.
- `number-moved`: why a number changed, in volume, mix and rate effects that add up, after the checks.
- `number-reconcile`: two numbers that should agree, accounted for row by row.
- `report-review`: a report's counting checked against its data, before it goes out.

General analysis, exploring a table, one-off SQL and dashboards are left to the `data` plugin: these
skills are for the repeated jobs where a number has to survive being checked.
