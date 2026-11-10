# The old cron estate

Before the platform, Acme's data ran as cron jobs on the old reporting host: shell scripts and SQL against the old
warehouse (`dw.*`). Everything still running there has to be moved onto the platform or retired.

- `inventory.csv` was exported from the cron host on 2026-11-04 at 06:00: every job in the crontab, its schedule,
  the owner on record, its last successful run, what it writes, and the jobs it waits for (`depends_on`).
- `jobs/` holds each job's script as it was on the host. Secrets are not in the scripts; the host's environment
  sets them.

Some owners on record have left the company.
