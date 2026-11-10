---
name: bug-hunt
description: Use when an error, a stack trace, a failing test or a bug report needs its root cause, to go from the symptom to a cause shown with evidence, a failing test that reproduces it, the other places with the same weakness, and fix options - fixing only after the yes.
argument-hint: "[error text, log file, failing test or issue]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/bug-hunt/scripts/guard.py" ] && exec python3 "$d/skills/bug-hunt/scripts/guard.py" pre bug-hunt; done; true'
---

# Bug hunt

The job: from the symptom to the root cause, proven, and a test that fails for exactly that
reason. It proposes the fix and writes it only after the yes. With no symptom yet, to look for bugs
across the code, use `code-audit`.

Input: the error text or a log file, a failing test, or a bug report. Ask for the trace and
when it started if they are missing.

## Steps

1. Symptom: the exact error, where it surfaced, when it first appeared and how often, in the
   user's words and in the log's.
2. Map the trace: `python3 "${CLAUDE_SKILL_DIR}/scripts/suspects.py" TRACE --repo REPO`, output
   to your scratchpad. It maps each frame to the repo and blames the line. If `code_moved` is
   true, the running code is not the code you are reading: find the deployed version first.
3. Reproduce: the smallest command or test that shows the same error, run in a scratch copy or
   with a temporary database, never against shared data. Cannot reproduce? Stop, say what is
   missing (data, environment, timing), and do not guess on.
4. Read the frames from the innermost one out: the values that reached each frame and where
   they came from.
5. What changed: read the commits the script names (`git show`), the deploys in the log, and
   the input data of the failing run against the last good one.
6. Hypotheses: two or three, each with the evidence for it, the evidence against it, and the
   check that decides between them. Run the checks. The one that survives is the root cause
   [high]. If none survives cleanly, report the best one as [med] and say which check is missing.
7. Regression test: the test that fails on the current code for the root cause, in the repo's
   own test style. Propose it; after the yes, add it and run it to show it fails for the right
   reason.
8. Same weakness elsewhere: search for the same assumption (the same call, the same parsing,
   the same missing check) across the repo, each place with file:line.
9. Fix options: two, with their effort and risk, and the one you recommend. After the yes, make
   the fix, run the regression test and the whole suite, and report both.
10. Write the page JSON, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page before you write.

Sections in this order: Symptom, Reproduction, The trace (code blocks with the failing line
highlighted), What changed (steps: commits and deploys on a timeline), Hypotheses (table:
hypothesis, for, against, check, result), Root cause, Regression test (code), Same weakness
elsewhere (findings), Fix options. Stats on top: first failure, failed runs, the commit that
caused it, places with the same weakness. The verdict names the root cause in one sentence.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<repo>/bug-hunt-<YYYY-MM-DD>.*`.

## Reads

- the error and the logs, the code, the tests, the git history, the input data of the run

## Writes

- the page and its JSON, outside the repo
- after the yes: the regression test, then the fix

## Never

- Never fixes before the root cause has evidence, and never fixes without the yes.
- Never changes, skips or loosens an existing test to make it pass.
- Never runs anything against production or shared data, and never deletes logs or data.
