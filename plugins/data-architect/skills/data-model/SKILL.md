---
name: data-model
description: Use when a subject area of a data platform must be modelled, from source schemas, DDL, dbt or sample files, to choose between one wide table, star schema, 3NF and Data Vault, state the grain of every fact, find the keys from the data, decide the history and mark personal data, ending in a clickable model and DDL drafts.
argument-hint: "[DDL, dbt project or samples folder] [the questions it must answer]"
---

# Data model

The job: a model of one subject area that someone can build from, with every decision made on
purpose: the grain, the keys, the history, the personal data. It changes nothing in a repository;
DDL goes in only after the yes.

Input: DDL, a dbt project or a folder of sample files, and the questions the model must answer.
Default: the current repository; ask for the questions.

## Steps

1. Read [references/modeling.md](references/modeling.md): the approaches, grain, keys, history and
   the classes of personal data.
2. Questions: what the model must answer, who asks, and which business processes produce the data.
3. Inventory: `python3 "${CLAUDE_SKILL_DIR}/scripts/sql_inventory.py" REPO` for DDL and dbt, and
   `python3 "${CLAUDE_SKILL_DIR}/scripts/data_profile.py" FOLDER` for samples, output to your
   scratchpad. Types, nulls, candidate keys and overlaps come from these, not from column names.
4. Approach, simplest first: one wide table, star schema, 3NF, Data Vault. Each climb needs a named
   reason, for example several sources disagreeing about one entity, or a full audit demand.
5. Grain: one sentence per fact. With samples, check it:
   `data_profile.py FOLDER --grain TABLE K1,K2` counts the duplicates at that grain. A grain you
   could not count is tagged [guess].
6. Keys: business keys, surrogate keys, and how keys from different sources map to each other. Use
   the overlaps: orphan rows and joins that multiply rows are findings.
7. Dimensions: which are shared across facts, as a bus matrix.
8. History: overwrite, new row or snapshot, per attribute that matters, with the reason. An
   attribute that past facts depend on must not be overwritten.
9. Personal data: a class per column, and where it is masked or dropped (`mask`).
10. Write the `model` block as JSON and run
    `python3 "${CLAUDE_SKILL_DIR}/scripts/model_check.py" MODEL.json`. Fix every error; answer or
    accept every warning.
11. DDL draft in a code block. Offer to write it into the repo; write only after the yes.
12. Write the page JSON, with `facts`, render it, and say where to open it, with a link that opens
    the main fact (`page.html#table=<id>`).

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format, including the
`model` block and `facts`, and [references/example.json](references/example.json) for a filled page.

Sections in this order: The questions (list), What the data says (table per source: rows, keys,
problems found, with the counts), Approach (a `decision` block, simplest first), The model (a `model`
block), Grain (table: fact, grain, duplicates measured), Keys (table: entity, business key, how
sources map, orphans), Bus matrix (table: facts by dimensions), History (table: attribute, type,
why), Personal data (table: column, class, masked where; columns and counts only), DDL draft (code),
Open questions. Stats on top: tables, facts, grains checked against data, personal columns. The
verdict says the approach and the biggest data problem the model must absorb.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/data-model-<YYYY-MM-DD>.*`. Write the
page in the language of the request; Serbian pages in Latin script.

## Reads

- the DDL, the dbt project, the samples and the repository, read-only

## Writes

- the page and its JSON, outside the repo; the DDL only after the yes

## Never

- Never leaves a fact without its grain.
- Never states a key or a grain as checked unless the data was counted; otherwise it is [guess].
- Never shows a personal value: columns and counts only. Never opens a `.env` file.
