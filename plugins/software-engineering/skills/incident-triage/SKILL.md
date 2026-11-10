---
name: incident-triage
description: Turns an alert or outage report and the logs into one timeline with the first error, what changed before it, a severity with its facts, mitigation options with evidence and a status update draft.
when_to_use: Use when an alert fires or production misbehaves and the team needs the picture now. Not for a failing test with its trace (bug-hunt) or after the incident (postmortem).
argument-hint: "[alert or report text] [log file or folder] [repository]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/incident-triage/scripts/guard.py" ] && exec python3 "$d/skills/incident-triage/scripts/guard.py" pre incident-triage personal; done; true'
  PostToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/incident-triage/scripts/guard.py" ] && exec python3 "$d/skills/incident-triage/scripts/guard.py" post incident-triage personal; done; true'
---

# Incident triage

The job: while it burns, the picture from the facts: when it started, what changed before it, who is
affected and how badly, what would stop it, and what to tell people now. It changes nothing, runs nothing
against production and posts nothing. The root cause is the next step, `bug-hunt`; the write-up after
the fire is `postmortem`.

Input: the alert or the report in the user's words, log files or a log folder, and the repository when
there is one; optionally a deploy record. Default: ask for the logs; without them the page says what is
known from the report alone and what the logs would add.

## Steps

1. Read [references/severity.md](references/severity.md): the criteria, the level each sets, and the
   mitigation moves with what each costs.
2. Timeline: `python3 "${CLAUDE_SKILL_DIR}/scripts/incident_timeline.py" LOGS --repo REPO`, output to your
   scratchpad. It gives the first error and the last normal entry before it, the error signatures with their
   counts, the rate before and after, the deploys and version changes, the runs and their outcomes, the
   commits in the window before the first error, and counts of the ids the errors mention. The guard's
   `personal` mode (`data_profile.py` beside the script) keeps e-mail addresses and ids out of what you read;
   the page carries counts, never a value.
3. Read the first error's entry and traceback in the log, and the code at the innermost frame that is in
   the repository. Read every error signature that differs from the first: one incident or two.
4. What changed before the first error: each deploy, version change and commit in the window, read, with
   what it touched; the one closest to the first error is a candidate, not the cause.
5. Severity: each criterion with the fact that sets it (how many runs, users or ids; is data lost, wrong or
   only late; is there a workaround; is it spreading), and the level the criteria give. A criterion with no
   fact is marked unknown and lowers nothing.
6. Impact in one sentence: who cannot do what since when.
7. Mitigation options, two or three, from severity.md: each with the evidence that it would help (the
   commit to roll back, the flag to turn off, the input to quarantine), what it costs and what it does not
   fix. None is executed; the user chooses.
8. Status update: what is known, what was done, what is next and when the next update comes, in the words
   of severity.md's template. Facts only; no cause before `bug-hunt` has one.
9. Roles to fill (who leads, who speaks, who fixes) and the next call: `bug-hunt` with the first error's
   trace, the log and the repository, written out.
10. Write the page JSON, with `facts`, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: Timeline (a `steps` block), Severity (table: criterion, fact, level it sets),
Impact (callout), What changed before the first error (table: when, what, where, read), Error signatures
(table: signature, count, first, last, component), Mitigation options (table: option, evidence, cost, what
it does not fix), Status update (code block), Roles and next steps (list). Stats on top: first error,
failed runs or error count, minutes since the first error, ids affected (a count), severity. The verdict
names the severity and the one thing to do first, in two sentences.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both files in
`${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<repo or service>/incident-triage-<YYYY-MM-DD>.*`. Write the page
in the language of the request; Serbian pages in Latin script.

## Reads

- the alert or report, the logs, the repository and its git history, a deploy record, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never runs anything against production or shared data, never restarts, rolls back or deploys; it proposes.
- Never posts a message, a status or a page anywhere; the status update is a draft on the page.
- Never names a person as a cause, and never names a cause at all before `bug-hunt` has evidence.
- Never shows a personal value from a log: an e-mail address, an id, an IP address is a count on the page.
- Never shows a secret or opens a `.env` file.
