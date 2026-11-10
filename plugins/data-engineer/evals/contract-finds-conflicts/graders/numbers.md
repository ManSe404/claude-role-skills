---
type: llm
---

The ERP orders contract has four planted conflicts: (1) it says deliver_by 06:00, but orders.csv arrived after 06:00 on 23 of 31 days, between 07:06 and 07:37, on every working day; it was on time only on the 8 weekend days; (2) it types amount as an integer in cents, but the ERP sends two decimals: 7110.00 with a decimal point on 2026-11-02, and a decimal comma (18846,00) from 2026-11-03; (3) owner and change_process are TBD; (4) it lists sales_rep_code, which the delivery of 2026-11-04 no longer carries (the earlier ones do).
One thing is fine and must not be reported as a conflict: the 3 on_hold lines of 2026-11-04, because the contract's allowed statuses include on_hold.
PASS if the reply names at least 3 of the 4 with their numbers (late days and times, the amount formats, TBD, the missing column), does not call on_hold a conflict, and does not say it changed the contract.
FAIL if it names fewer than 3, reports on_hold as a conflict, or says it changed files.
