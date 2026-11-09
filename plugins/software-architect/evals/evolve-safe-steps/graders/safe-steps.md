---
type: llm
---

PASS if the reply plans ordered steps, breaks the cycle between Shipments and Billing before moving Billing out, says for the steps how each is verified and how it is undone, and says where it would be reasonable to stop.
FAIL if it proposes a big-bang rewrite, moves Billing before dealing with the cycle, gives dates or person-days, or has no way to verify or undo the steps.
