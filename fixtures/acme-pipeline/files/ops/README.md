# ops: what the platform writes about itself

The scheduler, the runner and the billing export write these files on the platform host. They are kept for 31 days
and are not in git; only this file and the incident log are.

| file | one line or row per | fields |
|---|---|---|
| `runs.jsonl` | task of a run | `run_id`, `job`, `task`, `layer`, `attempt`, `start`, `end`, `status` (success, warning, failed, skipped), `rows_read`, `rows_written`, `rows_changed`, `error`, `message` |
| `checks.jsonl` | check result | `date` (the run date), `check`, `table`, `layer`, `status` (pass, warn, fail), `failing_rows` (null for freshness checks), `note` |
| `quarantine.jsonl` | row moved to quarantine | `date`, `table`, `rule`, `row_id`, `value` (the value that broke the rule), `run_id` |
| `deliveries.jsonl` | delivered file | `source`, `file`, `arrived_at`, `rows` |
| `usage.csv` | job or cluster and day | `date`, `resource_type` (job, cluster), `resource`, `cluster`, `compute_hours`, `compute_eur` |
| `storage.csv` | table | `table`, `layer`, `gb`, `eur_per_month` |
| `query_log.csv` | consumer, table and day | `date`, `consumer`, `table`, `queries` |
| `incident-log.md` | incident | what failed, the cause, the fix, what is still open |

Prices in the billing export: the `etl` cluster costs 2.00 EUR per compute hour, the `dev-adhoc` cluster 1.20 EUR
per hour it is up, storage 0.04 EUR per GB and month. A job's compute hours are node hours, so they can be more than
the job's wall time.

Times are local (Europe/Belgrade) with their offset. A task with status `skipped` did not run because a job it
depends on failed. Jobs with `record_runs: failures` write only their failed runs here.
