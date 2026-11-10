# What to look for in an old estate

`estate_inventory.py` reads the inventory and every script. Its output is a list of places to read; each
signal is confirmed in the script itself before it goes on the page.

| Signal | The script's field | Confirm by | What it means for the move |
|---|---|---|---|
| A dead job | `status` = `dead`: three or more missed runs and silent longer than `--dead-after` days | the last run against the schedule; whether anything still reads what it wrote (`links`, `outputs_no_job_reads`); the owner on record | retire, after the owner or a consumer confirms; archive the script and the last output |
| A stopped or late job | `status` = `stopped` or `missed` | the host's log, if any; a job that missed one run may just be slow | ask before the wave; never move a job whose state nobody knows |
| A job on schedule that looks idle | a monthly or weekly cadence with an old last run that equals `last_due` | the cadence; `next_due` | keep: it is on time, it just runs rarely |
| Identical scripts | `identical_scripts`, `near_identical_scripts` | diff them; who reads each output (two exports for two teams is still one query) | keep one job, deliver both outputs from it or point the second team at the first file |
| A link the inventory does not declare | `undeclared_links` | the line that writes the path or table and the line that reads it; the inventory row without the dependency | the new platform needs the dependency, or the reader runs on stale or half-written data; move writer and reader in one wave |
| An outside consumer | `outside_consumers` | the host, what is sent, the login (placeholder only), the partner's contact | the riskiest part of a move: agree the switch date with the partner, test with them, never in the first wave |
| An outside input | `outside_inputs`: file shares, source databases, tables no job writes | where it comes from and who keeps it | the new platform needs access to it before the wave that reads it |
| An output nobody inside reads | `outputs_no_job_reads` | exports in folders other teams pick up; tables only reports read | find the reader before moving or retiring it |
| Two jobs writing one target at the same time | `same_target` with `at_once: true` | what each does to the table (a reload and an update at the same minute race; the result depends on which ends last) | rebuild as one job, or one after the other with a declared dependency |
| A credential in a script | `credentials` | only `placeholder` is ever shown; `literal: true` means a value is written in the script, and it is reported as hidden | the secret moves to the new platform's secret store; a literal one is rotated |

## Ratings

- **Keep:** runs, is read, does one thing, and moves as it is.
- **Rebuild:** runs and is read, but moving it as it is would carry a defect: a hidden link, a race with another
  job, a copy of another job, a file hand-off that becomes a table, a credential in the script.
- **Retire:** dead, or a copy whose readers can use the other output, or an output nobody reads. Retire only
  after the owner or the readers confirm, and keep the script and the last output.

## Waves

- A wave is a group from `groups`: jobs linked by data move together. Inside a wave, `order` puts writers before
  readers.
- Start with a small, internal, well-read group; leave outside consumers and month-end jobs for later waves, and
  plan a month-end job's wave so its parallel run covers one real run.
- Acceptance numbers per wave, agreed before the parallel run: per day, the row count and the sum of the main
  amount equal between the old and the new output; files equal by row (sorted) or by a hash of each row; the
  delivery time no later than today's. Say the number of days compared.
- Parallel run: both run, the new output goes nowhere outside, a daily comparison of the acceptance numbers.
- Cutover: the old job is disabled, not deleted; consumers are pointed at the new output.
- Rollback: re-enable the old cron line and point the consumers back; the old target stays untouched until the
  wave is signed off.

## Severity of a finding

- **High:** a move that would silently change or stop data someone depends on: an outside consumer, a hidden
  link, two jobs racing on one table.
- **Medium:** work that would be wasted or a decision that needs an owner: dead jobs, copies, unknown readers.
- **Low:** hygiene: owners who have left, schedules nobody can explain, scripts no inventory lists.
