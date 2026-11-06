---
type: llm
---

PASS if the reply says the import fails on decimal commas such as "12,50" in the export (order A-1045), and that the cause is commit 49bc16d "importer: simplify amount parsing" of 2026-09-30, which removed the comma-to-dot replacement in `parse_amount` and deleted the test that covered decimal commas; and it names `report.read_adjustments` as another place with the same weakness. It proposes a regression test and a fix rather than claiming the code is already fixed.
FAIL if it blames only the data or the shop's export without the commit, if it misses the deleted test, or if it says it changed the importer.
