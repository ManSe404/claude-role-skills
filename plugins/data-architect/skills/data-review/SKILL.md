---
name: data-review
description: Use before a release, when you take over, or before you hand over a data platform, to review its models and loads in the code against the common failures - mixed grain, joins that multiply rows, loads that cannot be rerun, layers skipped, personal data served unmasked, money as floats, history overwritten, keys without tests - with file:line findings and fixes.
argument-hint: "[repository of the data platform] [samples folder]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/data-review/scripts/guard.py" ] && exec python3 "$d/skills/data-review/scripts/guard.py" pre data-review personal; done; true'
  PostToolUse:
    - matcher: "Bash|Read"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/data-review/scripts/guard.py" ] && exec python3 "$d/skills/data-review/scripts/guard.py" post data-review personal; done; true'
---

# Data review

The job: find what is wrong in a data platform's models and loads, prove each finding from the
code, and say what to fix first. It changes nothing.

Input: a repository, optionally a folder of sample files. Default: the current repository.

## Steps

1. Read [references/anti-patterns.md](references/anti-patterns.md): each failure, how to confirm it
   and how to fix it.
2. Scripts: `python3 "${CLAUDE_SKILL_DIR}/scripts/sql_inventory.py" REPO --checks`, and
   `python3 "${CLAUDE_SKILL_DIR}/scripts/data_profile.py" FOLDER` when there are samples, output to
   your scratchpad.
3. Confirm every hit by reading it. The script's hits are keyword matches: a hit you did not read
   is not a finding, and a hit that is fine is dropped with a reason in your notes.
4. Walk the failures a script cannot see: grain, history that matters, ownership, consumers outside
   the repository.
5. Measure where samples allow it, for example how many rows a join multiplies (`overlaps`,
   `multiplies_by`), orphan rows, duplicated keys. Say the numbers.
6. Findings: severity by what a wrong number would cost, file:line, evidence, fix, and the order of
   the fixes: what corrupts data first, then what exposes it, then what makes it hard to change.
7. Write the page JSON, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: Findings (a `findings` block, high first, each with file:line, evidence and
fix), Where they sit (an `architecture` or `graph` block with the problem spots flagged), What the
data shows (table, when there are samples), Order of the fixes (list), What this review did not
cover (list), Open questions.
Stats on top: findings by severity, hits confirmed of hits read. The verdict says whether numbers
from this platform can be trusted today and why, in two sentences.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/data-review-<YYYY-MM-DD>.*`. Write the
page in the language of the request; Serbian pages in Latin script.

## Reads

- the repository, its git history and the samples, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never changes a file, and never runs anything against a database.
- Never reports a finding it did not read in the code.
- Never shows a personal value or a secret: columns and counts only. Never opens a `.env` file.
