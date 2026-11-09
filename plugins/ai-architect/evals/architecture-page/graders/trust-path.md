---
type: llm
---

PASS if the reply describes the prototype as one agent loop calling an OpenAI chat model with four tools (manual search, stock check, fetch a URL, send an e-mail) over a FastAPI /chat endpoint with Qdrant as the store, walks a customer question through it, and points out that untrusted text (the customer message or a fetched web page) can reach the send_email tool with no person in between.
FAIL if it invents components the code does not have, or misses the path from untrusted text to send_email.
