# Stagefront infrastructure

Stagefront sells tickets for theatres and small venues. Acme Tickets bought the company in 2026. This
repository holds the cloud infrastructure of Stagefront's production estate, one environment, one account.

## What is here

- `infra/terraform/`: the main application: the network, the portal and the worker, the database,
  storage and queues.
- `infra/terraform/modules/queue/`: a queue with its dead-letter queue, as a local module.
- `infra/cloudformation/reports.yaml`: the reports part, owned by the analytics team.
- `infra/cloudformation/admin.yaml`: an admin host, deployed by hand with parameters.
- `infra/cloudformation/alerts.json`: the alert topic and the alarm.
- `docs/briefs/`: the brief for what comes next.

## Rules we agreed

- Production runs in `eu-central-1`. Customer data stays in the EU.
- Secrets go in Secrets Manager, not in environment variables.
- Things are changed through this repository, not in the console.

Contact: platform@example.com
