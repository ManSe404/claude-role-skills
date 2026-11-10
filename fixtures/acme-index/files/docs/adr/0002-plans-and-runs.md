# ADR 0002: Ingestion plans and runs

Status: accepted, 2026-08-05

## Context

A source is ingested by a sequence of steps (fetch, parse, index). When a source looks wrong in search we need to
know what its last run did, and whether two runs did the same work.

## Decision

- A plan is the ordered list of steps for one source. Its digest is the SHA-256 of the steps as canonical JSON.
- A run is a row in the `runs` table: the plan, its digest, the status and when it started and finished.
- Every run stores the digest of the plan it actually executed. When a step is dropped during a run because no
  handler exists for it, the stored digest is the digest of what ran, not of what was planned.
- A failed step fails the run, and the error is raised with the name of the step.

## Consequences

- Two runs with the same digest did the same work, so a run can be skipped when the last successful run of the
  source has the digest of the new plan.
