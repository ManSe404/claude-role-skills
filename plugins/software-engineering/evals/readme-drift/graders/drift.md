---
type: llm
---

The code has the flags `--notify` (import) and `--adjustments` (report) that the README never mentions, and acme.yaml.example names db_path, mail_api_url and vat_rate. Every command, flag and setting the README names exists in the code, so there is nothing stale.
PASS if the reply names --notify and --adjustments as undocumented, says that nothing in the README is stale (or lists no stale item), and the drafted Run section shows the real commands.
FAIL if it claims a stale command, flag or setting that the README does not contain, if it misses both flags, or if it writes a file into ./acme-orders.
