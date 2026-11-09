---
name: ai-architecture
description: Use when an AI or LLM solution must be shown to a client or a team, from a design or from its repository, to draw it as one interactive page - components in zones, clickable details, request flows played step by step, a switch between variants such as RAG and agentic RAG, and the trust boundaries where untrusted text enters and what it can reach.
argument-hint: "[ai-pattern or ai-stack page JSON, a description, or a repo]"
---

# AI architecture

The job: one interactive architecture page of an AI solution that a client can click through: what
each part does, how a request moves, where untrusted text enters and what it could make the system
do. It changes nothing in a repository.

Input: the JSON of an `ai-pattern` or `ai-stack` page, a description, or a repository. Default:
the newest `ai-stack-*.json` or `ai-pattern-*.json` of this project, else the current repository.

## Steps

1. From a repository, count first: `python3 "${CLAUDE_SKILL_DIR}/scripts/ai_inventory.py" REPO`
   into your scratchpad. Read the code at every hit you use. A component you did not read in the
   code is tagged [guess].
2. Components, by zone, left to right: user and channel, application, AI layer, knowledge,
   systems and people, operations. Give each a kind (user, channel, service, model, retrieval,
   store, tool, system, human, guard, ops), its technology, and `side_effect: true` when it sends,
   writes, pays or deletes. Keep labels short (about 18 characters).
3. Links, the way the request goes (caller to callee), with a short label. Mark
   `trust: "untrusted"` on every link that carries text nobody vetted: the user's message, a
   fetched page, a document, an e-mail, a tool's output.
4. Flows: two to four requests that matter most, step by step, each step from one component to
   the next with what happens there. Read every hop in the code when there is code.
5. Variants: the chosen design first, then at most two alternatives worth comparing (for example
   RAG and agentic RAG, or the cloud and the local stack). A component, link or flow that exists
   only in some variants says so.
6. Details per component: responsibility, the data it holds or sees, what happens when it fails,
   its share of the cost (from the `ai-stack` page when there is one), and for code, file:line.
7. Trust: render once, read the page's table of untrusted text reaching a side effect, and say
   for each path what stops it (a person, an allow-list, a confirmation) or that nothing does.
8. Write the page JSON, with `facts`, render it, and say where to open it, with a link that opens the main flow
   (`page.html#flow=<id>&step=1`).

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format, including
the `architecture` block, and [references/example.json](references/example.json) for a filled
page before you write.

Sections in this order: Architecture (one `architecture` block), Components (table: component,
zone, technology, responsibility, fails how), Trust boundaries (text and the paths the page found,
with what stops each), Data (what personal or confidential data goes where, and where it is stored
or logged), Open questions. Stats on top: components, flows, untrusted entry points, side effects
reachable from untrusted text. The verdict says in two sentences what the solution is and the one
risk a reviewer should look at first.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/ai-architecture-<YYYY-MM-DD>.*`. Write
the page in the language of the request; Serbian pages in Latin script.

## Reads

- the design pages, the description, the repository read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never draws a component, link or flow step from a repository as checked unless it read it there:
  it is read, or it is tagged [guess].
- Never shows a secret or a configuration value: settings are named, not quoted. Never opens a
  `.env` file.
- Never changes the repository, runs the application or calls a model.
