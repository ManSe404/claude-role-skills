---
type: llm
---

PASS if the reply recommends a single model call per e-mail with structured output (a fixed list of the six categories: order, technical, returns, invoice, partnership, spam), optionally with simple rules in front of it, and explains why nothing bigger is needed (one step, cheap mistakes, no documents to retrieve, no live data). Mentioning RAG, a workflow or an agent only as options it rejected is fine.
FAIL if it recommends RAG, an agent, several agents, fine-tuning or training a classifier as the solution, or if it asks questions instead of deciding.
