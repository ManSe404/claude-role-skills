# Choosing the stack, layer by layer

Products and prices change every month. This file gives the criteria and examples of candidates
(as of 2026-11), not a price list. Every price on a page comes from a price table with a date and a
source, through `cost_model.py`.

## Constraints first

Read them from the brief before naming any product. They remove candidates outright:
- **Where data may go**: the EU only, a named cloud tenant, on-prem only, no training on prompts.
- **What the client already runs**: their cloud, their database, their identity, their ops tools.
  Something new must earn its place.
- **Who runs it after hand-over**: a stack the client's team cannot operate is a bad stack.
- **Budget and volume**: the monthly ceiling at the brief's volume and peak.

## Layers

| Layer | Decide by | Candidates (examples) |
|---|---|---|
| **Model per step** | Quality on *your* eval set, languages (test Serbian in Latin and Cyrillic, not just English), structured output, tool calling, latency, region, price | Hosted: OpenAI or Azure OpenAI, Anthropic (direct, Bedrock, Vertex), Google Gemini, Mistral. Local: Llama, Qwen, Mistral or Gemma through Ollama or vLLM |
| **Small vs large** | Routing, classification and extraction usually run well on a small model; the answer the customer reads goes to the model that passes the eval | One small and one large model, both pinned to a dated version |
| **Embeddings** | Multilingual quality on your documents, dimension (storage), region | Hosted multilingual embedding models, or local ones (bge-m3, multilingual-e5, nomic-embed) |
| **Retrieval and store** | Hybrid search (keywords for part numbers and error codes, vectors for meaning), filters by product and language, what the client runs | Azure AI Search, PostgreSQL with pgvector, Qdrant, Elasticsearch or OpenSearch |
| **Orchestration** | A workflow needs code, not a framework. Use a framework when you need graphs with state, retries and checkpoints | Plain code with the provider SDK; LangGraph; Semantic Kernel (.NET); Microsoft.Extensions.AI |
| **Hosting** | Where the client runs services, private networking to the model, scaling to the peak | Azure Container Apps or App Service, Kubernetes, a VM with a GPU for local models |
| **Tracing** | Every call, tool call and retrieval visible, with cost and latency; self-hosting where data may not leave | Langfuse (cloud or self-hosted), OpenTelemetry GenAI conventions into Application Insights or Grafana |
| **Evals** | A labelled set from real cases, run on every change of prompt, model or retrieval | Langfuse datasets and experiments, promptfoo, Ragas for retrieval, a person-graded sample |
| **Guardrails** | What must never happen: PII leaving, an action without approval, an answer without a source | Input and output filters, PII redaction, tool allow-lists, a person before side effects, Azure AI Content Safety and Prompt Shields |

For each layer give two or three candidates, the chosen one, and **what the choice gives up**: a
choice without a cost is not a choice.

## Variants

At most two, so the client can compare: for example **cloud-native** (the client's cloud, its
managed model and search) against **local or open** (an open-weight model on their own server,
an open-source store). Same pattern, same flows. Only the products and the cost differ.

## Cost model inputs

Fill `DESIGN.json` for `cost_model.py` from the pattern and the brief, and say where each number
comes from:
- requests per day and the share of each route (the brief's mix);
- tokens per call: system prompt + retrieved passages + history + question, and the answer. Count
  the prompt with the corpus stats (`tokens_est` of a passage × passages per call);
- cached share: the stable prefix (system prompt, tool definitions) that prompt caching can reuse;
- seconds per call: measured, or the provider's published latency, marked as such;
- fixed monthly items: the vector store, hosting, the GPU server for a local model, tracing.

## Lock-in

For each layer: what is provider-specific (an API shape, an index format, a prompt tuned to one
model), and what moving would cost. Keep prompts, eval sets and traces in formats you own; then a
model can be swapped behind one interface and checked against the same eval set.

## Before the offer

- Quotas and rate limits (tokens and requests per minute) for the peak, in the region.
- The model and version are available in the region the data must stay in.
- Data processing terms: retention, abuse monitoring, no training on prompts.
- Private networking to the model and the store, if the client requires it.
- Prices and the exchange rate, with their date, in the offer.
