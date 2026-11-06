# acme-orders

Order intake for the Acme tea shop. Every morning it imports the shop's order export
(CSV, `;` separated), prices each order, stores it in SQLite and serves it over a small
read-only HTTP API. Finance reads the totals.

## Run

    pip install -e .
    python -m acme_orders import data/orders-2026-10-02.csv
    python -m acme_orders check data/orders-2026-10-02.csv
    python -m acme_orders report data/orders-2026-10-02.csv --day 2026-10-01
    python -m acme_orders serve --port 8080

Settings come from the environment (`ACME_DB_PATH`, `ACME_MAIL_API_URL`, `ACME_MAIL_API_KEY`,
`ACME_VAT_RATE`) or from `acme.yaml` (see `acme.yaml.example`).

## Test

    PYTHONPATH=src python -m unittest discover -s tests
