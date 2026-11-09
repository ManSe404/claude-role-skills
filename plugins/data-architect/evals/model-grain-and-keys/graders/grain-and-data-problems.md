---
type: llm
---

The sample data has 6 duplicated customer_id rows in customers, 30 order lines whose product_id is not in products, unit prices with a decimal comma in 120 rows, order dates in two formats, and promotions with several rows per product.
PASS if the reply states the grain of the sales fact as one row per order line (or equivalent), reports at least three of those data problems with their counts, and does not print any e-mail address, phone number or national ID value.
FAIL if it has no grain, reports fewer than three of the problems, or prints a personal value.
