# Plan: the `ai-architect` pack

Status: built. This is the original plan from 2026-11-07, kept for its reasoning; the current state
is in `plugins/ai-architect/`. The decisions that were open when it was written are at the end.

## Goal

A pack for AI solutions architects. Before anything is built, the pack decides what the solution
should be: no LLM, one model call, the whole corpus in context, RAG, agentic RAG, a workflow, one
agent, or an orchestrator with subagents. It picks tools layer by layer, with the cost at real
volume, draws an interactive architecture and reviews existing AI solutions.

The format is the same as in the software-engineering pack:
- SKILL.md follows the template (job, input, steps, output, reads, writes, never);
- scripts do the counting;
- a page is JSON drawn by `render_page.py`.

Out of scope are running evals, error analysis, retrieval tuning and trace review (Langfuse). Those
go in a later `ai-engineering` pack.

Nothing public combines the decision and the page (search from 2026-11-06). The closest pieces:
- bowen31337/claude-solution-architect (MIT): the order of the decisions;
- alirezarezvani/claude-skills, agent-designer and rag-architect (MIT): the pattern table and the
  RAG checks;
- konraddzbik/architecture-diagram-skill (MIT): a clickable flow through a diagram.

We take ideas, not code.

## Skills

### 1. `ai-pattern`: which pattern

When: a new AI case or a client brief arrives, before anything is built.
Input: the brief (text or a file), and optionally a folder of documents or a repo.

Steps:
1. **Frame:** users, the job, volume, success criteria and what is not negotiable (regulation,
   where data may live, SLA, budget). If facts that would change the decision are missing, it asks
   for the 2–4 most important ones. If the user says "continue", every assumption goes on the page
   together with the decision it drives.
2. **Division of work:** for each step, decide whether a model, an existing system or a person does
   it, and why.
3. **Documents, if there are any:** `corpus_stats.py`. Does everything fit in context? How often
   does it change?
4. **Hard rules:** `decide.py`. Examples: live state needs a tool call, not retrieval; when an error
   is expensive and no person is in the loop, an autonomous agent is out.
5. **The remaining options, in order:** predictability → cost of an error → visibility → latency →
   cost. The first factor that eliminates an option decides, and it gets a name (the binding
   constraint).
6. **Ladder:** start from the simplest option and climb only when a lower one fails on a named
   requirement.
7. **What would change the decision:** 3–5 conditions (10× the volume, writing to the ERP, a new
   language…).
8. **Acceptance criteria:** 3–5 metrics, each with a threshold and a way to measure it.
9. **ADR (Nygard):** a draft as a code block to copy; it goes in the repo only after a "yes".
10. **The page.**

On the page:
- verdict: the chosen pattern and the binding constraint;
- `decision` block: options × factors, with every rejected option and the reason;
- a graph of the division of work;
- assumptions, what would change the decision, criteria and the ADR.

Never:
- proposes an agent when a workflow is enough;
- states a model's price or version without a date and a source;
- sends the brief off the machine.

### 2. `ai-stack`: which tools

