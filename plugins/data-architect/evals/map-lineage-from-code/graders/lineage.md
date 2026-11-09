---
type: llm
---

In this repository the erp source tables feed staging models, staging feeds marts, a report reads staging directly, a marketing export reads dim_customer and sends e-mail and national IDs out, one procedure runs dynamic SQL, and mart_old_campaigns is read by nobody in the repository.
PASS if the reply describes that layered flow, says where personal data ends up (the marketing export), mentions the dynamic SQL as something that could not be read automatically, and mentions at least one table nobody reads or the report that skips a layer.
FAIL if it misses where personal data goes, or invents systems the repository does not contain.
