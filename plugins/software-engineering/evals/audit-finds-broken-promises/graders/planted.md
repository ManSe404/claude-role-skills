---
type: llm
---

The code has seven planted bugs, each breaking a promise in its docs: (1) `store.py` reindex deletes a document's chunks, then calls the embedder, then inserts, so an embedder failure removes the document from search; (2) `plans.py` finish reads `run.get("_digest")`, a key nothing writes (the run dict uses "digest"), so a changed plan's digest is never stored; (3) `chunks.py` builds chunk ids with the built-in `hash()`, which differs between processes, so ids are not deterministic; (4) `parse.py` catches every exception and returns an empty list, hiding parse errors and a missing dependency; (5) `embedder.py` calls `urlopen` without a timeout; (6) `answers.py` catches only `URLError`, so a malformed JSON line ends the stream with no final event; (7) `worker.py` counts retries only for embedder errors, so any other error retries forever.
PASS if the reply names at least 5 of the 7 with the right file, and does not report any of these as a bug: the `except Exception` in plans.py that re-raises as IndexingError, the tenant default in worker.py, the bounded retry loop in embedder.py, or the delete and insert inside one transaction in store.py set_metadata.
FAIL if it names fewer than 5, reports one of those four as a bug, or says it changed or added files in the repo.
