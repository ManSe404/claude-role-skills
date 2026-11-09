# The AI pattern ladder

Start at the bottom and climb only when the rung below fails a named requirement of the brief.
Every rung up adds model calls, latency, cost, failure modes and things to test.

| Rung | Pattern | Use it when | It breaks when |
|---|---|---|---|
| 0 | **No LLM**: rules, search, a form, a lookup | The input is structured or the answer is a field in a system | People write free text the rules cannot read |
| 1 | **One model call**, structured output | One step: classify, extract, rewrite, summarise one input | It needs knowledge the input does not carry |
| 2 | **Whole corpus in the prompt** | The documents fit a share of the window, change rarely, and volume is low or the prompt is cached | The corpus grows past the budget, or every call pays for all of it |
| 3 | **RAG**: retrieve, then one call | A large, stable body of documents; one lookup answers the question | The answer needs live state, or several lookups that depend on each other |
| 4 | **Workflow**: a fixed chain or a router | The steps are known for each kind of request: classify, then the matching path | Requests need paths nobody can list in advance |
| 5 | **Agentic RAG**: the model decides what to retrieve next | Multi-hop questions: what to search second depends on what came back first | The steps are known (a workflow is cheaper and testable), or latency is tight |
| 6 | **One agent with tools** | Open-ended tasks, an unknown number of steps, a person reviews the result or errors are cheap | Errors are expensive and nobody reviews, or the tools change the world without a check |
| 7 | **Orchestrator with subagents** | Independent subtasks that each need their own context and can run in parallel, with value that pays for many calls | There is nothing to split; hand-offs lose context and multiply cost |

Workflow shapes (rung 4), after Anthropic's *Building effective agents*: prompt chaining (fixed
steps, a check between them), routing (classify, then a specialised path), parallelisation
(sections in parallel, or several votes), evaluator-optimiser (one call writes, another grades,
loop with a limit). The orchestrator-workers shape is rung 7.

## Two rules that decide most briefs

- **Live state needs a call to its owner.** Order status, stock, balances and bookings change
  faster than any index is rebuilt. Retrieval returns a copy from the last indexing run. Use a
  read-only API or a tool call, and keep retrieval for stable knowledge.
- **Known steps mean a workflow.** If you can write the steps down for every kind of request,
  let code choose the path, not the model. A fixed path is cheaper and faster, you can test each
  step on its own, and a trace shows why it went wrong.

## The order of elimination

When the hard rules (`decide.py`) leave more than one option open, weigh them in this order and
stop at the first factor that rules an option out. That factor is the **binding constraint**:
name it on the page.

1. **Predictability**: does the same input take the same path? Can each step be tested?
2. **Cost of an error**: what does a wrong answer or a wrong action cost? Who catches it?
3. **Observability**: can you see why an answer came out wrong, step by step?
4. **Latency**: model calls in a row × seconds per call, against the budget.
5. **Cost**: calls × tokens × price × volume (the `ai-stack` skill counts it).

## Questions that flip the decision

Ask only the ones the brief leaves open, two to four at a time, in plain words:

| Fact for `decide.py` | Ask |
|---|---|
| `live_state` | "Does any answer depend on data that changes during the day, such as order status or stock?" |
| `steps_known` | "Can you list what the assistant must do for each kind of question?" |
| `error_cost`, `human_review` | "What does one wrong answer cost, and does a person see it before the customer does?" |
| `uses_documents`, `corpus_tokens` | "Which documents must it know, and how many pages are they in total?" |
| `distinct_steps` | "Is it one job, or several jobs that depend on the kind of request?" |
| `independent_subtasks` | "Does the work split into parts that could be done by different people at the same time?" |
| `latency_budget_s` | "How fast must the first answer appear?" |
| `context_budget_tokens` | Your call: about a quarter to a half of the model's window, leaving room for the question, the history and the answer |

## Acceptance criteria

Three to five, each with a threshold and how it is measured before launch. For example:

| Metric | Example threshold | Measured how |
|---|---|---|
| Correct answers on a labelled set | ≥ 90% of 200 real questions | Eval set from past tickets, graded by a person or a checked judge |
| Grounded answers | every answer cites a source; 0 claims without one | Judge on the eval set and a weekly sample from traces |
| Correct hand-off | ≥ 95% of return requests reach a person | Routing accuracy on the labelled set |
| Latency | p95 of the first token ≤ the budget | Traces under the expected peak load |
| Cost | ≤ budget per month at the brief's volume | `cost_model.py`, then the first month's bill |

## The ADR (Michael Nygard's format)

```text
# ADR-NNN: <decision in a few words>
Status: proposed
Context: the brief's facts and constraints that matter, with the numbers.
Decision: the chosen pattern and its shape (routes, tools, people), in two to four sentences.
Consequences: what gets easier, what gets harder, what we must build and measure; the options
eliminated and the binding constraint; what would make us revisit it.
```

## Sources

- Anthropic, *Building effective agents* (2024):
  https://www.anthropic.com/engineering/building-effective-agents
- Michael Nygard, *Documenting architecture decisions* (2011):
  https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
- The elimination order follows the idea of bowen31337/claude-solution-architect; the pattern
  table draws on alirezarezvani/claude-skills (agent-designer, rag-architect). Both are MIT. This
  text is written anew.
