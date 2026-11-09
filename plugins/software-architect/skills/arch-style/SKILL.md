---
name: arch-style
description: Use before building or restructuring a software system, when a brief arrives or someone proposes microservices, to decide what shape it should have - one deployable, a modular monolith, serverless functions, a few services, services with an event backbone or microservices - by eliminating options against the team and the brief's facts, ending in a decision page with fitness rules and an ADR draft.
argument-hint: "[brief file or text]"
---

# Architecture style

The job: decide what shape a software system should have before anyone builds it. Start from the
option with the fewest moving parts and climb only when the one below fails a named requirement. It
writes nothing but the page; the ADR goes into a repo only after the yes. For AI or LLM solutions use
`ai-pattern`; for data platforms use `data-platform`.

Input: a brief (a file or text). Default: ask for the brief.

## Steps

1. Read [references/styles.md](references/styles.md): the ladder, what each option costs a team, the
   order of elimination and the ADR format.
2. Frame: the business areas, the teams and who runs production, how often each part changes, load
   per part, consistency needs, and what is not negotiable. Write each one with where it came from.
3. Ask what flips the decision. If facts from the table in styles.md are open, ask for the two to
   four that matter most, in plain words, and wait. If the user says go on, assume, and put every
   assumption on the page next to the decision it drives.
4. Hard rules: write the facts as JSON in your scratchpad and run
   `python3 "${CLAUDE_SKILL_DIR}/scripts/style_rules.py" FACTS.json` (`--facts` lists them). Every
   eliminated option keeps the rule that eliminated it. Never overrule a rule; fix the fact.
5. Weigh what is still open in the order: can this team run it, consistency, change independence,
   operations, cost. The first factor that rules an option out eliminates it; the factor that
   separates the chosen option from the next one up is the binding constraint. Name it.
6. Choose the lowest open option that passes. Climb above `lowest_open` only for a reason you can
   name from the brief.
7. Boundaries: the modules or services, what each owns (data included), and what crosses between them.
8. What would change the decision: three to five conditions, each with the option it would lead to.
9. Fitness rules: three to five measurable checks that keep the shape true (no cycle between modules,
   each table written by one owner, a deployment of one part needs no other), each with how it is
   measured in CI.
10. ADR draft in Nygard's format as a code block. Offer to write it into the repo; write only after
    the yes.
11. Write the page JSON, with `facts`, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format, including
`nested` and `facts`, and [references/example.json](references/example.json) for a filled page.

Sections in this order: The brief (kv, with sources), Assumptions (list, each with the decision it
drives; omit when none), Decision (a `decision` block: every option of the ladder, factors as
columns, each eliminated option with its rule or factor), Why this one (text: the binding
constraint; show the thresholds the rules used), Boundaries (a `nested` block: the shape, with what
each part owns in its card), What would change it (list), Fitness rules (table), ADR draft (code),
Open questions. Stats on top: teams, business areas, options left after the hard rules, the chosen
option. The verdict says the shape and the binding constraint in two sentences.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/arch-style-<YYYY-MM-DD>.*`. Write the
page in the language of the request; Serbian pages in Latin script.

## Reads

- the brief, read-only

## Writes

- the page and its JSON, outside the repo; the ADR file only after the yes

## Never

- Never proposes services where a modular monolith passes, and never microservices without several
  teams and people to run them.
- Never quotes a vendor's price or limit without its date and source.
- Never sends the brief anywhere.
