# acme-index

Index documents for search and stream answers over them: a small Python library and a worker, written by the
search team of Acme Index in Novi Sad. Python 3.12, standard library only.

## What it does

- Parses `.txt` and `.md` files, and `.docx` files when `python-docx` is installed, into paragraphs.
- Splits the text into overlapping chunks, embeds them through the embedding service and keeps chunks and vectors
  in SQLite, one file per tenant.
- Finds the chunks closest to a question and streams an answer from the model server.

Parse errors are reported, never hidden: a file the parser cannot read fails with its path and the reason, and
does not end up in the index as an empty document.

## Worker

The worker drains the job queue of one tenant:

    python -m acme_index.worker acme-index.json

The config file is JSON:

| key | required | meaning |
|---|---|---|
| `database` | yes | folder that holds the SQLite files |
| `embedder_url` | yes | base URL of the embedding service |
| `tenant` | no | name of the tenant's SQLite file, default `default` |
| `backoff_seconds` | no | seconds to wait before the first retry, default 2 |

A job is retried at most 3 times, then moved to the dead-letter table. The table keeps the job with its last error,
so an operator can look at it and queue it again.

## Development

    PYTHONPATH=src python -m unittest discover -s tests

Rules for changes are in `CLAUDE.md`, what callers rely on is in `docs/contracts.md` and the decisions are in
`docs/adr/`.
