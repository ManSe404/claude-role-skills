---
name: number-reconcile
description: Use when two numbers that should agree do not, from two systems, reports or extracts of the same figure, and the rows behind both are available, to find exactly where they part and account for the whole difference, or say exactly how much remains unexplained.
argument-hint: "[file or query behind number A] [file or query behind number B] [the window] [the key that joins them]"
---

# Number reconcile

The job: two numbers should agree and do not. Find where they part, row by row, and account for the
whole gap with causes that add up: rows in one and not the other, duplicates, filters, time zones,
rounding, timing. What cannot be explained is stated as an exact amount, never left out.

Input: the rows behind each number (CSV or JSON Lines), the period, the key that joins them, and the
columns that hold the amount and the date on each side, or a repository where these can be read
from the SQL. Default: the current repository and the two files you are given.

## Steps

1. Read [references/causes.md](references/causes.md): what each bucket means and how to narrow the
   gap down further.
2. Pin the two numbers: which metric, which window, each side's date column, amount column, filters
   and key, reading the SQL where there is one. Reproduce both numbers from the rows with
   `python3 "${CLAUDE_SKILL_DIR}/scripts/measure.py" DATA_FOLDER SPEC.json`. If you cannot, that is the
   first finding, and you say which number you could not reproduce and by how much.
3. Profile both files: `python3 "${CLAUDE_SKILL_DIR}/scripts/data_profile.py" FILE_A FILE_B --grain
   TABLE KEY`, output to your scratchpad: is the key unique on each side, how many rows have no
   key, what columns are worth slicing by (`channel`, `status`, `region`, a batch, a day).
4. Account for the gap:
   `python3 "${CLAUDE_SKILL_DIR}/scripts/reconcile.py" FILE_A FILE_B --key KEY --value-a COL --value-b COL
   --date-a COL --date-b COL --window FROM:TO --filter-a ... --slice COLUMNS --filter-columns COLUMNS`.
   Pass a timestamp as the date on each side when there is one, so a time zone can be told from timing.
   `--filter-columns` lists columns that might hold a filter, such as `channel` or `status`.
5. Read `buckets`: the gap is the sum of them, exact (`adds_up` is true: if not, stop and find out
   why). `value_difference` is the unexplained part: same key, amounts differ by more than rounding.
6. Read `slices`: does the gap sit in one channel, one batch, one day? Follow it down with `--filter-a`,
   or a narrower window, until a bucket has one plain cause you can name. Say which cuts you tried.
7. Say what each bucket is, in the data's own terms, and which ones are real differences and which
   are definitions, timing or filters that are expected. Mark what you inferred with
   [high]/[med]/[guess]. A cause no row shows is a guess.
8. Write the page JSON, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: The two numbers (kv: each number, its definition, how many rows and keys,
reproduced or not), The gap accounted for (a `chart` of kind `waterfall`: from A to B, each bucket a
step, and it must land exactly on B; and the table of buckets with amount and rows), Where it sits
(table per slice column: gap per value, with the share), What each difference is (table: bucket, what it
means, the evidence, which side is right or that nothing here can say), Still unexplained (the exact
amount and rows, and what would explain it). Stats on top: the gap, explained, unexplained, rows in
each bucket's biggest cause. The verdict says how much of the gap is explained, and the exact amount left, in
one sentence.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/number-reconcile-<YYYY-MM-DD>.*`. Write the
page in the language of the request; Serbian pages in Latin script.

## Reads

- the two files or the data they come from; the repository and its SQL, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never leaves part of the gap out: every amount is in a bucket, and what is not explained is in the
  unexplained bucket as an exact amount.
- Never says which number is right unless a row or a definition says so.
- Never shows a key or a personal value: columns and counts only. Never opens a `.env` file.
- Never prints rows of a data file while working, not even in a diagnostic: a diagnostic reaches the
  session log. Columns and counts, through the scripts.
