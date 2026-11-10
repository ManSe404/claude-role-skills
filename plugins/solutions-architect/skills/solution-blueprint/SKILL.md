---
name: solution-blueprint
description: Use when the specialist pages for one project exist and must become one solution, across AI, data, software and cloud, to join their facts and find where they contradict each other - regions, costs, decisions, technologies, team sizes, what nobody covered - and write one page with the whole solution drawn, every conflict named with the side it recommends, and what to do first. Not for deciding one area; that is ai-pattern, data-platform, arch-style or cloud-design.
argument-hint: "[pages folder or page JSON files]"
---

# Solution blueprint

The job: join the pages the specialists wrote about one project into one solution, and name where they
contradict each other. It changes nothing a specialist decided and recomputes no number a specialist worked
out. It reads their `facts`, and it says when something is missing rather than guessing it. For a decision
inside one area, use that area's skill.

Input: the project's pages folder (default `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/`, or the folder the
user names), and the client brief when there is one. Default: ask where the pages are.

## Steps

1. Read [references/conflicts.md](references/conflicts.md): how to read each conflict type, what makes it real
   and how to recommend a side.
2. Run `python3 "${CLAUDE_SKILL_DIR}/scripts/join_facts.py" PAGES_FOLDER`. Add `--expect a,b` only when no
   `solution-brief` page says who had to run.
3. Say what could not be joined: `pages.missing_skills`, `pages.no_facts`, `pages.superseded`, `pages.invalid`.
4. Read every entry of `conflicts`: open the JSON of the pages it names, the whole page and not just `facts`, and
   the brief. Decide for each: real, not real (say why), or only the client can settle it. Never pass over one.
5. Recommend a side for every real conflict, with the reason and what must change on which page. Name it as a
   recommendation: a person decides. Leave anything the pages do not settle as an open question.
6. Compare the brief with the pages: what the brief asks for that no page covers.
7. Costs: copy the script's `costs.groups` (each cloud or variant, per currency) with their dates and sources into
   the summary, adding only what the script added. Where `added_across_pages` has several pages, check they did not
   price the same thing twice. Never add across currencies, never convert one, and say which cost a group leaves out.
8. Draw the whole solution as one `nested` block from `merged.components`: the regions as boxes and the components
   inside them, each region box with `kind: "ops"`, a `flag: "bad"` on each box in a real conflict and a card that says
   which page and why. Links come from what the specialists' pages state; a link you only infer is labelled `assumed`
   and says so in the card.
9. List the decisions with where each came from, what is missing, the open questions, and what to do first (in
   order, from the conflicts that block the most).
10. Write the page JSON, with `facts`, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format, including `nested`, `findings`
and `facts`, and [references/example.json](references/example.json) for a filled page.

Sections in this order: What was joined (table of pages read, kv of what is missing), The whole solution (one
`nested` block), Decisions (table: decision, chosen, page), Cost (one row per cloud or variant, per currency, with
dates, sources and what it leaves out), Conflicts (`findings`, high first, each with which page says what, what
should change and the side recommended; `declined` with a reason when it turned out not to be real), Not covered
(list), Open questions, What to do first (ordered list). Stats on top: pages joined, conflicts real, conflicts not
real, currencies. The verdict says whether the pages can be built together as they stand, in two sentences.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both files in
`${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/solution-blueprint-<YYYY-MM-DD>.*`, outside the repository. Write
the page in the language of the request; Serbian pages in Latin script.

## Reads

- the specialist page JSON files and the brief, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never recomputes or changes a specialist's number, and never adds costs across currencies or converts one.
- Never resolves a conflict silently: it names it, says what each page says, and recommends a side.
- Never fills a gap with an invented fact; what no page says is an open question.
