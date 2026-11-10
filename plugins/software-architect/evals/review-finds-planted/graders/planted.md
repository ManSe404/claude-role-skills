---
type: llm
---

The design has eight planted flaws: (1) Booking waits on Pricing, which waits on the Carrier Gateway for a live quote of 400–800 ms, so the goal of a booking confirmed in under 500 ms at p95 cannot be met; (2) both the Tracking and the Billing service write `shipments.status`; (3) "a customer is never charged twice" while the charge is retried on timeout and no idempotency key or dedupe exists; (4) "highly available and scale for peak season" has no number; (5) nothing says what happens when a carrier API is slow or down; (6) the proposal says Tracking gets status changes as broker events, while accepted ADR-0003 says Tracking polls Booking's REST API every minute; (7) one central Data Service owns every table and every service reads and writes through it; (8) the broker is still to be decided (ADR-0004 proposed) while Tracking relies on per-shipment event order.
PASS if the reply names at least 6 of the 8, and does not call any of these a problem: the tariff cache with its accepted 15-minute staleness, Pricing having its own database, or the Address Validator call with its 50 ms budget and fallback.
FAIL if it names fewer than 6, reports one of those three as a flaw, reviews code instead of the documents, or says it changed files.
