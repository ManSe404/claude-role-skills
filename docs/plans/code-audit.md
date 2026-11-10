# code-audit, and arch-review as a design review

## Why

A run on a real repository asked `arch-review` to review code. The bugs that mattered there, such as a value read
from a key that is never written or a re-index that deletes before it writes, are findings of a code review, and the
packs had no skill for one. `arch-review` had been asked to do a job it was not written for.

Stefan's decisions, the same day:

- A new skill in software-engineering reviews code as it stands. Its name is `code-audit`, so it does not share a name
  with the built-in `/code-review` and the org's `engineering:code-review`, which both review a change.
- `arch-review` keeps its name and reviews design documents only: a proposal, a target architecture, ADRs, before the
  system is built. Code that exists goes to `code-audit` or `codebase-map`.

The structure of existing code (cycles, layer breaks, hidden coupling, hot spots) had no other home, so it became the
second part of `code-audit`, with the shared `code_graph.py`. `arch-evolve` still measures today's structure, but only
to plan a move to a target.

## Which review takes which request

| Request | Skill |
|---|---|
| the code as it stands, a module or a repository: bugs, failure handling, promises the code breaks, its structure | `code-audit` |
| a diff, staged changes or a pull request | not ours: the built-in `/code-review`, `engineering:code-review`, or a team's own pull-request reviewer |
| one known failure: an error, a stack trace, a failing test | `bug-hunt` |
| one planned change: what it reaches | `impact` |
| a design not built yet: proposal, target architecture, ADRs | `arch-review` |
| writing or weighing one decision record | not ours: `engineering:architecture` |
| an AI or LLM solution, a data platform, infrastructure code | `ai-review`, `data-review`, `cloud-review` |

Each skill's text says where the neighbouring requests go. `tools/selection_cases.json` holds prompts for every row,
including three where none of ours may fire (a pull request, staged changes, an ADR to write).

## Measuring it against the account's own plugins

The selection check loads every pack from this repository. A pack loaded from anywhere else (an installed copy) makes
that case an error, and a skill picked from another plugin keeps its full name in `picked_full` and is counted in
`picked_elsewhere`. Run on an account whose own plugins include `engineering`, the same run shows which requests those
plugins take from ours and which of ours take theirs. Not run yet.
