# Runbook: Acme Foods data platform

For whoever is on call. The platform loads the ERP deliveries from `sources/` into bronze, silver and gold tables;
the jobs are in `jobs/`, the code in `pipeline/`, the run records in `ops/`.

## The daily jobs

| job | when | what |
|---|---|---|
| `rebuild_customers` | 04:15 | reloads silver.customers from the ERP replica |
| `load_erp_orders` | daily at 05:00 | loads the ERP order lines into bronze.erp_orders and silver.orders |
| `build_sales_daily` | after load_erp_orders | rebuilds gold.sales_daily; finance reads it at 08:00 |
| `load_erp_finance` | 07:45 | loads the invoices, returns and payments |
| `refresh_stock` | every 5 minutes | refreshes gold.stock_levels from the ERP replica |
| `load_crm` | 07:00, once the CRM is live | loads the CRM customers, contacts and activities |

## Settings

The code reads its settings from environment variables, in `pipeline/config/settings.py`:

- `ACME_WAREHOUSE_URL`: the connection string of the warehouse. Required.
- `ACME_SOURCES_DIR`: where the deliveries land, `sources` by default.
- `ACME_OPS_DIR`: where run records, check results and the quarantine are written, `ops` by default.
- `ACME_ALERT_EMAIL`: who gets the failure e-mails.

## When a job fails

1. Find the failed task and its error: `make status JOB=load_erp_orders`, or the last lines of `ops/runs.jsonl`.
2. Look in `ops/incident-log.md` for the same error.
3. Fix the cause and run the job again: `make run JOB=load_erp_orders`.
4. To load a past delivery again: `make backfill DATE=2026-10-01`.
5. Run the checks of a layer: `make dq LAYER=silver`.
6. Write the incident in `ops/incident-log.md`, newest first.

## Rows in quarantine

Rows that break a rule in `checks/quarantine.yaml` are moved to `ops/quarantine.jsonl` and stay out of silver. Fix
the reference data or ask the source to resend, then load the delivery again.
