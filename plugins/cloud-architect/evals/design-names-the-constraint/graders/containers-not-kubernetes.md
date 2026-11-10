---
type: llm
---

The brief is 6 container images, 8 engineers with 1 platform engineer, none needing the Kubernetes API, private addresses for all data stores, must survive one zone, must stay in the EU, budget 5,000 USD a month.
PASS if the reply recommends serverless containers (Container Apps) over Kubernetes and names why (too few platform engineers, nothing needs the Kubernetes API), keeps data private with private endpoints and zone redundancy, and gives a monthly cost per variant with date and source.
FAIL if it recommends Kubernetes or multi-region, leaves the data stores on public endpoints, or quotes a price with no date or source.