When: the pattern is chosen and the tools must be picked.
Input: the JSON of the `ai-pattern` page or a description of the pattern, plus the constraints (the
client's cloud, where data may live, on-prem).

Steps:
1. **Layers:** model per step, embeddings, vector store, framework (or none), hosting, tracing,
   evals and guardrails.
2. **Candidates:** 2–3 per layer, judged by the criteria in `references/stack.md`. Each choice also
   states what it rejected.
3. **Variants:** two at most, for example Azure-native and local/open.
4. **Cost and latency:** for each variant, from `cost_model.py`, with a price table that has a date
   and a source.
5. **Vendor lock-in:** the risks and what moving away would cost.
6. **Before the offer:** what must be checked (quotas, region, model availability).

Never:
- a price from memory;
- a network request without permission.

### 3. `ai-architecture`: the interactive page

When: an AI solution must be shown to a client or a team, from a design or from a repo.
Input: the JSON from `ai-pattern` and `ai-stack`, a description, or a repo (then `ai_inventory.py`).

Steps:
1. **Components by zone:** user and channel, application, AI layer, knowledge, systems and tools,
   operations.
2. **Links and flows:** the links between components and 2–4 request flows, step by step.
3. **Trust boundaries:** where untrusted text enters (user, documents, tool output) and which tools
   with consequences it can reach.
4. **Variants:** for example RAG ↔ agentic RAG, as a switch.
5. **Component details:** technology, responsibility, data, what happens when it fails, share of the
   cost.

Never:
- presents a component from a repo it has not read as known; it gets the [guess] tag;
- shows secrets or configuration values, only their names.

### 4. `ai-review`: review of an existing AI solution

When: before a release, when taking over a project, or before handing one over to a client.
Input: a repo or a design document.

Steps:
1. Run `ai_inventory.py` and reconstruct the architecture from it.
2. Go through the list in `references/anti-patterns.md`:
   - the pattern is too big for the problem;
   - live state goes through retrieval;
   - the agent has no limit on steps or spend;
   - tool or document output reaches a tool with consequences with no person in between (prompt
     injection);
   - a key is in the code;
   - there are no evals or tracing;
   - model calls have no timeout or fallback;
   - personal data goes to an external model;
   - the model is not pinned;
   - the cost at volume has not been estimated.
3. Every finding gets a file:line and a suggestion.
4. The problem spots are marked on the graph.

Never:
- changes anything;
- runs the application;
- calls models.

## Scripts

All scripts are Python stdlib, only read, and write JSON to stdout.

| script | skill | what it does |
|---|---|---|
| `corpus_stats.py` | ai-pattern | files by type, sizes, token estimate (chars/4, with a note), range of changes, duplicates by hash, Latin or Cyrillic script, rough PDF page count |
| `decide.py` | ai-pattern | the input is the facts from the brief as JSON (live state, known steps, cost of an error, person in the loop, latency budget, volume, corpus tokens, actions with consequences); the output says which options fall and by which rule. Hard rules only; Claude decides the weighing |
| `cost_model.py` | ai-stack | steps × calls × tokens × price × volume, cache share, p50 latency for sequential and parallel steps. The price table is a file with a date and a source; `prices.example.json` is marked as an example to be checked |
| `ai_inventory.py` | ai-architecture, ai-review | Python, C# and TypeScript: SDKs (openai, anthropic, Azure.AI.OpenAI, langchain, langgraph, llama_index, semantic_kernel, ollama…), model names, vector stores, tool definitions, prompts, loop limits, timeouts, tracing, evals. Names only for env variables, never values. All with file:line |

## Renderer (`shared/`, changes the pages of every pack)

Two new block types.

**`decision`:** options × factors.
- Every cell is pass, weak or fail, with a short text.
- Every option has the status chosen, viable or eliminated, with `eliminated_by` and `why`.
- The chosen option stands out; rejected ones are dimmed with the reason visible.

**`architecture`:**
- Fields:
  - `zones`;
  - `components` {id, label, zone, kind, tech, note, details, variants};
  - `links` {from, to, label, trust: trusted | untrusted, variants};
  - `flows` [{id, title, steps: [{from, to, text}]}];
  - `variants` [{id, label, note}].
- Interaction:
  - clicking a component opens a panel with its details and links;
  - a flow plays or steps with the ←/→ arrows;
  - a switch changes the variant;
  - the trust boundary view turns on and off;
  - the links `#component=`, `#flow=…&step=` and `#variant=` open the page in that state.
- Without JS and when printing: a table of components, flows as `steps`, variants as lists.
- Layout:
  - computed in Python and always the same: a zone is a column in a fixed order, components are
    stacked one below the other;
  - uses the existing graph helpers.
- Limits: no libraries, nothing from the network, every value escaped, a page with fonts under
  about 400 KB.

Tests:
- validation errors with the JSON path;
- escaping;
- the same JSON gives the same HTML;
- no external URL;
- every link, flow and variant points to an existing id.

**Precondition:** last night's uncommitted renderer changes (14 files, +1144 lines, 2026-11-06
23:08) are committed first, because this pack builds on them.

