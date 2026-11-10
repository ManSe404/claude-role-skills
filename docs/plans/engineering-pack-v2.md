# Plan: the `software-engineering` pack, second round

Status: phase 1 built, 2026-11-10 (the four skills, the nine audit rules, their tests and evals); phases 2 and 3 open. Written after comparing the pack with Anthropic's `engineering` plugin
(v1.2.0: `architecture`, `code-review`, `documentation`, `incident-response` and six more; 765 lines in
all, templates and checklists, no scripts, no evals). Decisions still open are at the end.

## What the comparison showed

The two sides differ in method, not in topics. Theirs says what a good ADR, review or postmortem looks like
and relies on connectors (source control, tracker, monitoring, chat) to bring the facts in. Ours makes
Claude count with a script, read before it claims, tag what it did not check, and end in one page; a guard
hook enforces the Never rules; evals check that the planted problem is found.

Three jobs are not covered by this pack, or only in part:

| Job | Theirs | Ours today |
|---|---|---|
| Review a change (a diff or a pull request) | `code-review`: four dimensions, a findings table, a verdict | nothing: `code-audit` sends a diff to the built-in `/code-review` |
| Write technical documentation (README, runbook, API reference, onboarding) | `documentation`: document types and five principles, no procedure | nothing: `codebase-map` makes a map, not prose |
| An incident, from triage to postmortem | `incident-response`: SEV levels, status update and postmortem templates, 5 whys | `bug-hunt` finds the cause; nothing for triage, communication or the postmortem |

Theirs also has the security and performance lists (OWASP items, N+1, unbounded queries, resource leaks)
that our `audit-checks.md` lacks, and two output habits worth keeping: "what looks good" and a one-line
verdict in three states.

The rule for this round: take the jobs and the lists, not the method. Nothing here becomes a template Claude
fills from memory; every number comes from a script and every claim from a read or a tag.

## Phase 1: the pack itself

### 1. `change-review` (new): a diff or a pull request

When: before a change is merged. Not for code as it stands (`code-audit`), one failure (`bug-hunt`) or
a planned change (`impact`).

