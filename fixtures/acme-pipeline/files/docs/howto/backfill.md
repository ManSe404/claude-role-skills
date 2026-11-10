# How to load a past delivery again

When a day was loaded wrong or not at all, and its files are still in `sources/<source>/<delivery date>/`:

1. Make sure the files of that day are the corrected ones.
2. Run the job for that day: `make backfill-day JOB=load_erp_orders DATE=2026-10-01`.
   The loaders replace the day's partition in bronze and the silver SQL deletes the day before inserting it, so
   running a day twice does not double it.
3. Rebuild what depends on it: `make run JOB=build_sales_daily`.
4. Check the new run records: `make status JOB=load_erp_orders`.

`sources/` keeps the last three deliveries per source. An older day has to be asked from the source again.
