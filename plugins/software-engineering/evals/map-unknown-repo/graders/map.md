---
type: llm
---

PASS if the reply describes acme-orders as an order import service (CSV export, priced, stored in SQLite, served over a read-only HTTP API), names the ways it starts (the `acme-orders` console script or `python -m acme_orders` with its import, check, report and serve commands, and the Docker CMD that serves), traces the import flow through importer, pricing and storage, and points out at least one real surprise: ACME_VAT_RATE is read into the settings but pricing uses its own VAT_RATE constant; finance reads `orders.total_cents` straight from the SQLite file; the mail API call has no timeout; or the tests cover only pricing and the importer.
FAIL if it states behaviour the code does not have, or if it changed files in the repository.
