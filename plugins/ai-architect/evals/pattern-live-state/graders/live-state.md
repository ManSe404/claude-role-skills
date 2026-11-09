---
type: llm
---

PASS if the reply recommends a workflow with routing (a fixed path per kind of question, not an autonomous agent): retrieval over the manuals and policies for how-to questions, a live read-only call to the OrderDesk API for order status (and says retrieval or an index would be stale for it), and a hand-over to the support staff for returns and refunds. It must name the constraint that decides (for example live order status, the cost of a wrong warranty or return answer, or predictability) and give at least one measurable acceptance criterion.
FAIL if order status is answered from an index, a snapshot or the documents, if returns can be approved without staff, or if it recommends one autonomous agent or several agents as the solution.
