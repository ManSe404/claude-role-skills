---
name: postmortem
description: Writes the blameless postmortem of a resolved incident from the triage and bug-hunt pages, the logs and git, with a sourced timeline, cause and factors, a why chain that stops at the first guess, and action items with checks.
when_to_use: Use when an incident is resolved and the team needs the write-up. Not while it burns (incident-triage) and not to find the cause (bug-hunt).
argument-hint: "[incident-triage and bug-hunt page JSON] [logs] [repository] [detected, mitigated and resolved times]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/postmortem/scripts/guard.py" ] && exec python3 "$d/skills/postmortem/scripts/guard.py" pre postmortem personal; done; true'
  PostToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/postmortem/scripts/guard.py" ] && exec python3 "$d/skills/postmortem/scripts/guard.py" post postmortem personal; done; true'
---

# Postmortem

The job: after the fire, the write-up the team can learn from: what happened and when, with a source for
every entry, why, as far as the evidence goes and no further, and what will change, each change with the
check that shows it is done. Roles, not names. It changes nothing; the document goes into a repository or
a wiki only after the yes. The cause itself comes from `bug-hunt`; the picture during the incident from
`incident-triage`.

Input: the JSON of the incident-triage and bug-hunt pages when they exist, the logs, the repository, and
the times the incident was detected, mitigated and resolved. Default: ask for the times the logs cannot
give; without a bug-hunt page, stop at the cause and write out the call to run it.

## Steps

1. Read [references/postmortem-checks.md](references/postmortem-checks.md): what a sourced timeline needs,
   how a why chain is tested, and what makes an action item real.
2. Timeline: `python3 "${CLAUDE_SKILL_DIR}/scripts/incident_timeline.py" LOGS --repo REPO --detected T
   --mitigated T --resolved T`, output to your scratchpad. Beside the first error, the deploys and the
   version changes, it gives the minutes to detect, to mitigate and to resolve, and the errors in each
   phase. The guard's `personal` mode (`data_profile.py` beside the script) keeps personal values out of
   what you read; the page carries counts.
3. Read the triage and bug-hunt pages: their facts, their verdict, their open questions. What they state
   is quoted with its page as the source; what they left open stays open here.
4. The timeline on the page: every entry with its source (log line, page, git, a person's statement
   marked as such), from the last change before the first error to the resolution. A gap nobody can
   source is written as a gap.
5. Root cause: from the bug-hunt page, in one sentence, with its evidence. Without that page, the
   section says so and the next call is written out; nothing is inferred from the symptoms.
6. Contributing factors: what let the cause reach production and stay there (a test removed, no alert,
   a deploy without a check, a format nobody documented), each with evidence.
7. The why chain: from the symptom, each link with the evidence that backs it and its tag; the chain stops
   at the first link that would be a [guess], and says what evidence would extend it. Five whys is not a
   target.
8. What went well and what went poorly, from the facts: time to detect against the error count before
   detection, a rollback that worked, an alert that did not fire, a runbook that was missing.
9. Action items: each tied to a factor, with its owner as a role, and the check that shows it is done
   (a test, an alert that fires on the signature, a document that exists). An item with no check is not
   listed.
10. Write the page JSON, with `facts`, render it, and say where to open it. The postmortem in Markdown is
    on the page; offer to write it where the user says, after the yes.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: Summary (callout), Timeline (a `steps` block, each with its source), Root cause,
Contributing factors (table: factor, evidence, where), Why chain (table: why, answer, evidence, tag), What
went well and poorly (two lists), Action items (table: action, factor, role, check), The document (a `code`
block in Markdown). Stats on top: minutes to detect, to mitigate, to resolve, errors before detection,
action items. The verdict names the cause in one sentence and the one change that matters most.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both files in
`${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<repo or service>/postmortem-<YYYY-MM-DD>.*`. Write the page in the
language of the request; Serbian pages in Latin script.

## Reads

- the triage and bug-hunt pages, the logs, the repository and its git history, read-only

## Writes

- the page and its JSON, outside the repo
- after the yes: the one Markdown file, where the user named

## Never

- Never names a person: the timeline, the factors and the action items carry roles.
- Never writes a cause it did not read on the bug-hunt page or in the code; the why chain stops at the first guess.
- Never posts anywhere, and never writes into a repository or a wiki before the yes.
- Never shows a personal value from a log, a secret, or the content of a `.env` file.
