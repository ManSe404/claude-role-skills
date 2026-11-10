# Checks for the checks

What makes a check worthless, how to confirm it, how to rate it, and how to set a table's verdict.
`quality_summary.py` counts; reading the definitions proves.

**A check that warns every day.** A warning on every day of the period, with the failing rows in a narrow
band, is noise nobody acts on: it hides the day it gets worse. Confirm: `warn_every_day` with its
`thresholds`: a `fail_if` far above the observed rows never fires. Fix: a threshold just above the
steady level, or fix the rows and make it fail. Rate medium; the table is "use with care" while it warns.

**A check that cannot fail.** A query whose condition is never true (`amount < amount`, `1 = 0`, a
column both null and not null) returns no rows whatever the data, so it passes forever. Confirm:
`cannot_fail` with file:line, and read the condition. Its record of passes proves nothing. Rate high: the
table looks guarded and is not. Fix: the condition meant (`amount <= 0`) and a test case with a bad row.

**A check never tried on bad data.** A check that never failed is only worth something if it was once
shown to fail on rows that should fail it. Confirm: `never_failed` with `test_case`, and
`without_a_test_case`. A never-failed check with no test case is unproven; with one, say when it was tried
and on what. Rate medium, high together with "cannot fail".

**A single failure with a reason.** A check that failed once with a note that explains it (a holiday, a
planned outage) and passed the next day is the check working. Confirm: `single_failures` with the note
and the next result. It goes under "what looked wrong but is fine", never in the findings.

**Freshness against the service level.** A table with an `sla` that was not built in time. Confirm:
`freshness` with `failed_on` from the checks, `days_not_built_by_the_sla` from the runs, `last_built`.
Rate high for a table people read every morning; say who reads it (job definition, product document).

**The quarantine.** Rows a rule moved out are rows missing from a table. Read the rule per day: a step
change (`step_change`: a few rows a day, then a hundred) means a new kind of row, not noise. Read the
values behind it (`values`, `in_reference`): a store id the reference table lacks is a missing reference
row, and every order of that store is missing from silver and gold until it is added. Say the rows, the
days, the first day, the value, and which tables are short. No check watches the quarantine when
`quarantine_watched_by_a_check` is false: rate the jump high.

**Definitions without results, results without definitions.** A check that is defined and never ran,
or a result of a check nobody can read: say both.

## Verdicts

Per table, on the last day of the period:

| Verdict | When |
|---|---|
| do not use | a check failed, its freshness failed, or its last build failed or was skipped |
| use with care | a check warned, a check of it cannot fail or was never tried on bad data, its quarantine jumped |
| safe | every check of it passed, could have failed, and was tried on bad data |

The script gives a first verdict with reasons; adjust it with what you read and say why. Never call a
table safe on passes alone.

## How a finding is written

`where` is the check's definition (file:line) and, for a result, the line in the results file. `evidence`
counts: "warned on 31 of 31 days with 37 to 41 rows; `fail_if: rows > 500` never fires". `fix` names the
change to the check, the threshold, the test case or the reference row.
