# 0009. Pages declare an archetype, checked against a schema

Date: 2026-11-23, at Stefan's request that every agent produce pages of the same structure.

## Status

Accepted

## Context

Fifty skills write page JSON, and other agents (Codex, a second Claude session) are to write it too. `render_page.py`
already refused a page it could not draw, but it accepted anything else: a misspelt optional field (`sevrity`) was
dropped without a word, and nothing said that a review page must list findings or a decision page must name what it
chose. Structure was kept by the text of each SKILL.md and by good will. A rule that only lives in prose drifts as
soon as a second author writes pages.

The pages fall into a few kinds. Looking at all fifty examples: seventeen hold findings against rules, eleven rule
options out, eight draw a system, three tell an incident as a timeline, seven close a workflow chain, and four explain
a result in tables and numbers (numbers that moved or reconcile, a brief, a drafted document set). The five kinds
first proposed (decision, map, review, incident, chain) left those four out, so a sixth, `report`, was added rather
than forcing them into a kind they are not.

## Decision

- `shared/page-schema.json` is a JSON Schema (Draft 2020-12) of the page JSON: every block type, every field and the
  `facts` section, with unknown fields refused. It is the contract a tool outside this repository can check against.
- `shared/page-archetypes.json` names six archetypes (`decision`, `map`, `review`, `incident`, `chain`, `report`)
  and for each what a page must have (errors) and should have (warnings), as rules a script reads: a verdict, block
  types present, `facts` keys present or non-empty.
- A page declares its kind in a top-level `archetype`. `render_page.py --check` (and rendering itself) validates the
  page as before, then against the schema and its archetype, and prints every problem with its JSON path.
- The checker understands the subset of JSON Schema the file uses, in the standard library like every script here.
  A test checks the schema with the `jsonschema` package (a development dependency only) and that both agree.
- A page without an archetype is held to the old checks; the missing archetype and any schema problem are warnings.
  Old pages and agents that do not know archetypes keep working.
- Each skill names its archetype in SKILL.md and runs `--check` before it calls the page done.

## Consequences

- A misspelt field, a review without findings or a decision without a decision in its facts fails at the end of the
  run, where the agent can still fix it, instead of reaching a reader.
- Both files are shared files: `tools/sync_shared.py` copies them into every skill beside `page-format.md`.
- Cross-references (edge ends, ids, waterfall totals) stay in `render_page.py`, which JSON Schema cannot express.
- A new block type or field changes three places: the renderer, `page-format.md` and the schema. A test fails when
  the schema and the renderer's block types differ.
- "Should have" warnings point at skills that write less than their kind asks (for example review pages without
  `facts.open`); filling them is a roadmap item, not a failure today.