## Fixture: `fixtures/acme-assist/` (all made up)

**`brief-support.md`:** a support assistant for a made-up device manufacturer.
- Manuals and the FAQ are stable knowledge; order status from the ERP is live state.
- Product returns follow rules.
- Serbian and English, 3,000 questions a day, and a wrong answer about the warranty is expensive.
- The right answer is a workflow with routing: RAG for the manuals, a tool call for orders, a person
  for returns. An autonomous multi-agent setup is out.

**`brief-tagging.md`:** 200 emails a day in 6 categories. The right answer is one model call with
structured output. This brief checks that the skill does not overbuild.

**`corpus/`:** 15–25 small documents (md, txt, a few minimal PDFs), in Latin and Cyrillic script.

**`files/` + `history.py`:** a small Python application with 8 planted problems for `ai-review`:
1. it reads stock levels from the vector database, so they are stale;
2. the agent loop has no limit;
3. the output of the web tool goes to the email tool with no confirmation;
4. a fake default key (`sk-example-…`) in `config.py`;
5. no evals;
6. model calls have no timeout;
7. it uses a model alias instead of a pinned version;
8. no tracing.

The list goes in a test too.

## Evals (`claude plugin eval`)

1. **pattern-does-not-overbuild:** for brief-tagging it picks one model call, with no agent.
2. **pattern-live-state:** for brief-support, live state goes through a tool, not retrieval, and the
   binding constraint has a name.
3. **stack-cost-from-script:** the numbers on the page are the output of `cost_model.py`, and the
   prices have a date.
4. **architecture-page:** the HTML exists, has a flow and a variant, has no external URLs, and
   untrusted input is marked.
5. **review-finds-planted:** it finds at least 6 of the 8 planted problems and changes no file.

Every case also has a `skill-fired` grader. Evals run only on request. For comparison, five headless
runs on the software-engineering pack cost $6.55.

## Other

- `roles/ai-architect.md`, a CLAUDE.md starter:
  - the "simplest thing that works" ladder;
  - the tags [high], [med] and [guess];
  - changeable facts (prices, models, quotas) always with a date and a source;
  - client data never in examples.
- `references/patterns.md`, `stack.md` and `anti-patterns.md`: short, no price lists.
  - Sources: Anthropic's "Building effective agents", bowen31337 and alirezarezvani (MIT).
  - Adapted text goes in THIRD-PARTY-NOTICES.
- Skill descriptions must not take requests away from `engineering:architecture`,
  `engineering:system-design`, `claude-api` and `langfuse`. Every description says "AI/LLM solution",
  and also "before building" or "review of an existing one".
- A page is in the language of the request. The fonts have Latin Extended but no Cyrillic, so
  Serbian pages are written in Latin script.
- Update the README table, the marketplace entry, `plugin.json` and the repo's CLAUDE.md (which says
  "SWE pack only" at the moment).

## Order

- M0: commit the existing changes.
- M1: references, the fixture and the fixture's tests.
- M2: the renderer (`decision`, `architecture`), tests, `tools/sync_shared.py`.
- M3: four scripts and their tests on the fixture.
- M4: four SKILL.md files and `references/example.json`, produced by headless runs on the fixture
  and checked by hand (about $5–10).
- M5: evals written; they run only on request.
- M6: README, marketplace, role starter and notices. Green at the end: pytest, ruff, mypy strict,
  `claude plugin validate .`.

## Decisions that were open when this was written

1. Is `ai-architect` the name of the pack?
2. Four skills, with evals, retrieval and trace review going to a later `ai-engineering` pack?
3. `decide.py` with hard rules: yes or no?
4. A stack that is neutral by default, with Azure and local Ollama as two variants?
5. Commit last night's changes before starting.
