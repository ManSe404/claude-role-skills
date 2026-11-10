# What to look for in a platform's bill

`cost_breakdown.py` prints the money and four kinds of candidates. A candidate is a place to read, never a
finding: each one is confirmed in the job file, the SQL and the records before it goes on the page.

| Waste | The script's field | Confirm by | The cut | Saving a month |
|---|---|---|---|---|
| A table nobody reads | `candidates.unread_tables` | no query in the log and no SQL reads it; search the repository for the name (exports, notebooks, BI files, dbt sources); read the comments of the SQL that made it, they often say why it exists and when it may go | drop it once the person named in the comment or its maker signs off; keep a dated export if the sign-off asks for one | its `eur_per_month` plus the compute that still writes it |
| A full reload of a table that barely changes | `candidates.full_reloads`, `barely_changes: true` | the job says `load: full` or the SQL truncates or replaces the table; rows changed stay under the share on every run; find a column that marks a change (`updated_at`, a change number) | load only the changed rows: a merge on the key, filtered on the change column; a full reload once a week to catch deletes | the job's cost minus the cost of the smaller load; when unsure, say "most of" the job's cost and give the share of rows that change |
| A schedule faster than the reads | `candidates.schedules`, `faster_than_reads: true` | runs a day against the most reads a day of the tables it writes, by consumers and by other jobs; read what the readers need (the product document, an SLA, the app that reads it) | a schedule that matches the reads, or a refresh on demand before the read | `eur_per_run` × the runs that stop |
| Compute that runs with no jobs | `candidates.compute_without_jobs` | the cluster is billed but no job definition and no job line in the export uses it; days up all 24 hours; weekend days | auto-stop after idle minutes, or a schedule that stops it at night and at weekends; ask who uses it before stopping it | the hours it is up with nobody on it × its rate; the weekend cost is the floor |

## What looks like waste but is not

- **The most expensive job whose table is read all day.** A gold table rebuilt once a day and read every hour
  by several consumers is the platform doing its job. List it under money well spent with its cost a read.
  A cheaper build may still be possible, but it is an improvement to weigh, not a cut.
- **A bronze or staging table with no consumer in the query log.** The pipeline itself reads it: the script
  counts SQL readers (`read_by_sql`, `read_by_jobs`). It is unread only when nothing reads it at all.
- **A table read rarely but on purpose.** A month-end table read once a month is read as often as it is
  needed; compare the schedule with the cadence of the reads, not with a daily rhythm.
- **A full rebuild where a real share of rows changes.** Above the share, an incremental load saves less
  and adds risk; give the numbers and leave it.
- **Rows changed missing from the run records.** The script says so (`note`); without them a reload cannot
  be called needless. Say what record would settle it.

## How the money is counted

- Compute is what the usage export says, summed exactly in cents. A job's compute is split over the tables
  it builds by their share of the run time in the run records, evenly when there are none; the parts add
  up to the job's cost to the cent.
- Storage is the monthly figure of the storage table. Over a period of 28 to 31 days it counts as one month;
  otherwise the script prorates it and says so.
- The total is compute for the period plus storage for it. `adds_up` must hold before any figure is used.
- A saving is per month and is either a figure the script printed (a table's storage, a cluster's weekend
  cost) or a product of them with the formula on the page.

## How a cut is written

`where` is the file and line that proves it (the job's schedule line, the SQL that truncates, the row of the
usage export). `evidence` gives the records' numbers: "rebuild_customers wrote 750,333 rows over 31 runs and
changed 347 (0.046 %; at most 17 in a run); it cost EUR 46.14". `fix` is the change and the saving a month,
and names who must agree. Severity follows the money and the certainty: high when it is the largest share of
the bill or certain and easy, medium for a confirmed cut under a few percent, low for a lead that needs a
record the platform does not keep.
