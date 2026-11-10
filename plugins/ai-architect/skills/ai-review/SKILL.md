---
name: ai-review
description: Reviews the code of an AI or LLM solution for the common failures, such as untrusted text reaching actions, agent loops without limits, no evals, no timeouts and unknown cost, with file:line fixes.
when_to_use: Use before a release, a takeover or a handover of an AI or LLM solution. For general bugs in code use code-audit.
argument-hint: "[repo] [brief]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/ai-review/scripts/guard.py" ] && exec python3 "$d/skills/ai-review/scripts/guard.py" pre ai-review; done; true'
---

# AI review

The job: review an existing AI solution's design from its code, item by item, and show where the
problems sit in its architecture. It proposes fixes and changes nothing.

Input: a repository, optionally the brief or design document it was built for. Default: the
current repository.

## Steps

1. Count first: `python3 "${CLAUDE_SKILL_DIR}/scripts/ai_inventory.py" REPO` into your scratchpad.
   Its hits are leads: read the code at every one before it becomes a finding.
2. Reconstruct the architecture from the code: entry points, the model calls, the tools and what
   each can do, the stores, the outside systems, the prompts. Read every hop of the main request.
3. Read [references/anti-patterns.md](references/anti-patterns.md) and go through every item.
   Give each one a status: found, not found (and what you checked) or not checked (and why).
4. Against the brief, if given: is the pattern the simplest that passes? Would a workflow, RAG or
   one call do? Use the ladder in the `ai-pattern` skill when it is installed, else the table in
   anti-patterns.md.
5. Findings: title, file:line, evidence (quote the code line; never a secret value), the failure it
   leads to, the smallest fix, severity. Order by severity. Tag each claim.
6. What is good: the parts to keep, with file:line, so the fixes do not break them.
7. The architecture with the problem spots: an `architecture` block of the solution as built, with
   `flag: "bad"` or `"warn"` on the components and links of the findings, untrusted links marked,
   and side effects marked, so the page shows where untrusted text reaches an action. When fixes
   change the shape, add a "fixed" variant.
8. Write the page JSON, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page before you write.

Sections in this order: Architecture as built (`architecture` block with flags), Findings
(`findings`, high first), Checklist (table: item, status, where, note), What is good (list), Fix
order (steps: what to fix first and why), Open questions. Stats on top: findings by severity,
model calls without a timeout, tools with side effects, tracing and evals present or not. The
verdict says in two sentences whether it is fit to release and the one fix that matters most.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<repo>/ai-review-<YYYY-MM-DD>.*`. Write the page
in the language of the request; Serbian pages in Latin script.

## Reads

- the repository and its git history, the brief, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never changes a file, runs the application, its tests against live services, or calls a model.
- Never opens a `.env` file and never shows a secret value, even a fake one: name it, give its
  kind and where it is.
- Never reports a lead from the script as a finding without reading the code at that line.
- Never prices from memory: give the calls and tokens per request, and leave the price to the
  `ai-stack` skill or a price table with its date and source.
