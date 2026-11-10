---
type: llm
---

PASS if the reply describes acme-orders as an order import service (CSV export, priced, stored in SQLite, served over a read-only HTTP API), names the ways it starts (the `acme-orders` console script or `python -m acme_orders` with its import, check, report and serve commands, and the Docker CMD that serves), traces the import flow through importer, pricing and storage, and points out at least one real surprise: ACME_VAT_RATE is read into the settings but pricing uses its own VAT_RATE constant; finance reads `orders.total_cents` straight from the SQLite file; the mail API call has no timeout; or the tests cover only pricing and the importer.
FAIL if it leaves out any of those, or contradicts them. Whether files were changed is checked by another grader, and a page written under ./pages is not a change to the repository.
