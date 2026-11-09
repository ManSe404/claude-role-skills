---
name: data-map
description: Use when you inherit a data platform or must explain one, from its SQL, dbt, notebooks and pipelines, to map the sources, layers and consumers, the table lineage read from the code, the owners, the tables nobody reads and where personal data travels.
argument-hint: "[repository of the data platform]"
---

# Data map

The job: one page that explains a data platform from what its code does: where the data comes
from, which layers it passes, who reads it, who owns it, and where personal data travels. It
changes nothing.

Input: a repository of SQL, dbt, notebooks and pipelines. Default: the current repository.

## Steps

1. Inventory: `python3 "${CLAUDE_SKILL_DIR}/scripts/sql_inventory.py" REPO`, output to your
   scratchpad: tables, reads and writes per statement, DDL, dbt tests, dynamic SQL.
2. Read the code at every hit you use. A table or link you did not read is tagged [guess]. Dynamic
   SQL cannot be read by the script: open each place and say what it can touch.
3. Layers: from folders, schemas and names (`layer` in the output). What does not fit is listed,
   not forced in.
4. Consumers: dashboards, exports, APIs, whoever reads the last layer. A consumer outside the
   repository is an open question, not a guess.
5. Owners and change rate from git: `git log --format='%an' -- FILE` for the files that matter.
6. Orphans and cycles: `unread` means nobody in this repository reads it, which is a question to
   ask before it is a finding. Report `cycles` as they are.
7. Flows: the two to four most important tables traced hop by hop, from source to consumer, each
   step with file:line.
8. Personal data: where it starts, where it is masked, who it reaches. Use the names in the code;
   use `reach` to draw it.
9. Write the page JSON, with `facts`, render it, and say where to open it, with a link that opens
   the main flow (`page.html#flow=<id>&step=1`).

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format, including
`reach` and `facts`, and [references/example.json](references/example.json) for a filled page.

Sections in this order: The platform (an `architecture` block: zones for sources, each layer,
consumers, operations; links point the way the data goes; flows; `reach` for personal data), Lineage
(a `graph` block, grouped: under about 40 nodes), Tables (table: name, kind, layer, fed by, read by,
owner, file), Dynamic SQL (table: file:line and what it can touch), Nobody reads these (table), Where
personal data goes (text and the paths), Open questions.
Stats on top: tables, layers, consumers, dynamic SQL sites. The verdict says in two sentences what
this platform is and the first thing to look at.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/data-map-<YYYY-MM-DD>.*`. Write the
page in the language of the request; Serbian pages in Latin script.

## Reads

- the repository and its git history, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never connects to a database or a workspace; this map comes from the code.
- Never draws a link as checked unless it was read in the code; otherwise it is [guess].
- Never shows a secret or a connection string: settings are named, not quoted. Never opens a
  `.env` file.
