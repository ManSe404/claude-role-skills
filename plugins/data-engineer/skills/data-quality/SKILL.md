---
name: data-quality
description: Summarises a platform's checks over a period, with what passed, warned and failed, the quarantine, freshness against each table's service level, checks that prove nothing, and a verdict per table.
when_to_use: Use when asked which tables are safe to use today, what the checks stopped or how far to trust them. A design review of models and loads goes to data-review, a report's counting to report-review.
argument-hint: "[repository] [period] [tables that matter most]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/data-quality/scripts/guard.py" ] && exec python3 "$d/skills/data-quality/scripts/guard.py" pre data-quality personal; done; true'
  PostToolUse:
    - matcher: "Bash|Read"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/data-quality/scripts/guard.py" ] && exec python3 "$d/skills/data-quality/scripts/guard.py" post data-quality personal; done; true'
---

# Data quality

The job: how far the platform's tables can be trusted today, from what its checks really did over a
period. Which checks passed, warned and failed; what the quarantine took out, by rule and day, and why
it moved; how fresh each table is against its service level; and the checks that prove nothing: one
that warns every day and nobody acts on, one that cannot fail, one never tried on bad data. It ends
in a verdict per table: safe, use with care, do not use. It changes nothing. A design review of the
models and loads goes to `data-review`; one failed run to `pipeline-incident`; the counting in a report
to `report-review`; what one served table means for its consumers to `data-product`.

Input: the platform's repository with its check results, quarantine, run records, check and
quarantine definitions, the bad-data cases the checks were tried on, and job definitions with their
service levels. Default: the current repository and the whole period of its check results. Optional:
a period, and the tables that matter most.

## Steps

1. Read [references/checks.md](references/checks.md): what makes a check worthless, how to confirm it,
   how to set a verdict.
2. Summarise: `python3 "${CLAUDE_SKILL_DIR}/scripts/quality_summary.py" REPO [--from DAY --to DAY]`,
   output to your scratchpad. It says which files and fields it understood, then per check the passes,
   warnings and failures, the checks that warn every day, never failed, cannot fail or were never tried
   on bad data, single failures with their notes, freshness against each SLA, the quarantine per rule
   and day with any step change and the values behind it, and a first verdict per table with reasons.
   A hit is a place to read, not a finding.
3. Read each check that the summary marks: its definition (query, thresholds), its test case, and for a
   failure its note. A single failure with a note that explains it and a pass the next day is not a
   finding; say it and why. A check that cannot fail is proven by reading its condition, not by its
   record of passes.
4. Quarantine: for a rule whose daily rows jumped, read the rule and the reference table it reads.
   Profile the reference with `python3 "${CLAUDE_SKILL_DIR}/scripts/data_profile.py" FILE` if needed.
   Say what the rows are (a new value the reference lacks, a source change), how many rows and days,
   and which table is missing them. Counts and codes only, never a row.
5. Freshness: per table with a service level, the days it was not built in time, from the checks and
   the runs, and who reads it (job definitions, product documents).
6. Verdicts: start from the script's, then adjust with what you read: a table whose freshness failed or
   whose load failed is do not use; a warning nobody acts on, rows held in quarantine or a check that
   cannot fail is use with care; safe only when its checks passed and could have failed. One line of
   why per table, with the numbers.
7. Findings, each with file:line (the check's definition, the result line), the numbers, what it
   lets through, and the fix (a threshold, a condition, a test case, a reference row). Write the page
   JSON, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: Verdict per table (table: table, verdict, why, last result), Findings (a
`findings` block, high first), Checks over the period (table: check, table, pass, warn, fail, failing
rows, test case), Freshness (table: table, SLA, last built, days late), Quarantine (a `chart` of kind
`line` of rows per day for the rule that moved, and a table of its values with rows, first day and
whether the reference has them), What looked wrong but is fine (list), What this summary did not check
(list). Stats on top: results in the period, failures, tables do not use, checks that prove nothing,
rows quarantined. The verdict says in two sentences which tables not to use today and why, and the
check to fix first.

Fill `facts`: scope, assumptions, and the open questions.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<repo>/data-quality-<YYYY-MM-DD>.*`. Write the page
in the language of the request; Serbian pages in Latin script.

## Reads

- check results, quarantine, run records, check, rule and job definitions, test cases, reference
  tables and product documents, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never changes a check, a threshold, a rule or a reference table, never releases quarantined rows,
  never reruns a job.
- Never calls a table safe because its checks passed when a check of it cannot fail or was never
  tried on bad data.
- Never shows a personal value: columns and counts only. Never opens a `.env` file.
- Never prints rows of a data file while working, not even in a diagnostic. Columns and counts,
  through the scripts.
