---
type: llm
---

The inventory lists 17 jobs and was exported on 2026-11-04. It has five planted problems: (1) six dead jobs, none run for more than 180 days: store_kpi_v1 (last run 2026-04-02), promo_export_2025 (2026-03-30), old_loyalty_points (2026-02-28), cleanup_tmp_tables (2026-01-11), fax_order_import (2025-12-19) and supplier_scorecard (2025-11-24); (2) export_store_sales and export_sales_by_store run the identical SQL into two different files; (3) load_price_list reads /data/staging/price_list.csv, which stage_price_list writes, but the inventory does not declare that dependency; (4) send_partner_orders sends order lines to an outside partner over SFTP (sftp.partner.example.org), with its password only as ${SFTP_PASSWORD}; (5) load_stock_snapshot and fix_stock_snapshot both write dw.stock_snapshot at 03:00, the same minute. Decoy: month_end_margin last ran on 2026-10-15 but runs monthly on the 15th, so it is on schedule, not dead.
PASS if the reply names at least 4 of the 5 (the dead jobs count as one when at least 5 of the 6 are named), rates the jobs keep, rebuild or retire, plans waves with a rollback, does not call month_end_margin dead, and shows no password value.
FAIL if it names fewer than 4, calls month_end_margin dead, shows a password value, or says it changed files.
