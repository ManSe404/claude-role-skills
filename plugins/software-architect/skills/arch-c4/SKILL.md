---
name: arch-c4
description: Use when a software system must be drawn and explained, from a brief or from its repository, to produce a C4 view on one clickable page - the system in its context, the containers that run, the components inside the ones that matter - with zoom between levels, requests traced hop by hop and every box tied to the code or marked as a guess.
argument-hint: "[repository, or a brief or arch-style page]"
---

# C4 view

The job: a drawing of a software system that is true, at the three levels that matter: who uses it
and what it talks to, what runs, and what is inside the parts that matter. It changes nothing. For
an AI or LLM solution use `ai-architecture`; for cloud resources, `cloud-architect`.

Input: a repository, a brief, or the JSON of an `arch-style` page. Default: the current repository.

## Steps

1. From a repository, count first: `python3 "${CLAUDE_SKILL_DIR}/scripts/containers.py" REPO` and
   `python3 "${CLAUDE_SKILL_DIR}/scripts/code_graph.py" REPO`, output to your scratchpad.
2. Read the code at every hit you use. A box or a link you did not read is tagged [guess]. People and
   outside systems usually come from the README, the docs and the outside hosts in the output.
3. Context: the system as one box, the people who use it, the systems it depends on and those that
   depend on it.
4. Containers: what runs on its own: apps, workers, databases, queues. Each with its technology.
5. Components: only inside the containers that matter, usually one or two. Group modules; do not
   draw classes. Keep to about 40 boxes.
6. Links: between the most specific boxes, each labelled with what crosses it and how. The page
   moves a link out to the visible box at higher levels.
7. Flows: two to four requests that matter most, step by step, at the Containers level; read every
   hop in the code when there is code.
8. Details per box: responsibility, what it owns, what happens when it fails, file:line for code.
9. Write the `nested` block as JSON and run
   `python3 "${CLAUDE_SKILL_DIR}/scripts/c4_check.py" PAGE.json`. Fix every error.
10. Write the page JSON, with `facts`, render it, and say where to open it, with a link that opens
    the Containers level (`page.html#variant=containers`).

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format, including the
`nested` block and `facts`, and [references/example.json](references/example.json) for a filled page.

Sections in this order: The system (a `nested` block with the levels Context, Containers and one per
container opened; flows), What runs (table: container, technology, deployed how, owns), Outside systems
(table: name, why, how it is called, what happens when it is down), Components (table per opened
container: component, responsibility, file), Open questions.
Stats on top: containers, outside systems, components drawn, guesses left. The verdict says in two
sentences what this system is and where a change is most likely to hurt.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/arch-c4-<YYYY-MM-DD>.*`. Write the
page in the language of the request; Serbian pages in Latin script.

## Reads

- the repository, its docs, the brief, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never draws a box or link from a repository as checked unless it was read; otherwise it is [guess].
- Never shows a secret or a setting's value: settings are named, not quoted. Never opens a `.env` file.
