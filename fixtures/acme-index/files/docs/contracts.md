# Contracts

What callers of acme-index rely on. A change that breaks one of these needs an ADR first.

## Search

- Re-indexing a document never removes it from search before its new version is stored.
- Search returns at most `limit` chunks, best first.
- A tenant's chunks live in that tenant's SQLite file and nowhere else.

## Answer stream

`Answerer.stream_answer` yields events, each a dict with a `type`:

| type | fields | when |
|---|---|---|
| `token` | `text` | a piece of the answer |
| `end` | | the answer is complete |
| `error` | `message` | the model server failed or sent something unreadable |

Every answer stream ends with exactly one `end` or `error` event. The client shows tokens as they come and closes
the answer on that last event; a stream without one leaves the client waiting.

The model server sends newline-delimited JSON: `{"text": "..."}` for each token and `{"done": true}` at the end.

## Jobs

- `index` and `reindex` jobs carry `doc_id` and `path`.
- A job whose handler returned is done and is never run again.
