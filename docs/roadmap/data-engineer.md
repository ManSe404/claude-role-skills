# data-engineer pack

## Why

The data packs cover deciding a platform (data-architect), the numbers on top of it (data-analyst) and models
(data-scientist). Nothing covers running a platform: a new source arriving, the contract with it, a failed run, the
checks, the money, an old estate to move, the tables served to consumers. This pack covers those
jobs, built the way the other packs are built. Stefan's choice, 2026-11-10: seven jobs. A runbook skill was planned
and dropped the same day: `docs-draft` (software-engineering) writes runbooks from the code, and it is to read job
definitions and schedules too, so one skill covers every runbook.

## Skills

| Skill | The job | Its own script |
|---|---|---|
| `source-profile` | a new source, feed or file set, understood before any contract or pipeline: format, schema and drift, quality, bad records, orphans, gaps and deletes, personal data, compared with the vendor's metadata | `source_format.py` (delimiter, quoting, encoding, null tokens, decimal separator, date formats, placeholder values such as 9999-12-31, schema drift between files, business days without rows, delete markers) and the shared `data_profile.py` |
| `source-contract` | the data contract with the source system: format, schema, keys, quality rules, delivery window, owner, change process; agreed with the source owner, conflicts with the metadata and the observed deliveries named | `contract_check.py` (a contract file against the profile, the metadata document and the delivery log: missing or extra columns, types, keys, rules the data already breaks, delivery times) and `data_profile.py` |
| `pipeline-incident` | a failed run, from the error to the root cause, the workaround, two fixes with their effort, other tables with the same weakness, email drafts to consumers and the source owner, and the incident-log entry (written only after the yes) | `run_trace.py` (the run layer by layer from the run records, the first failed task and its error, the check results and quarantine of that run, what changed against the last good run, matching past incidents) and `data_profile.py` |
| `data-quality` | which checks passed, warned and failed over a period, what was quarantined and why, freshness against each table's service level, checks that warn every day, checks that never failed and when they were last tested, and a verdict per table: safe, use with care, do not use | `quality_summary.py` and `data_profile.py` |
| `data-cost` | where the compute and storage money goes, per job, pipeline and table, and what to cut: tables nobody reads, full reloads of tables that barely change, schedules faster than anyone reads, compute that never stops | `cost_breakdown.py` (a usage or billing export and the query log) |
| `data-migration` | an old estate of jobs and tables inventoried, rated (keep, rebuild, retire) and planned into waves, with acceptance numbers, the parallel run and the rollback | `estate_inventory.py` (a job inventory and the job scripts: last run, dependencies read from the scripts, duplicates, dead jobs, outside consumers) |
| `data-product` | everything a consumer of one served table needs: what it is, its grain and model, the metric definitions, starter queries, quality and freshness, releases and the data contract; conflicts between the documents named | `product_facts.py` (a served table's columns, grain, consumers from the query log, the checks that cover it, its freshness, the definitions found in docs and reports) and `data_profile.py` |

Out of scope, and where it goes:

| Request | Goes to |
|---|---|
| what a change to a table or column reaches | `impact` (software-engineering) and `data-map` (data-architect) |
| two numbers that should agree | `number-reconcile` (data-analyst) |
| a pull request or diff | a change review (built-in `/code-review`) |
| the platform's models and loads reviewed for design mistakes | `data-review` (data-architect) |
| tests to write first | `test-gap` (software-engineering) |
| a quick look at a table, one-off SQL, charts, dashboards | not ours: the Anthropic `data` plugin or plain Claude |
| the runbook or how-to guides of a platform | `docs-draft` (software-engineering) |
| a live outage of a service, from its logs | `incident-triage` (software-engineering); the write-up after it, `postmortem` |

## Shape, as in every pack

- `SKILL.md` in the house format, under 120 lines; `description` says what it does in one sentence and `when_to_use`
  says when, in one or two sentences, starting "Use when" or "Use before", with where a neighbouring request goes.
  Together under 400 characters.
- The `hooks:` block with `guard.py`; the skills that ship `data_profile.py` get `personal` (raw reads of files with
  personal columns refused, e-mail, IBAN and JMBG removed from tool output).
- Scripts: stdlib, read-only, JSON on stdout, tests in `tests/test_scripts_engineer.py`.
- One page per run, drawn by `render_page.py`; `references/example.json` from a headless run on the fixture,
  checked by hand.
- One eval case per skill, graded against the planted problems; a `skill-fired` grader and a check that the
  skill's script ran.
- Stack neutral. The fixture uses plain SQL, Python loaders, YAML job definitions and JSON lines run records, so no
  vendor is assumed; a script reads the common export shapes and says which ones it understood.

## Fixture `acme-pipeline`

A made-up food distributor, Acme Foods in Novi Sad, with a small platform: deliveries land from an ERP and a CRM,
SQL builds bronze, silver and gold tables, a scheduler runs the jobs, checks run after each layer, rows that break a
rule go to quarantine. Fictional names, `example.com` addresses.

What it holds: source deliveries per day (and one new source that has just arrived), the vendor's metadata
document, existing contracts, the pipeline code and job definitions, run records, check results, the quarantine, an
incident log, a usage export, a query log, an inventory and scripts of the old cron estate, the served gold tables
with their consumer documents, and a runbook with how-to guides (its planted drift is kept for `docs-draft`). Each skill has two to six planted problems and at
least one decoy that looks wrong but is fine, listed in `tests/test_fixture_acme_pipeline.py` as `PLANTED[skill]`
and `DECOYS[skill]`.

## Order

1. This plan and the pack skeleton (plugin.json, marketplace entry).
2. The fixture, with its tests.
3. Two builders in parallel: `source-profile`, `source-contract`, `pipeline-incident`, `data-quality`; and
   `data-cost`, `data-migration`, `data-product`.
4. Integration: README, role file, notices, selection cases, checks, example pages read by hand.

Evals cost money and run only when asked.
