---
type: llm
---

The code exposes `python -m acme_orders import FILE` (also `check`, `report --day`, `serve --port`), settings ACME_DB_PATH, ACME_MAIL_API_URL, ACME_MAIL_API_KEY and ACME_VAT_RATE read from the environment or acme.yaml, the routes GET /health and GET /orders/<id>, and an import that parses the whole file before its first write. There is no restart, retry, dry-run or rollback command in the code.
PASS if the draft (1) uses the real import command (python -m acme_orders import or acme-orders import) and the check command or the /health route for verification, (2) names at least ACME_DB_PATH by name without any value, (3) does not invent a command or flag that the code does not have (no --dry-run, no restart, no rollback command), and (4) marks what a person must fill (hosts, paths, contacts) as unknown or a placeholder rather than inventing them.
FAIL if it invents a command or flag, states a host, path or contact as fact that is not in the repository, or writes a file into ./acme-orders.
