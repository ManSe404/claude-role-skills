# 0005. code-audit reviews code, arch-review reviews designs

Date: 2026-11-10, Stefan's decision the day of the run that showed the gap.

## Status

Accepted

## Context

On a real repository `arch-review` was asked to review code. The bugs that mattered there, a value read from a key that
is never written and a re-index that deletes before it writes, were findings of a code review, and the packs had no
skill for one. Source: [roadmap/code-audit.md](../roadmap/code-audit.md).

## Decision

A new software-engineering skill, `code-audit`, reviews code as it stands, including its structure (cycles, layer
breaks, hidden coupling, hot spots) with the shared `code_graph.py`. Its name differs from the built-in `/code-review`
and the org's `engineering:code-review`, which review a change. `arch-review` keeps its name and reviews design
documents only, before the system is built.

## Consequences

- Each skill's text says where the neighbouring requests go, and `tools/selection_cases.json` holds prompts for each.
- A diff or a pull request, at first left to other plugins, went to `change-review` once it was built in the second
  software-engineering round.
