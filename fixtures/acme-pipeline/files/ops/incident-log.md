# Incident log

Newest first. Each entry: what failed, the cause, the fix and what is still open.

## 2026-09-14: load_erp_finance failed in silver.invoices

- What failed: the 07:45 run of `load_erp_finance` stopped at task `silver.invoices` with
  `invalid input syntax for type numeric: "1.234,50"`. silver.invoices and the cash plan were a day late.
- Cause: the ERP vendor's update 2026.9 switched the invoice export to the Serbian number format, a decimal comma
  and a dot between thousands. `pipeline/silver/invoices.sql` cast the delivered text straight to numeric.
- Fix: a safe parse, `util.parse_amount` in `pipeline/functions/parse_amount.sql`, reads both formats.
  `silver.invoices` uses it since 15 September; the delivery of 14 September was loaded again the same day.
- Open: check the other ERP amount columns.

## 2026-08-18: load_erp_finance failed in bronze.erp_payments

- What failed: `payments.csv` was missing from the delivery of 18 August; the loader stopped with a file not found.
- Cause: an outage at the ERP vendor; the file came at 11:20.
- Fix: the job was run again by hand at 11:30.
- Open: nothing.
