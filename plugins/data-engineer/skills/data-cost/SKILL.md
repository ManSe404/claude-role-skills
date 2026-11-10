---
name: data-cost
description: Breaks a data platform's compute and storage spend down per cluster, job, pipeline and table, and finds spending with no use behind it, such as unread tables, needless full reloads, schedules faster than the reads and idle clusters.
when_to_use: Use when the platform bill grows or before a budget review. Choosing or pricing a cloud platform goes to cloud-design, the platform's design to data-review.
argument-hint: "[repo] [usage export, storage table, query log if elsewhere]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/data-cost/scripts/guard.py" ] && exec python3 "$d/skills/data-cost/scripts/guard.py" pre data-cost; done; true'
---

# Data cost

The job: where a data platform's money went over a period, per cluster, job, pipeline and table, with
every figure adding up to the bill; then what can be cut, each cut proved from the records and priced
in money a month. It changes nothing. Choosing or pricing a cloud platform goes to `cloud-design`; a
design review of the models and loads to `data-review`; a table nobody can explain to `data-map`; a
failed run to `pipeline-incident`; checks and freshness to `data-quality`.

Input: the repository with the job definitions and SQL, and the platform's usage or billing export,
storage table, query log and run records (CSV or JSON Lines). Default: the current repository; ask for
the billing export when the script finds none.

## Steps

1. Read [references/cost-checks.md](references/cost-checks.md): each kind of waste, how to confirm
   it, how to price the cut, and what looks like waste but is not.
2. Count: `python3 "${CLAUDE_SKILL_DIR}/scripts/cost_breakdown.py" REPO`, output to your scratchpad;
   add `--usage`, `--storage`, `--queries`, `--runs` or `--jobs` for files outside the repository.
   Read `inputs` first: which file and column fed each field, and what was not found. A missing input
   is said on the page, never guessed.
3. Check the sum: `adds_up.equals_compute_total` must be true, and compute plus storage must equal
   `totals.total_eur`. If the export carries its own total, compare. Every money figure on the page
   is one the script printed, or a product of them with its formula shown (cost a run × runs saved).
4. Confirm each candidate by reading, never from the script alone:
   - an unread table: the SQL that creates it and its comments, a search of the repository for its
     name (an export, a notebook, a BI file reads outside the query log), when it was made;
   - a full reload: the job file and the SQL (`truncate`, `create or replace`), rows changed against
     rows written on every run, and a column that would carry an incremental load;
   - a schedule faster than the reads: the job file, who reads the table and how often, and what
     the readers need (the product document, an SLA);
   - compute with no jobs: the cluster in the export with no job defined or billed on it, the days it
     was up all 24 hours, the weekends.
5. Money well spent: the expensive jobs whose tables are read a lot are not cuts. List them with
   their reads and cost a read, so nobody cuts them by mistake.
6. For each cut: the change (drop after a named sign-off, a load of changed rows only, a schedule
   that matches the reads, auto-stop), the saving a month with its formula, the risk, and who must
   say yes. A cut that needs someone's sign-off says whose.
7. Write the page JSON, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: What to cut (a `findings` block, the largest saving first; each with `where`
as file:line, evidence with the records' numbers, and the fix with its saving a month), Where the
money goes (a bar `chart` of compute by job and cluster, and tables by cluster and by pipeline),
Money well spent (table: job, cost, table, consumers, reads, cost a read), By table (table: table,
storage a month, compute, total, consumer reads, cost a read), How it adds up (kv: compute, storage,
total, the check), What this did not cover (list). Stats on top: total for the period, compute,
storage a month, savings found a month, savings as a share of the bill. The verdict says in one or
two sentences how much can be cut and which item is biggest. Fill `facts`: a `costs` line per cluster
and storage, each with `as_of` and `source`, and `open` for every sign-off still needed.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<repo>/data-cost-<YYYY-MM-DD>.*`. Write the page
in the language of the request; Serbian pages in Latin script.

## Reads

- the repository, its job definitions and SQL, and the usage, storage, query and run exports, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never drops a table, changes a schedule or a load, stops a cluster or edits a job: the cuts are
  proposals for the people who own them.
- Never puts a figure on the page that the script did not compute or that does not add up to the
  totals.
- Never calls a cost waste because it is large: a cut needs spending with no use behind it.
- Never shows a secret or opens a `.env` file; a consumer that is a person's e-mail stays a label.
