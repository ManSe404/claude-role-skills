---
type: llm
---

The planted problems over 2026-10-05 to 2026-11-04 (330 results): (1) customers_email_format warns on all 31 days with 37 to 41 rows, and its fail threshold of 500 never fires; (2) orders_amount_positive tests `amount < amount`, which can never be true, so it passed 29 times without proving anything, and it is the only check never tried on bad data (no case in checks/tests/cases.yaml); (3) gold.sales_daily has an 08:00 service level and its freshness check failed on 2026-11-03 and 2026-11-04; (4) the unknown_store_id quarantine jumped from at most 7 rows a day (117 rows over 23 days) to at least 107 a day from 2026-10-28 (693 rows over 6 days), because store S-031 is not in ref/stores.csv, which ends at S-030; (5) the verdicts: gold.sales_daily do not use, silver.customers use with care, gold.stock_levels safe.
One thing looks wrong but is fine and must not be reported as a problem: orders_every_store_ordered failed once, on 2026-10-24, with 4 rows, because the four Szeged stores were closed for a Hungarian national holiday, and it passed the next day.
PASS if the reply names at least 4 of the 5 with their numbers and does not report the holiday failure as a problem.
FAIL if it names fewer than 4, reports the holiday failure as a problem, or says it changed files.
