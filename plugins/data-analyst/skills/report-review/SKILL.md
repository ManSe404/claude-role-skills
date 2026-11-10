---
name: report-review
description: Checks the counting behind an analysis against its data, such as double counting, wrong denominators, dropped rows, partial periods and misleading charts.
when_to_use: Use before a report or analysis with its SQL or notebook goes out. Not for general feedback with no code or data behind it.
argument-hint: "[report folder] [folder of sample data]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/report-review/scripts/guard.py" ] && exec python3 "$d/skills/report-review/scripts/guard.py" pre report-review personal; done; true'
  PostToolUse:
    - matcher: "Bash|Read"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/report-review/scripts/guard.py" ] && exec python3 "$d/skills/report-review/scripts/guard.py" post report-review personal; done; true'
---

# Report review

The job: before a report goes out, find the counting errors in it, prove each one from the code and
the data, and say what the corrected number is and whether the report's conclusion survives. It
changes nothing.

Input: a report folder with its SQL or notebook and its numbers, and a folder of sample data (CSV
or JSON Lines). Default: the current repository; ask where the sample data is if it is not there.

## Steps

1. Read [references/checks.md](references/checks.md): each failure, how to confirm it and how to
   compute the corrected number, with the shape of the data checks.
2. Read the report and list its claims: every number or comparison it states, with file:line. These
   are what the review answers.
3. Places to read:
   `python3 "${CLAUDE_SKILL_DIR}/scripts/report_check.py" sql REPORT --data DATA_FOLDER`, output to your
   scratchpad; `python3 "${CLAUDE_SKILL_DIR}/scripts/data_profile.py" DATA_FOLDER` for the keys, rows and
   columns the queries assume. A hit is a place to read, not a finding: open each one, and read every query the
   report relies on even where nothing was hit. Check notebooks too, and any chart: its axis, its
   period, what it leaves out.
4. Recount each claim with the data:
   `python3 "${CLAUDE_SKILL_DIR}/scripts/report_check.py" data CHECKS.json DATA_FOLDER`
   (avg_of_averages, small_groups, simpson, fanout, windows: shapes in the references) and
   `python3 "${CLAUDE_SKILL_DIR}/scripts/measure.py" DATA_FOLDER SPEC.json` for the rest, such as a
   corrected denominator. Compare with the number in the report.
5. Confirm or drop each hit, with the numbers. Findings: severity by whether it changes a conclusion,
   file:line, evidence with the report's number and the corrected number, the fix. A finding that
   changes a headline is high; say what the headline becomes.
6. Say what you could not check and why: a chart in a screenshot, a number with no query behind it,
   a filter on a table you have no sample of.
7. Write the page JSON, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: Findings (a `findings` block, high first, each with file:line, evidence with
the report's number and the corrected number, and the fix), The headlines after correction (table:
claim, the report's number, the corrected number, the conclusion now), One chart for the biggest
error (a `chart`: the claimed against the corrected number, or a Simpson's reversal as a bar chart per
stratum), What was checked (table: claim, file:line, how it was checked, result), What this review did
not check (list). Stats on top: findings by severity, claims checked, claims that changed. The
verdict says whether the report can go out as it is, in one sentence with the worst number.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/report-review-<YYYY-MM-DD>.*`. Write the
page in the language of the request; Serbian pages in Latin script.

## Reads

- the report folder, its queries and notebooks, the sample data, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never changes the report, a query or a notebook.
- Never reports a finding it did not read in the code and count on the data; what it could not
  count is listed as not checked.
- Never shows a personal value: columns and counts only. Never opens a `.env` file.
- Never prints rows of a data file while working, not even in a diagnostic: a diagnostic reaches the
  session log. Columns and counts, through the scripts.
