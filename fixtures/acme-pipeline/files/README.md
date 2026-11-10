# Acme Foods data platform

Acme Foods distributes food to the Acme Market franchise stores: 26 in Vojvodina and 4 in Szeged, Hungary. This
repository is the small data platform behind finance's cash plan, the BI sales board and the store apps.

## How it works

- The ERP drops its daily files into `sources/erp/<delivery date>/`: the order lines, invoices, returns and payments
  of the previous day. The CRM is being added as a second source, see `sources/crm/README-vendor.md`.
- Python loaders in `pipeline/loaders/` copy each file into a bronze table; the SQL in `pipeline/silver/` and
  `pipeline/gold/` builds the typed silver tables and the served gold tables.
- Jobs are defined in `jobs/*.yaml` (a cron schedule, the steps, a service level where there is one) and run by the
  scheduler on the `etl` cluster through `pipeline/runner.py`.
- Checks in `checks/` run after each layer. Rows that break a rule in `checks/quarantine.yaml` are moved to the
  quarantine before silver is built.
- Run records, check results, the quarantine, the delivery log, the billing export and the query log are written to
  `ops/` on the platform host (see `ops/README.md`); only the incident log is kept in git.

## Layout

| path | what |
|---|---|
| `sources/` | the deliveries, the last three per source (not in git), and the vendors' documents |
| `contracts/` | data contracts with the source systems |
| `pipeline/` | loaders, SQL per layer, shared SQL functions and the settings |
| `jobs/` | job definitions |
| `checks/` | checks, quarantine rules and the bad-data cases each check was tried on |
| `ref/` | reference tables kept by hand |
| `docs/` | the runbook, how-to guides and the documents of the served tables |
| `reports/bi/` | the BI team's metric definitions |
| `legacy/` | the old cron estate that is being moved onto the platform |
| `samples/` | CSV copies of the served tables, made by `make samples` (not in git) |
