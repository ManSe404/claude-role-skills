# Checks for a failed pipeline run

How to go from the error to a cause that is proven, what to rule out, and how to rate what is found.
`run_trace.py` gives the places; the cause is proven by reading the code and the delivered files.

## The cause

**Read the first failed task, not the last.** A run fails at one task; everything after it is skipped
or fails because of it. The trace's `run.first_failed` and `error_parts` give the task, the layer, the
value in the error, the file and line, and the column.

**What changed since the last good run.** A task that worked yesterday and fails today on the same code
failed because its input changed, its code changed, or its environment changed. Check all three:
- input: `changed_since_the_last_good_run.input_files`: rows, columns added or removed, and how each column
  writes its values (`decimal point` 401 against `decimal comma` 1038 is a format change);
- code: `commits_between` (with `--git`); none means the code is not the change;
- environment: a new runtime, a credential, a full disk: only from the error text or the platform's logs.
A cause is proven when the changed input meets the failing line (a decimal comma meets `cast(amount as
numeric)`) and nothing else changed. Say it with the numbers: the value from the error, the rows of the
delivery, the line.

**Retries and later runs.** `same_error_since` lists the runs that failed the same way: a retry on the same
input fails the same way and proves nothing new, but it says how long the failure lasts.

## What it was not

Every suspect gets a line with its numbers. A warning in the same run is not the cause when it also came
on runs that loaded fine (`warnings_in_the_run`: 23 runs with the warning, 21 of them loaded). A late file
the job waited for is not a failure. A safe version of the failing code elsewhere (a file that already
uses the safe parse) is the fix, not a second victim.

## Impact

- Tables not built since the failure: `downstream` gives the dependent jobs, their runs since (skipped,
  failed), their last build against their `sla`, and the documents that name their tables (who reads them).
- Rows held back: the rows read by the failed task; rows quarantined that day.
- Since when: the last good build, in hours or working days late against the service level.

## The same weakness elsewhere

`same_expression_elsewhere` lists every line with the same expression as the failing one. Each is the next
incident when its source changes the same way: list them all, with which already use the safe way.

## Past incidents

`past_incidents` matches the log by the error, the job, the task or the file. A past incident with the
same cause is the strongest finding of all when its fix was applied to one table only: name the fix, where
it is used (`where_those_are_used`, `called_in_the_failing_file: false`) and the item it left open.

## Severity

High: the cause, and every consumer-facing table late or wrong. Medium: the same weakness waiting in
another table, a check that should have caught it earlier. Low: a log or alert that would have named it
sooner.

## Workaround, fixes and drafts

- Workaround: the smallest step that gets today's data in, after a yes (load the day again once the
  fix is in; never edit the delivered file by hand).
- Fix one, narrow: the failing line uses the safe way (effort in hours, risk, the test with the failing
  value).
- Fix two, closing the weakness: every place in the list, a check or contract clause that stops the
  format change at the door, and the open item of the past incident closed.
- E-mail to the consumers: what is missing, since when, when it is expected, nothing about blame.
- E-mail to the source owner: what changed in the delivery (the day, the column, the format, counts),
  and what to agree (announce changes; a contract clause).
- Incident-log entry: in the log's own format and order (what failed, cause, fix, open), dated, written
  only after the yes.
