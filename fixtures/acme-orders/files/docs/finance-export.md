# Finance export

Finance's month-end job does not call the API. It reads `orders.total_cents` straight from
the SQLite file, which is copied every night to the finance share, and sums it per day.

`total_cents` is the order total with VAT after the discount, in euro cents. Do not change
what it means without telling finance first (owner: finance-ops@example.com).