Input: a git range (`main..feature`), a patch file, or a PR number with `gh` present (opt-in, the guard
asks). Optional: the PR description or the ticket text, and what worries the reviewer ("this handles
payments").

Script `diff_facts.py` (stdlib): the files and hunks with line numbers; functions and classes touched
(Python by `ast` on the before and after text; other languages by hunk headers); source files changed
with no test changed; config, migration, dependency and CI files touched; the audit rules run on the
changed lines only (the same `audit_scan.py` rules, so the two skills agree); promises in the PR
description or commit messages (the promise extractor of `audit_scan.py`); size figures. A hit is a
place to read.

Steps: read every hunk, none skipped; for each hunk the four dimensions from `review-checks.md`
(security: injection, authorisation, secrets, path traversal, SSRF, deserialisation; performance: a query
inside a loop, an unbounded read, quadratic work on a hot path, a resource not closed; correctness:
empty input, null, overflow, a race, an error swallowed or re-raised without context, off by one;
maintainability: a second copy of a rule, a name that lies, logic with no test); what the change claims
against what it does; changed code with no test, and the test that would cover it, written out; what
looks good, with file:line, because a reviewer who only lists faults is not read; a verdict in three
states, approve, request changes, needs discussion, with the one sentence that justifies it.

Page: Findings, Claims against the diff (table), Changed code without a test (table and code blocks),
Hunks read (table: file, hunk, lines, dimension that applies), What looks good, Verdict. Stats: files,
hunks, lines added and removed, hunks read of all, findings high, tests touched.

Never: never approves a hunk it did not read; never changes the branch or the PR; never posts a comment
or a review anywhere (connectors are phase 3); never runs the code without a yes.

### 2. `code-audit` (changed): the security and performance lists

`audit_scan.py` moves to `shared/` and gets rules for: SQL built from strings (`sql-concat`), a shell
command with a variable (`shell-input`), a path joined from input and opened without a root check
(`path-from-input`), a literal that looks like a key or token (`secret-literal`), `pickle.load` and
`yaml.load` without a safe loader (`unsafe-load`), an HTTP call whose URL comes from input (`url-from-input`),
a query or an HTTP call inside a loop (`call-in-loop`), a read of a whole table or file with no limit where
the caller is a list endpoint (`unbounded-read`), a resource opened and not closed on every path
(`unclosed-resource`). `audit-checks.md` gets one row per rule with how to confirm it, the fix and the
test. `change-review` uses the same copy, so a rule added once applies to both.

### 3. `docs-draft` (new): technical documentation from facts

When: a README, a runbook, an API reference, an onboarding guide or an architecture document must be
written or brought back in line with the code. Not for a map of an unknown repository (`codebase-map`)
or a design review (`arch-review`).

Input: the repository, the kind of document, the audience, and where it will live. Default: ask for the
kind and the audience.

Script `docs_facts.py` (stdlib): what the code exposes: entry points (console scripts, `__main__`,
argparse subcommands by `ast`, container commands), HTTP routes (decorators and router calls), the
configuration it reads (names only, from `environ`, settings classes and example files), the public
surface (`__all__`, exported names, published messages), the commands the Makefile, `pyproject`, CI
and the README give; what the existing documents mention, so every exposed item is `documented`,
`undocumented` or `stale` (mentioned, no longer in the code). Nothing is quoted from a secret.

Steps: facts; the audience and the first thing that reader needs, in one sentence; a draft where every
command, path, name and number comes from a fact and everything else is tagged [guess], with the
drift table beside it; the document kinds of `doc-kinds.md` (README: what, why, five-minute start,
configuration, how to run and test, how to contribute; runbook: when, access needed, steps, rollback,
escalation; API reference: route, request, response, errors; onboarding: setup, the systems and how they
connect, common tasks; architecture: context, design, decisions, data flow, from an `arch-c4` or
`codebase-map` page when one exists); the draft is written into the repo only after the yes.

Page: the draft (a `code` block in Markdown), Drift (table: item, where in the code, where in the docs,
status), What the draft leaves for a person (list: owners, contacts, policy), Sources (table).

Never: never invents a command, a route, a flag or a number; never documents a secret value; never
writes into the repo before the yes.

### 4. `incident-triage` (new): while it burns

When: an alert fires, production misbehaves, a user reports an outage. Not for a known failing test
with a trace (`bug-hunt` straight away) and not after the fact (`postmortem`).

Input: the alert or report text, log files or a log folder, optionally the repository and a deploy
record. Default: ask for the logs.

Script `incident_timeline.py` (stdlib, read-only, `personal`: the guard redacts e-mail addresses,
IBANs and JMBGs from what Claude sees): one timeline from the logs, the git history and deploy
markers; the first error and the last normal line before it; error rate per minute before and after;
error signatures with the message normalised (numbers and ids replaced) and counted; the components,
endpoints and hosts named in the errors; distinct user or account ids as counts, never as values;
commits and configuration changes in the window before the first error.

Steps: facts from the timeline; severity from `severity.md` (who is affected and how many, is data at
risk, is there a workaround, is it spreading), each criterion with the fact that sets it, so the level
has a reason, not a feeling; impact in one sentence; what changed before the first error, with the
commit and the deploy; mitigation options (roll back the named commit, turn the feature off, scale,
drain), each with the evidence that it would help and what it would cost, none executed; the status
update draft: what is known, what was done, what is next and when the next update comes, facts only;
roles to fill (who leads, who speaks, who fixes); the next call: `bug-hunt` on the first error, with
the exact arguments.

Page: Timeline (steps), Severity (table: criterion, fact, level it sets), Impact, What changed (table),
Mitigation options (table), Status update (code block), Roles and next steps.

Never: never runs anything against production or shared data; never posts a message anywhere; never
names a person as a cause; never shows a personal value from a log.

### 5. `postmortem` (new): after the fire

When: the incident is resolved and the team needs the write-up. Not during (`incident-triage`).

Input: the incident-triage and bug-hunt pages when they exist (their JSON), the logs, the repository,
the time it was detected, mitigated and resolved. Default: ask for the times it cannot read from the
logs.

Script: `incident_timeline.py` again, with `--detected`, `--mitigated`, `--resolved`, so it adds time to
detect, time to mitigate and time to resolve, and the number of errors and affected ids in each phase.

Steps: the timeline reconstructed with a source for every entry; the root cause from the bug-hunt page,
or a stop and the call to run it; contributing factors, each with evidence; the chain of whys, each
link tagged, [guess] where nothing in the logs or the code backs it, and the chain stops at the first
guess instead of inventing a fifth why; what went well and what went poorly, from the facts (detection
delay, rollback that worked, an alert that did not fire); action items, each tied to a factor, with the
check that shows it is done; the postmortem in Markdown for the wiki, roles and not names.

Page: Summary, Timeline (steps with sources), Root cause, Contributing factors, Why chain (table),
What went well and poorly, Action items (table), the Markdown document (code block). Written into a
repo or a wiki only after the yes.

Never: never names a person; never writes a cause it did not read in the bug-hunt page, the logs or the
code; never posts anywhere.

### What changes elsewhere in phase 1

- `README.md`: the software-engineering table, and the line under it that sends diffs to the built-in
  `/code-review` goes.
- `roles/software-engineer.md`: the four new skills.
- `plugins/software-engineering/.claude-plugin/plugin.json`: 0.4.0, ten skills; `marketplace.json`.
- `fixtures/acme-orders`: a feature branch in `history.py` with a planted change (a timeout removed, a
  query built from a string, a test deleted) for `change-review`; its log already fails since 2 October,
  which serves `incident-triage` and `postmortem`; its README already promises what the code does not
  keep, which serves `docs-draft`.
- `tools/selection_cases.json`: eight cases for the new skills, and negatives ("summarise this PR for the
  standup" is not a review).
- Tests: `test_scripts_review.py`, `test_scripts_docs.py`, `test_scripts_incident.py`; `test_skill_files.py`
  covers the new SKILL.md files by itself.
- Evals: two per new skill (the planted problem is found; the Never rule holds) and one for the new
  audit rules.

## Phase 2: `engineering-lead`, the orchestrator

A pack on top of `software-engineering` and `software-architect`, the way `solutions-architect` sits on
the architect packs. Two skills:

- `eng-brief`: reads one request (a bug report, an alert, a pull request, a take-over, a brief) and frames
  it once: what is asked, what is known, which skills run in which order and with which shared facts, and
  the exact calls. Nothing runs here. For an incident the order is `incident-triage`, `bug-hunt`,
  `change-review` of the fix, `postmortem`.
- `eng-digest`: joins the pages of one run into one report with a `join_pages.py` that lists where they
  disagree (a severity set twice, a cause named twice, a time that differs) as places to read; never
  redoes a specialist's work.

Phase 2 starts only when phase 1 has run on a real repository at least once.

## Phase 3: connectors

Opt-in, each behind the guard's network rule: `gh` for the PR diff and for posting a review draft after
the yes; a tracker for linking findings to tickets; a chat for posting the status update after the yes.
Reading is first; posting is last and always after the yes. Not before phases 1 and 2 are used.

## Out of scope

Anthropic's `standup`, `deploy-checklist`, `tech-debt`, `testing-strategy`, `debug` and `system-design`:
`test-gap`, `bug-hunt`, `impact` and `arch-style` already do the parts of them that need counting, and the
rest is conversation.

## Open decisions

1. Names: `change-review`, `docs-draft`, `incident-triage`, `postmortem`. Alternatives: `pr-review`,
   `docs-write`, `incident`, `incident-review`.
2. Whether `incident-triage` and `postmortem` are two skills or one with two modes. Two keeps each
   SKILL.md under 120 lines and lets the guard treat the first as `personal`.
3. Whether `docs-draft` writes the Markdown file itself after the yes or only shows it on the page.
4. Whether the orchestrator is a separate pack (phase 2) or routing lines in each SKILL.md are enough,
   as today.
5. `audit_scan.py` to `shared/`: it changes `code-audit`'s copy too, so its eval must run again.
