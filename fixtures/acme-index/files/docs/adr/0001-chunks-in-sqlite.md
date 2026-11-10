# ADR 0001: Chunks and vectors in SQLite, with deterministic ids

Status: accepted, 2026-06-02

## Context

A tenant has at most a few thousand documents. Search has to run next to the worker, on one machine, without
another service to operate.

## Decision

- Each tenant gets one SQLite file that holds its chunks and their vectors. Search is brute-force cosine similarity.
- Chunk ids are deterministic; re-indexing overwrites, never duplicates. An id is built from the document id, the
  position of the chunk and a digest of its text, so the same input gives the same id in every process.
- Vectors are stored as JSON text. They are small, and the file stays readable in the sqlite3 shell.

## Consequences

- Search reads every chunk of the tenant. Above about 50,000 chunks per tenant we revisit this decision.
- Changing how ids are built means re-indexing every tenant, so it needs a new ADR.
