---
name: number-moved
description: Explains why a business number changed between two periods, checking for late or missing data first, then splitting the change into effects that add up exactly.
when_to_use: Use when someone asks why a reported number moved and the rows behind it are in a CSV or JSON Lines file. Not for a trend question with no data file.
argument-hint: "[data file] [the number and the two periods] [definition, repo or SQL behind it]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/number-moved/scripts/guard.py" ] && exec python3 "$d/skills/number-moved/scripts/guard.py" pre number-moved personal; done; true'
  PostToolUse:
    - matcher: "Bash|Read"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/number-moved/scripts/guard.py" ] && exec python3 "$d/skills/number-moved/scripts/guard.py" post number-moved personal; done; true'
---

# Number moved

The job: say why a number moved, in a way that adds up. First it rules out the data itself (late or
missing rows, duplicates, a definition or scope change). Then it splits what is left into volume, mix
and rate effects by segment, ranks the drivers, and says how much they explain and what is left. It
never says more about causes than the data can show.

Input: the rows behind the number (CSV or JSON Lines), the number as it was reported and the two
periods, and where the definition lives if there is a repository. Default: the current repository
and the file you are given; ask for the file and the two periods if they are missing.

## Steps

1. Read [references/decomposition.md](references/decomposition.md): the effects, how to read each
   one, the data problems to rule out, and the wording that does not claim a cause.
2. Pin the number: which metric, which two periods, the definition (`git log` and the SQL if there
   is a repository), and the reported figures. Run the definition on the sample with
   `python3 "${CLAUDE_SKILL_DIR}/scripts/measure.py" FOLDER SPEC.json` and compare: if the reported
   numbers do not come out, the gap between them is the first finding.
3. Profile: `python3 "${CLAUDE_SKILL_DIR}/scripts/data_profile.py" FILE`, output to your
   scratchpad, for the columns and keys. Candidate segments are columns with few distinct values.
4. Rule out data problems first, with
   `python3 "${CLAUDE_SKILL_DIR}/scripts/decompose.py" FILE --date COL --a FROM:TO --b FROM:TO --value COL
   --volume COL --by SEGMENT --filter ... --dedupe KEY --loaded-at COL --as-of TIMESTAMP` (`--loaded-at`
   and `--as-of` when the rows carry when they arrived and the report has a moment). Read `checks`:
   rows and duplicates removed, days with no rows and thin days, unequal period lengths, and `late`: what a
   report at that moment could not have seen, and how much of the reported change that fakes
   (`change_faked_by_late_rows`). Then `git log` over the two periods for the definition's file, and
   segments that exist in only one period. Say the fake or doubtful part of the change as a number
   before going on, and decompose on the corrected rows.
5. Decompose: run `decompose.py` with one `--by` per candidate segment. Read `effects`, the row per
   segment, and `drivers`. Keep the segment that concentrates the change, and say which others you
   tried. `adds_up` must be true; say so if it is not.
6. Explain with what was measured: the effects, the top drivers, how much of the change they cover
   (`explained_by_top`) and what is left (`left_unexplained`), including that a rate effect only says the
   amount per unit moved. Name what the data cannot show.
7. Write the page JSON, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: The change (reported against final, the part that is not real), The checks
(table: late rows, missing and thin days, duplicates, definition and scope, each with what was counted
and the result), From last period to this one (a `chart` of kind `waterfall`: the first period, the
fake part if any, volume, mix, rate, new and gone (leave out a zero), the second period, and it must add
up), Drivers
(a `chart` of kind `bar` ranked by size, and the segment table with volume, mix and rate), What is
left unexplained (the top drivers' share, the remainder, and what the rate effect does not say),
What the data cannot show (list). Stats on top: the reported change, the change after the
checks, the largest effect, the share of the change the top drivers explain. The verdict says how
much of the move is real and what it is mostly made of, in two sentences with numbers.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/number-moved-<YYYY-MM-DD>.*`. Write the
page in the language of the request; Serbian pages in Latin script.

## Reads

- the data file; the repository and its git history when given, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never decomposes before the data problems are checked and either ruled out or taken out.
- Never states a cause the data cannot show: a price rise, a campaign, a competitor. What the data
  cannot show goes on the page as a question or a [guess], never as a result.
- Never reports a share or an effect it did not count with the script.
- Never shows a personal value: a personal column is never a segment. Never opens a `.env` file.
- Never prints rows of a data file while working, not even in a diagnostic: a diagnostic reaches the
  session log. Columns and counts, through the scripts.
