# 0008. Descriptions name their subject, checked with every pack loaded

Date: 2026-11-09, agreed with Stefan in the plan of the architect series.

## Status

Accepted

## Context

Claude picks a skill from its `description` and `when_to_use` alone. Five skills match "draw the architecture":
`codebase-map`, `ai-architecture`, `data-map`, `arch-c4` and `cloud-map`. `claude plugin eval` loads one pack at a time,
so it cannot show which skill Claude picks among all of them. Source: "Settled early" in
[roadmap/architect-packs.md](../roadmap/architect-packs.md#settled-early-because-they-are-expensive-to-change-later).

## Decision

Every description names its subject (a repository, an AI solution, a data platform, a system's structure, cloud
infrastructure), and `when_to_use` says where a neighbouring request goes. `tools/selection_check.py` loads every pack
and checks which skill Claude picks for each prompt in `tools/selection_cases.json`, including prompts where none of
ours may fire.

## Consequences

- The selection check makes real model calls and is run by hand.
- `description` and `when_to_use` stay under 400 characters together, because with many skills installed Claude Code
  cuts long descriptions.
