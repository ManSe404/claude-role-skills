---
name: metric-spec
description: Use when two teams or reports show different numbers for what should be the same business metric, or before a metric goes on a dashboard or into a target, and the SQL, dbt models or report folder that compute it and a sample of its data are at hand, to write the one definition everyone will use.
argument-hint: "[repository or report folder] [metric name] [folder of sample data]"
---

# Metric spec

The job: one definition of a metric that two people can compute and get the same number. It finds
how the metric is defined today, measures on sample data how far those definitions disagree, and
writes the definition: grain, filters, formula, time window, currency, owner, what it does not
include. It changes nothing.

Input: a repository or report folder, the metric's name and any other names it goes by, and a folder
of sample data (CSV or JSON Lines). Default: the current repository; ask for the metric's name.

## Steps

1. Read [references/definition.md](references/definition.md): what each field must say and how to
   decide it when the existing definitions disagree.
2. Find where it is defined:
   `python3 "${CLAUDE_SKILL_DIR}/scripts/metric_compare.py" find REPO --name NAME[,OTHER_NAME]`,
   and `python3 "${CLAUDE_SKILL_DIR}/scripts/sql_inventory.py" REPO` for the tables behind each one, output to
   your scratchpad. Read every hit in its file: the first script only finds aliases and their WHERE.
   Other definitions live in dashboards, spreadsheets and heads: say which sources you did not see.
3. Understand each definition: the grain, every filter, the formula, the date it counts by, the
   currency, and who owns it, from a `meta` owner, a CODEOWNERS file or `git log`. Note when and why
   a definition last changed.
4. Profile the sample: `python3 "${CLAUDE_SKILL_DIR}/scripts/data_profile.py" FOLDER`: rows, nulls, keys
   and the date range. If the sample cannot tell two definitions apart, say so.
5. Write each definition as a `measure` (the shape `measure.py` reads: table, window, filters, dedupe,
   value) in SPEC.json as {"definitions": [{"name", "source": "file:line", "measure"}]}, the first being
   the one others are compared with, and run
   `python3 "${CLAUDE_SKILL_DIR}/scripts/metric_compare.py" compare SPEC.json DATA_FOLDER`.
   Read `walks`: each difference one at a time and how much it moves the number. The steps add up to
   the whole gap, in the stated order (`adds_up` is true: if it is not, stop and find out why).
6. Write the definition. Decide each field from the references, one sentence of reason for every
   place where the existing definitions differ. Do not invent a rule the data or the business did
   not give: what is left is an open question with its owner, and the page says so.
7. Check the definition on the sample with
   `python3 "${CLAUDE_SKILL_DIR}/scripts/measure.py" DATA_FOLDER SPEC.json` so the number on the page
   comes from the script, and say which existing definition it matches or how far it is from each.
8. Write the page JSON, with `facts`, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: The definition (a `kv` block with grain, filters, formula, time window,
currency, owner, not included), Where it is defined today (table: name, file:line, formula, filters,
date column, owner, number on the sample), How far they differ (a `chart` of kind `waterfall` from
one definition to another, and the table of the walk), Why this definition (table: the difference,
the choice, the reason), Open questions (list with who should answer). Stats on top: definitions
found, the largest gap and its share of the number, rows in the sample. The verdict says the
metric's definition in one sentence and how much of today's numbers it changes.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/metric-spec-<YYYY-MM-DD>.*`. Write the
page in the language of the request; Serbian pages in Latin script.

## Reads

- the repository or report folder and its git history; the sample data, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never changes a query, a model or a file in the repository.
- Never states a definition as agreed: this page proposes it, and the owner decides.
- Never shows a personal value: columns and counts only. Never opens a `.env` file.
- Never prints rows of a data file while working, not even in a diagnostic: a diagnostic reaches the
  session log. Columns and counts, through the scripts.
