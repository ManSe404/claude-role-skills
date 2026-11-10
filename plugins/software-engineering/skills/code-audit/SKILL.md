---
name: code-audit
description: Reviews code as it stands for bugs, failure handling, promises in its docs that no code keeps and structure that makes it hard to change, each with file:line and the test that would catch it.
when_to_use: Use before you build on, take over or release a repository or module. Not for a diff or pull request (a change review), one known failure (bug-hunt) or an unbuilt design (arch-review).
argument-hint: "[repo, folder or module] [what worries you]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/code-audit/scripts/guard.py" ] && exec python3 "$d/skills/code-audit/scripts/guard.py" pre code-audit; done; true'
---

# Code audit

The job: the bugs in the code as it stands, each read in the code and tied to the scenario that
triggers it, and what to fix first. It changes nothing. A diff or a pull request goes to a change
review such as the built-in `/code-review`; one known failure to `bug-hunt`; one planned change to
`impact`; a design that is not built yet to `arch-review`; a repository nobody knows yet to
`codebase-map` first. An AI or LLM solution goes to `ai-review`, a data platform to `data-review`,
infrastructure code to `cloud-review`.

Input: a repository, or a folder or module in it. Default: the current repository. Optional: what
worries the user ("we keep losing documents"), which is checked first.

## Steps

1. Read [references/audit-checks.md](references/audit-checks.md): what to look for, how to confirm
   it, and how to rate it.
2. Scan: `python3 "${CLAUDE_SKILL_DIR}/scripts/audit_scan.py" REPO [--path FOLDER]`, output to your
   scratchpad. It lists what the docs promise and the places in the code worth reading. A hit is a
   place to look, never a finding.
3. Promises: from the scan and from reading the README, CLAUDE.md or AGENTS.md, the docs, contracts
   and ADRs, list what the code must guarantee: no data loss, idempotency, ordering, timeouts, retry
   limits, errors reported, a final event, stable ids. For each, find the code that keeps it. A
   promise that no code keeps is a finding.
4. Failure paths: for each main flow, walk what happens when a step fails halfway: an error after
   a delete or a partial write, a cancel, a retry or a redelivery, a missing optional dependency,
   malformed input from outside, a slow or absent service, two runs at once. Write down what the
   user or the data is left with.
5. Confirm every scan hit by reading the code around it. Drop the false ones and say how many and
   why. Read the tests near each finding: a test that should have caught it belongs in the finding.
6. Structure: `python3 "${CLAUDE_SKILL_DIR}/scripts/code_graph.py" REPO --git`, output to your
   scratchpad. Cycles, layer breaks, dumping grounds and hidden coupling (two places that share a
   format through copied strings) go in their own section, each confirmed by reading. With few
   commits, say that the history measures mean nothing yet.
7. Findings: severity by what reaches a user or the data. Each has file:line, the scenario (input
   or state, then the wrong result), the promise it breaks, the fix, and the test that would catch
   it, written out on the page.
8. Order: what loses or corrupts data first, then what fails silently, then what fails loudly,
   then the rest. Say what you would leave alone.
9. Write the page JSON, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: Findings (a `findings` block, high first), Promises (table: promise, where
stated, kept by, status: kept, broken or not checked), Failure paths (table: what fails, what happens
today, what should happen), Structure (a `graph` of the modules with the problem spots, and tables
for cycles, layer breaks and hidden coupling), Tests that would catch these (code blocks), What to
leave alone (list), What this audit did not cover (list). Stats on top: files read, promises, promises
broken, high findings, scan hits confirmed of all hits. The verdict says in two sentences whether the
code is safe to build on, and what to fix first.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<repo>/code-audit-<YYYY-MM-DD>.*`. Write the page
in the language of the request; Serbian pages in Latin script.

## Reads

- the code, its tests, docs, contracts and ADRs, and the git history, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never changes a file, and never adds a test to the repo: the tests are written out on the page.
- Never runs the code, its tests or its tools without a yes; reading is the method.
- Never reports a finding it did not read in the code; a scan hit alone is a place to look.
- Never shows a secret or opens a `.env` file.
