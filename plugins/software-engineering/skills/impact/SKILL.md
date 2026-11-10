---
name: impact
description: Finds everything a change reaches, including callers, dynamic uses, public surfaces, stored data and outside consumers, and the safe order to make it.
when_to_use: Use before you change, rename or remove a function, class, module, endpoint, setting or column, or on the current diff.
argument-hint: "[name and intended change, or the diff]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/impact/scripts/guard.py" ] && exec python3 "$d/skills/impact/scripts/guard.py" pre impact; done; true'
---

# Impact

The job: what one change reaches, and the order that keeps everything working while it lands.
It writes nothing but the page. To look for bugs in the code as it stands use `code-audit`.

Input: a name (function, class, module, endpoint, setting, column) and what will change about it
(signature, behaviour, meaning, removal, rename). Or the current diff: then every changed public
name is an input.

## Steps

1. Name the change: what exactly changes, in one sentence. If the intent is unclear, ask.
2. References: `python3 "${CLAUDE_SKILL_DIR}/scripts/refs.py" NAME --repo REPO --dynamic`.
   Output to your scratchpad. A text match is not a use until you read it.
3. Dynamic uses: read every dynamic site the script lists, those marked `related_to` first.
   Also look for the name as data: a string key, a route, a serialized field, a DI registration.
4. Direct uses: for each one, file:line and the verdict: breaks, needs a change, or safe.
5. Indirect uses: run the script again with the `enclosing` functions of the direct uses, round
   by round, until each path ends at a boundary: an HTTP endpoint, a CLI command, a published
   package API, a message or event, a scheduled job, a database table or file.
6. Stored data: what the old code wrote that the new code must still read (rows, cached values,
   messages in queues, files). Watch for writes by position, like `INSERT ... VALUES (?, ?)`,
   that a name search cannot find.
7. Outside the repo: who consumes each boundary, from what the repo shows (API docs, client
   code, notes like "finance reads this column"). The repo cannot prove there are no other
   consumers: say so, and say who to ask.
8. Tests: which tests cover each affected path, and which paths no test covers.
9. Safe order: expand and contract. Add the new beside the old, move the callers, migrate the
   data, tell the consumers, then remove the old. One step per deploy, each with its check.
10. Write the page JSON, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page before you write.

Sections in this order: The change, What it reaches (graph: the change as `changed`, uses as
`affected` or `safe`, boundaries as `boundary`, stored data as `data`, outside consumers as
`external`), Every use (table: where, kind, verdict, test), Stored data, Outside consumers,
Untested paths (findings), Safe order (steps). Stats on top: direct uses, indirect uses,
boundaries, outside consumers, untested paths. The verdict says whether the change is safe as
one step, and if not, how many steps it needs.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<repo>/impact-<name>-<YYYY-MM-DD>.*`.

## Reads

- the code, the tests, the docs and the git history of the repo, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never makes the change, not even a part of it.
- Never says a public surface has no other consumers: the repo cannot show that.
- Never drops a use it could not classify: it goes on the page as `unknown`.
