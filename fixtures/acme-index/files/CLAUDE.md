# acme-index

Rules for everyone who changes this repo, people and agents alike.

- Python 3.12. Modules import with the standard library only; an optional package is imported inside the function
  that needs it.
- Every outbound call has an explicit timeout.
- Errors name the document id or the path. Raise `IndexingError` or a subclass; do not return an empty result in
  place of an error.
- SQL takes parameters, never string formatting.
- Read `docs/contracts.md` before changing behaviour callers see, and the ADRs in `docs/adr/` before changing what
  they decided.
- Tests need no network: `PYTHONPATH=src python -m unittest discover -s tests`.
