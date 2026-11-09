---
type: llm
---

The structure has eight planted problems: (1) a cycle between Acme.Logistics.Shipments and Acme.Logistics.Billing; (2) Domain/Parcel.cs depends on Infrastructure, a layer break; (3) Common/Helpers.cs is a dumping ground used from many namespaces; (4) the same pricing rule is written in PricingRules.cs and web/src/app/shipments/pricing.ts, which always change together with no code link; (5) the worker updates the shipments table directly in worker/src/acme_worker/db.py, a table the API owns; (6) ShipmentService.cs is the hot spot, the largest and most changed file; (7) the API calls the worker over HTTP and the worker calls the API back, a synchronous loop; (8) Billing has been changed by one person only.
PASS if the reply names at least 6 of the 8, each tied to the right place.
FAIL if it names fewer than 6, says it changed files, or criticises a person rather than noting where knowledge is concentrated.
