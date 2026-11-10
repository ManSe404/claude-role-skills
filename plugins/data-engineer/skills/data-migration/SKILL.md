---
name: data-migration
description: Inventories an old estate of scheduled jobs from its inventory and scripts, rates each job keep, rebuild or retire, and plans the move in waves with acceptance numbers, a parallel run and a rollback.
when_to_use: Use before moving cron jobs, an old warehouse or a legacy ETL estate onto a new platform. Choosing the new platform goes to data-platform, restructuring a software system to arch-evolve.
argument-hint: "[job inventory or crontab] [scripts folder] [as-of time]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/data-migration/scripts/guard.py" ] && exec python3 "$d/skills/data-migration/scripts/guard.py" pre data-migration; done; true'
---

# Data migration

The job: an old estate of jobs and tables understood from what it really does, not from what its
inventory says: which jobs still run, which are dead, which are copies, what each script reads and
writes, who outside depends on it. Then a rating per job (keep, rebuild, retire) and a plan in waves,
each with acceptance numbers, a parallel run and a rollback. It changes nothing. Choosing the new
platform goes to `data-platform`; moving a software system's structure to `arch-evolve`; what one
change reaches to `impact`; lineage of the new platform to `data-map`.

Input: the job inventory (CSV or JSON Lines, or a crontab) and the job scripts. Default: an
inventory in the current repository; ask for it, and for the time it was taken, if neither is clear.

## Steps

1. Read [references/migration-checks.md](references/migration-checks.md): each signal, how to
   confirm it, the rating rules, and what a wave needs.
2. Inventory: `python3 "${CLAUDE_SKILL_DIR}/scripts/estate_inventory.py" INVENTORY --as-of "YYYY-MM-DD HH:MM"`,
   output to your scratchpad. Take the as-of time from the inventory's own note (when it was
   exported); without one the script uses the latest last run, and the page says so. Read `inputs`:
   scripts missing, scripts nobody lists.
3. Confirm each signal by reading the scripts, never from the script's output alone:
   - dead and stopped jobs: last run, missed runs, and whether what they wrote is still read;
   - identical scripts: what each output is for and who reads it, so one survives;
   - undeclared links: the line that writes and the line that reads the same path or table, and
     the inventory row that does not declare it;
   - outside consumers and inputs: the host, what goes there, how it logs in. A credential appears
     only as its placeholder, such as `${VAR}`; a literal value is reported as hidden, never shown;
   - two jobs writing the same target at the same time: what each does to it, and which result wins;
   - outputs nobody inside reads: exports that someone outside depends on, or nobody.
4. Rate each job keep, rebuild or retire, with the reason in one line. A dead job is retired only
   after its owner or a consumer confirms; a copy keeps one job and points the other's readers at it.
5. Plan waves from `groups` and `order`: jobs linked by data move together, writers before readers,
   the riskiest outside consumer not in the first wave. Each wave: its jobs, the acceptance numbers
   (rows and sums per day equal to the old output for an agreed number of days, files equal by row,
   delivery time), the parallel run (how long, compared how), the cutover, and the rollback (the old
   cron line re-enabled; the old target untouched until sign-off).
6. Questions: per owner or consumer, what must be answered before their wave.
7. Write the page JSON, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: Findings (a `findings` block: dead jobs, copies, hidden links, clashes,
outside consumers, each with file:line and evidence), The estate (table: job, cadence, last run,
status, reads, writes, rating and why), Links between jobs (a `graph` of jobs and the data between
them, outside hosts as `external`), Waves (`steps`, one per wave), Acceptance and rollback (table per
wave: check, number, how compared, rollback), Questions before each wave (list), What this did not
cover (list). Stats on top: jobs, dead, keep, rebuild, retire, waves. The verdict says in two
sentences how big the move really is and what must happen first. Fill `facts`: `components` for the
outside hosts and file shares, `decisions` for the ratings, `open` for the questions.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<repo>/data-migration-<YYYY-MM-DD>.*`. Write the
page in the language of the request; Serbian pages in Latin script.

## Reads

- the inventory and the job scripts, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never disables, edits, runs or deletes a job, a crontab line or a table: the plan is a proposal.
- Never retires a job on the inventory alone: the last run, the readers and an owner's yes decide.
- Never prints a credential, password or token: a placeholder such as `${VAR}` at most, and never
  opens a `.env` file or the host's environment.
- Never treats the inventory's `depends_on` as the whole truth: links come from what scripts read
  and write.
