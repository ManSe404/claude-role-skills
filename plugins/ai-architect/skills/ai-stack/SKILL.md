---
name: ai-stack
description: Use when the pattern of an AI or LLM solution is chosen and the tools must be picked, to choose the model per step, embeddings, retrieval store, orchestration, hosting, tracing, evals and guardrails against the client's constraints, in at most two variants, with monthly cost and latency computed from a dated price table, the lock-in, and what to check before the offer.
argument-hint: "[ai-pattern page JSON or a description] [constraints]"
---

# AI stack

The job: the tools for each layer of a chosen AI design, what each choice gives up, and what it
costs and how fast it is at the brief's volume. Every number comes from the cost script and a
price table with a date and a source.

Input: the JSON of an `ai-pattern` page, or a description of the pattern, plus the constraints:
the client's cloud, where data may go, on-prem, budget. Default: the newest `ai-pattern-*.json`
in the pages folder of this project, if there is one.

## Steps

1. Read [references/stack.md](references/stack.md). Then read the pattern: its steps, routes,
   volume, latency budget and constraints. List the constraints that remove candidates outright.
2. Layers: for every step of the pattern, the model (small or large), and for the solution the
   embeddings, the retrieval store, orchestration, hosting, tracing, evals and guardrails.
3. Candidates: two or three per layer by the criteria in stack.md; the chosen one, why, and what
   the choice gives up. Prefer what the client already runs.
4. Variants: at most two, for example cloud-native against local or open. Same pattern, same flows.
5. Prices: ask the user for a price table, or, after a yes, read the providers' price pages (a
   timeout on every request) and write `prices.json` in your scratchpad with `currency`, `as_of`
   and `source` for every model. Without either, use
   [references/prices.example.json](references/prices.example.json) and mark every number on the
   page EXAMPLE.
6. Write `DESIGN.json` in your scratchpad: requests per day, the share of each route, tokens per
   call (system prompt, passages, history, question, answer), cached share, seconds per call,
   fixed monthly items. Say where each number comes from. Then run
   `python3 "${CLAUDE_SKILL_DIR}/scripts/cost_model.py" DESIGN.json --prices PRICES.json`.
   Every warning it prints goes on the page.
7. Latency: each path's seconds against the budget. Cost: each variant against the budget, with
   the step that costs most and what would cut it (a smaller model, caching, fewer passages).
8. Lock-in: per layer, what is provider-specific and what moving would cost.
9. Before the offer: quotas for the peak, the model and version in the required region, data
   processing terms, private networking, the date of every price and rate.
10. Write the page JSON, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page before you write.

Sections in this order: Constraints (list), Stack (table: layer, chosen, alternatives, why, gives
up), Variants (table), Cost (table per variant and step, fixed items, total, the budget), Latency
(table per path against the budget), Lock-in (table), Before the offer (list), Assumptions (table:
number, value, source). Stats on top: monthly total per variant, cost per request, the slowest
path, the date of the price table. The verdict names the recommended variant and whether it fits
the budget and the latency.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/ai-stack-<YYYY-MM-DD>.*`. Write the
page in the language of the request; Serbian pages in Latin script.

## Reads

- the pattern page or description, the brief, the price table the user gives

## Writes

- the page and its JSON, outside the repo; DESIGN.json and prices.json in the scratchpad

## Never

- Never gives a price, a quota or a model version from memory: from the price table, with its
  date and source, or marked EXAMPLE.
- Never goes online without the yes, and then only to the providers' public price pages.
- Never puts a number on the page that `cost_model.py` did not compute, and never picks a
  product that the client's constraints exclude.
