# 0001. Scripts count, Claude reads and tags

Date: 2026-11-10, written down from the plan of the second software-engineering round; the packs were built this way
from the first one.

## Status

Accepted

## Context

The skills that existed for the same jobs were templates. Anthropic's `engineering` plugin (v1.2.0) is templates and
checklists with no scripts and no evals, and relies on connectors to bring the facts in. A template says what a good
review, map or decision looks like and leaves the facts to Claude's reading, so numbers are estimated and a claim nobody
checked reads like one that was. Source: [roadmap/engineering-pack-v2.md](../roadmap/engineering-pack-v2.md#what-the-comparison-showed)
and "The shape every specialist follows" in [roadmap/architect-packs.md](../roadmap/architect-packs.md).

## Decision

Every number on a page comes from a script with fixed output: Python 3.11+, standard library only, read-only, JSON on
stdout. Claude reads what the scripts point at before it claims anything, and tags every claim it did not count
`[high]`, `[med]` or `[guess]`. From other skills we take the jobs and the lists, not the method: nothing becomes a
template Claude fills from memory.

## Consequences

- Two runs on the same input give the same numbers, and the tests pin the scripts' output on deterministic fixtures.
- Every skill needs scripts and a fixture to test them on, which costs more to build than a template.
- A script that scans for problems, such as `audit_scan.py`, gives places to read, not findings: Claude reads every hit
  before it claims one.
