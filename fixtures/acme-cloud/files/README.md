# Acme Tickets infrastructure

Acme Tickets sells tickets for concerts and festivals. This repository holds the cloud infrastructure
of the production estate. It is managed by hand from the `platform` team's laptops, one environment.

## What is here

- `infra/terraform/`: the main application: the portal, the worker, the database, storage, queues.
- `infra/terraform/modules/worker/`: the worker as a Container App, as a local module.
- `infra/bicep/`: the reports part, owned by the analytics team, deployed at subscription level.
- `infra/arm/`: an older template for the alert group.
- `docs/briefs/`: two briefs for what comes next.

## Rules we agreed

- Production runs in `westeurope`. Customer data stays in the EU.
- Secrets go in Key Vault, not in app settings.
- Things are changed through this repository, not in the portal.

Contact: platform@example.com
