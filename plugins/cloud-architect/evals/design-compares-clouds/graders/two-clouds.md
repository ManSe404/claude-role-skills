---
type: llm
---

The brief is 6 container services, 1 platform engineer, about 600 requests a second at peak, 400 GB of relational data, private data stores, loss of one availability zone must be survived, EU only, budget at most 5,000 USD a month. PASS if the reply makes one neutral decision (serverless containers, one relational database, private data, zone redundant, one region), maps it to services on Azure and on AWS (Container Apps and ECS on Fargate), gives a monthly total for each cloud with its date and source, and says which comes out cheaper and by how much, without deciding on price alone if the difference is small.
FAIL if it chooses Kubernetes, gives a total for only one cloud, or quotes a price with no date or source.
