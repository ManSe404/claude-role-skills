# 0003. A `facts` section on every page

Date: 2026-11-09, agreed with Stefan as the first of the decisions taken early in the architect series.

## Status

Accepted

## Context

`solutions-architect` was to come last and join the specialists' pages. It cannot do that from text written for
people: it needs regions, data classes, components, dated costs, decisions and assumptions in one shape. Without one
shape from the start, every pack would have been reworked at the end. Source: "Settled early" in
[roadmap/architect-packs.md](../roadmap/architect-packs.md#settled-early-because-they-are-expensive-to-change-later);
the format is in [roadmap/data-architect.md](../roadmap/data-architect.md#facts).

## Decision

A page's JSON carries a top-level `facts` object in one shape, validated by `render_page.py` and not drawn. A later
skill reads an earlier page's `facts`, never its prose.

## Consequences

- `solution-blueprint` joins the specialists' pages through `join_facts.py`, and a workflow step reads the previous
  step's page the same way; `chain_status.py` takes each step's open items from `facts.open`.
- Seven skills built before the rule reached them (`codebase-map`, `impact`, `bug-hunt`, `test-gap`,
  `dependency-audit`, `code-audit`, `ai-review`) write no `facts` yet, so their open items do not reach a chain page.
