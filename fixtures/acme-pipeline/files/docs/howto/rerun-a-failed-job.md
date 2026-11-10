# How to rerun a failed job

1. See which task failed and why: `make status JOB=<job>`. Each line is one task of a run, with its error.
2. A task that waited for a file and timed out needs only the file: once it is in `sources/`, run the job again
   with `make run JOB=<job>`.
3. A task that failed on the data (a cast, a check that fails) fails again on the same data. Find the cause first,
   in the delivered file and in `ops/incident-log.md`.
4. After a successful rerun of `load_erp_orders`, run `build_sales_daily` too: it does not start by itself after a
   manual run.
