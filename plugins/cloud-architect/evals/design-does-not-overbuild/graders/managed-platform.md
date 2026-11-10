---
type: llm
---

The brief is 2 engineers, no platform engineers, one web application, 20 requests a second, 30 GB of relational data, a budget of at most 200 USD a month.
PASS if the reply recommends a managed app platform (App Service) with one managed database, says why containers platforms and Kubernetes are not needed, gives a monthly cost under the budget or says plainly that it does not fit, and every price carries its date and source.
FAIL if it recommends Kubernetes, serverless containers or virtual machines as the solution, recommends multi-region or zone redundancy, quotes a price with no date or source, or asks questions instead of deciding.
