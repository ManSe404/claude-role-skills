# acme-assist

Prototype support assistant for the Acme Devices Kestrel coffee machines (K-200, K-300) and the
MF-1 milk frother. Customers ask in the chat widget on the shop, in Serbian or English. The
assistant answers from the manuals and policies in `knowledge/`, checks stock, reads links the
customer sends and can e-mail a follow-up.

Built by Dejan Popov, a contractor, for Acme Devices.

## How it works

- `python -m acme_assist index` splits the Markdown and text files in `knowledge/` into chunks
  and stores their embeddings in Qdrant. The PDF quick-start guides and the safety sheet are kept
  in `knowledge/` for reference.
- The warehouse system exports stock every night to `data/stock_snapshot.csv`. A cron job runs
  `python -m acme_assist index-stock` after the export.
- `POST /chat` takes the customer's message and the conversation so far. The agent answers and
  calls tools as it needs them: `search_manuals`, `check_stock`, `fetch_url` and `send_email`.

## Run

    pip install -e .
    python -m acme_assist index
    python -m acme_assist index-stock
    python -m acme_assist serve --port 8000

Settings come from the environment: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `QDRANT_URL`,
`SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` and `MAIL_FROM`.

    curl -s localhost:8000/chat -H 'content-type: application/json' -d '{"message": "My K-200 shows E3"}'

## Test

    PYTHONPATH=src python -m unittest discover -s tests

## Next steps

Acme's briefs for what comes after the prototype are in `docs/briefs/`.
