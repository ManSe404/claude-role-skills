---
type: llm
---

The brief is a small company: one ERP and a budget spreadsheet, 3 GB, refreshed daily, one analyst, no data engineer.
PASS if the reply recommends one database with scheduled SQL (or a very close equivalent, such as a small managed SQL database loaded by scheduled jobs), and says why nothing bigger is needed.
FAIL if it recommends a lakehouse, a streaming path, a data mesh or a warehouse platform as the solution, or if it asks questions instead of deciding.
