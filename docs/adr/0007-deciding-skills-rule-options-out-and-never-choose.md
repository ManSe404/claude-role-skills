# 0007. Deciding skills rule options out and never choose

Date: 2026-11-09, agreed with Stefan in the plan of the architect series.

## Status

Accepted

## Context

A deciding skill (what an AI solution, a data platform, a system, a cloud design or a model should be) can climb to a
bigger option than the brief needs. Source: "Settled early" and "The shape every specialist follows" in
[roadmap/architect-packs.md](../roadmap/architect-packs.md#settled-early-because-they-are-expensive-to-change-later).

## Decision

Every deciding skill starts at the bottom of a ladder and climbs only for a requirement it can name. Its rule script
eliminates options and never chooses; Claude weighs what is left and writes a `decision` block. Every architect fixture
includes a brief where the right answer is boring.

## Consequences

- An eval on the boring brief catches a skill that overbuilds (the `*-does-not-overbuild` cases).
- The rules are judgements written into the scripts, such as the thresholds in `cloud_rules.py`, and are printed in the
  output so a page can show them.
