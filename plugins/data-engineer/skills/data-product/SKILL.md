---
name: data-product
description: Writes the consumer guide of one served table from its SQL, sample, query log, checks and documents, with its real grain, metric definitions, freshness and personal columns, naming every conflict between documents.
when_to_use: Use when a served table gets new consumers or its document is in doubt. One metric whose numbers differ between teams goes to metric-spec, lineage of the whole platform to data-map.
argument-hint: "[schema.table] [repo] [folder of sample data]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/data-product/scripts/guard.py" ] && exec python3 "$d/skills/data-product/scripts/guard.py" pre data-product personal; done; true'
  PostToolUse:
    - matcher: "Bash|Read"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/data-product/scripts/guard.py" ] && exec python3 "$d/skills/data-product/scripts/guard.py" post data-product personal; done; true'
---

# Data product

The job: everything a consumer of one served table needs, checked against the table itself: what it
is, its real grain and model, the definition of each metric, starter queries, quality and freshness,
releases and the data contract. Where the documents, the reports and the SQL disagree, each conflict
is named with both places. It changes nothing. One metric whose numbers differ between teams goes to
`metric-spec`; lineage of the whole platform to `data-map`; a design review of the models to
`data-review`; the checks of every table to `data-quality`; runbooks to `docs-draft`.

Input: the table's name, the repository that builds it, and a sample of the table (CSV or JSON
Lines). Default: the current repository; ask which table if it is not named.

## Steps

1. Read [references/product-checks.md](references/product-checks.md): what a guide must hold, how to
   confirm each part, and the conflicts to look for.
2. Facts: `python3 "${CLAUDE_SKILL_DIR}/scripts/product_facts.py" REPO --table SCHEMA.TABLE --grain K1,K2`,
   output to your scratchpad. `--grain` is the documented grain written as columns ("one row per
   store and day" is `store_id,sales_date`); without a document, leave it out. Read `inputs`.
3. Profile: `python3 "${CLAUDE_SKILL_DIR}/scripts/data_profile.py" SAMPLE --grain NAME K1,K2` (NAME
   is the sample file's name without its extension) for types, nulls and ranges. Never Read or print
   the sample's rows: the scripts give counts.
4. Grain: compare the documented grain, the key the checks use, the SQL's GROUP BY and
   `smallest_unique_keys`. If the documented key is not unique on the sample, say how many keys have
   more than one row, which column differs inside them, and what the real grain is.
5. Definitions: for every metric defined in more than one place, read each place. Name each
   conflict with both file:line and which one the SQL computes. `term_conflicts` are leads only.
   The guide gives the SQL's definition and says who must settle the conflict.
6. Personal data: a personal column in a served table is a finding: its name, how many rows carry
   it, the SQL line that brings it in, who reads the table. Never its values.
7. Freshness and quality: the SLA in the job against what the document promises; the last good
   build and the days it was missed; each check that covers the table, its results and whether it
   was ever tried on bad data; what no check covers.
8. Owner, contract, releases: who answers questions, whether the table has its own contract (a
   source contract that lists it as a consumer is not one), and its history.
9. Write the guide on the page, with a draft of each missing piece (owner, SLA, contract) marked as
   a draft for the owner. Write the page JSON, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: Findings (a `findings` block: conflicts, a wrong grain, personal columns,
gaps, each with file:line and evidence), What it is (text: purpose, built by, from what, for whom),
Grain and model (the grain stated and the real one, and a `model` block of the table and its
sources), Metric definitions (table: metric, definition the SQL computes, other definitions with
file:line, conflict), Starter queries (`code` blocks that respect the real grain), Quality and
freshness (table: check, what it covers, results, tried on bad data; the SLA and the misses),
Consumers (table: consumer, reads, how often), Releases and contract (history, and the contract
draft as `kv`), What this did not check (list). Stats on top: rows in the sample, consumers, reads,
conflicts, personal columns. The verdict says in two sentences whether consumers can rely on the
table today, and what must change first. Fill `facts`: `data` for each personal column, `open` for
each conflict that needs an owner.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<repo>/data-product-<YYYY-MM-DD>.*`. Write the page
in the language of the request; Serbian pages in Latin script.

## Reads

- the repository (SQL, jobs, checks, documents, reports), the sample data, the query log, check
  results and run records, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never changes the document, the SQL, a check or a report: the guide and its drafts are on the page.
- Never picks the right definition of a metric alone: it says which one the SQL computes and who decides.
- Never shows a personal value, on the page or in the chat: column names and counts only. Never opens
  a `.env` file.
- Never prints rows of a data file while working, not even in a diagnostic: a diagnostic reaches the
  session log. Columns and counts, through the scripts.
