# Plan: pack `data-architect`

Status: agreed with Stefan on 2026-11-09; built. The decisions are at the end.

## Goal

A pack for the person who designs a data platform. Before anything is built it decides what the
platform should be, from "report on the source" up to a data mesh. It designs the model with its
grain and keys, maps what exists from the code, and reviews it.

Same format as the other packs: `SKILL.md` in the fixed order, scripts that count, a page that is
JSON drawn by `render_page.py`.

Out of scope:
- writing or running production pipelines (data engineering);
- analysis, dashboards, queries for a question (the `data:*` skills, later the data analyst pack);
- prices of a platform: this pack sizes it in GB and rows, `cloud-architect` prices it.

Checked 2026-11-09:
- `wjlgatech/data-architecture` (MIT): five knowledge skills and an orchestrator, covering Data
  Vault, star schema, 3NF, governance and strategy. No scripts, so nothing is measured.
- `microsoft/skills-for-fabric` (53 SKILL.md): `e2e-medallion-architecture` builds on Fabric only.
- An existing data-engineering skill pack: profile, contract, lineage and model pages for one running
  platform, no decision on what the platform should be. Its `model.html` shows an entity as its key plus
  "+ N more columns", which is the right idea for the `model` block.

Nothing found joins the decision, a model checked against the data, lineage from the code and a
page. We take ideas, not code.

## Skills

### 1. `data-platform`: what the platform should be

When: a brief or a list of sources arrives, or a platform is being rethought.
Input: a brief (text or file), optionally a folder of samples.

Description: "Use before building or rebuilding a data platform, when a brief or a list of sources
arrives, to decide what it should be - reports on the source, one database with scheduled SQL, a
warehouse, a lakehouse, a streaming path or a data mesh - by eliminating options against the brief's
facts, ending in a decision page with sizing, the layers and an ADR draft."

Steps:
1. **Frame:** consumers and what they decide, sources, volumes, freshness per use, what cannot be
   negotiated (residency, retention, budget), the team. If facts that would change the decision are
   missing, ask for the 2–4 that matter most. If the user says go on, every assumption goes on the
   page with the decision it drives.
2. **Samples, if any:** `data_profile.py`.
3. **Hard rules and sizing:** `platform_rules.py FACTS.json`.
4. **The remaining options, in order:** can this team run it, freshness, cost of wrong data,
   governance, cost. The first factor that rules an option out decides it and gets named.
5. **Ladder:** start at the lowest open option and climb only for a named requirement.
6. **Paths:** only the paths that need streaming get it, not the whole platform.
7. **Layers:** what each keeps, for how long, who may read it.
8. **What would change the decision:** 3–5 conditions.
9. **Acceptance criteria:** 3–5 measures, each with a threshold and how it is measured.
10. **ADR (Nygard):** a draft in a code block; into a repository only after the yes.
11. **The page.**

On the page: the verdict with the deciding constraint, a `decision` block, an `architecture` block
of the layers with `reach` for personal data, sizing, assumptions, what would change it, criteria, ADR.

Never:
- proposes a lakehouse when a database passes;
- gives a vendor's price, limit or region without its date and source;
- sends the brief off this machine.

### 2. `data-model`: the model, its grain and its keys

When: a subject area must be modelled, or an existing model understood.
Input: DDL, a dbt project or sample files, and the questions the model must answer.

Description: "Use when a subject area of a data platform must be modelled, from source schemas, DDL,
dbt or sample files, to choose between one wide table, star schema, 3NF and Data Vault, state the
grain of every fact, find the keys from the data, decide the history and mark personal data, ending
in a clickable model and DDL drafts."

Steps:
1. **Questions:** what the model must answer, and which business processes produce it.
2. **Inventory:** `sql_inventory.py` for DDL and dbt, `data_profile.py` for samples.
3. **Approach, simplest first:** one wide table, star schema, 3NF, Data Vault. Each climb needs a
   named reason, for example several sources disagreeing about one entity, or a full audit demand.
4. **Grain:** one sentence per fact. With samples, check it: `data_profile.py --grain TABLE K1,K2`
   counts the duplicates at that grain.
5. **Keys:** business keys, surrogate keys, how keys from different sources map to each other.
   Candidates come from the script, not from column names alone.
6. **Dimensions:** which are shared across facts, as a bus matrix.
7. **History:** a type (overwrite, new row, snapshot) per attribute that matters, with the reason.
8. **Personal data:** a class per column, and where it is masked.
9. **Check:** `model_check.py MODEL.json`, fix what it reports.
10. **DDL draft:** in a code block; into a repository only after the yes.
11. **The page.**

On the page: the verdict, stats (tables, facts, unchecked grains, personal columns), a `model` block,
the bus matrix, grain per fact with the measured duplicates, keys, history, DDL.

Never:
- leaves a fact without its grain;
- states a key as checked unless the data was counted, else it is `[guess]`;
- shows a personal value: columns and counts only.

### 3. `data-map`: what exists

When: you inherit a data platform or have to explain one.
Input: a repository of SQL, dbt, notebooks and pipelines.

Description: "Use when you inherit a data platform or must explain one, from its SQL, dbt, notebooks
and pipelines, to map the sources, layers and consumers, the table lineage read from the code, the
owners, the tables nobody reads and where personal data travels."

Steps:
1. **Inventory:** `sql_inventory.py REPO`: tables, reads and writes per statement, dynamic SQL.
2. **Read the code** at every hit you use. A table or link you did not read is `[guess]`.
3. **Layers:** from folders, schemas and names; what does not fit is listed, not forced in.
4. **Consumers:** dashboards, exports, APIs, whoever reads the last layer.
5. **Owners and change rate** from git.
6. **Orphans and cycles:** tables nobody reads, tables that feed themselves.
7. **Flows:** the 2–4 most important tables traced hop by hop from source to consumer.
8. **Personal data:** where it starts, where it is masked, who it reaches (`reach`).
9. **The page.**

On the page: an `architecture` block with layers and flows, a `graph` of the lineage (click to
trace), the table inventory with a filter, the paths of personal data, open questions.

Never:
- connects to a database or a workspace;
- draws a link as checked unless it was read in the code;
- shows a secret or a connection string. Never opens a `.env` file.

### 4. `data-review`: what is wrong with it

When: before a release, when taking over, before handing over.
Input: a repository, optionally samples.

Description: "Use before a release, when you take over, or before you hand over a data platform, to
review its models and loads in the code against the common failures - mixed grain, joins that
multiply rows, loads that cannot be rerun, layers skipped, personal data served unmasked, money as
floats, history overwritten, keys without tests - with file:line findings and fixes."

Steps:
1. **Scripts:** `sql_inventory.py REPO --checks`, and `data_profile.py` when there are samples.
2. **Confirm** every hit by reading it; the script's hits are keyword matches.
3. **What a script cannot see:** walk `references/anti-patterns.md` (grain, history, ownership).
4. **Measure** where samples allow it, for example how many rows a join multiplies.
5. **Findings:** severity, file:line, evidence, fix, order of the fixes.
6. **The page:** findings, and the map with the problem spots flagged.

Never:
- changes a file;
- shows a personal value or a secret;
- reports a finding it did not read in the code.

## Scripts

All standard library, read-only, JSON on stdout.

| script | skills | what it does |
|---|---|---|
| `data_profile.py` (shared) | data-platform, data-model, data-review | CSV and JSON Lines: rows, size, types, nulls, distinct values, date range, candidate keys, overlap between columns of different files, duplicates at a grain (`--grain`), personal-data hits by name and by value checks (e-mail, IBAN mod 97, JMBG check digit). Prints counts, never personal values. |
| `sql_inventory.py` (shared) | data-model, data-map, data-review | Comments and strings stripped first. T-SQL, PostgreSQL, Spark SQL, dbt (`ref`, `source`, `schema.yml`), notebooks (`.ipynb`, `spark.sql`, `saveAsTable`, `read.table`). Tables, columns from DDL, reads and writes per statement, CTEs excluded. Dynamic SQL is reported as such with file:line. `--checks` adds families of hits for the review. |
| `platform_rules.py` | data-platform | Input: the brief's facts as JSON. Applies the hard rules, prints the options still open, the lowest open one, and the unknown facts that would eliminate something. Never chooses. Also sizing: total after two years, daily ingest. |
| `model_check.py` | data-model | Input: the `model` block. Every fact has a grain, every relation resolves, no n:n without a bridge, every personal column has a masking decision, every tracked attribute a history type. |

Ladder for `platform_rules.py`, by moving parts: reports on the source or a replica, one database
with scheduled SQL, a managed warehouse, a lakehouse in layers, a lakehouse with a streaming path, a
data mesh.

Rules, as a first set. Each threshold is a judgement, stated in the script and shown on the page:
- several sources joined, history the source overwrites, or a source that cannot take the load:
  reports on the source are out;
- more than about 2 TB after two years: one database is out;
- files, images or models trained on raw data: everything without file storage is out;
- freshness under 5 minutes on any path: options without a streaming path are out;
- no data engineer: anything that must be operated is out, a lakehouse and up;
- fewer than three domain teams with their own engineers: a mesh is out.

Two limits, on purpose:
- table-level lineage only, no column lineage in this version;
- no SQL parser package, because an installed skill cannot assume one. Accuracy is measured on the
  fixture, and what it cannot resolve is listed as dynamic.

`tools/sync_shared.py` gets two more markers for the shared scripts.

## Renderer (`shared/`, changes every pack's pages)

**`model` block:**
- `areas` [{id, label}];
- `tables` [{id, label, area, kind: fact, dimension, bridge, hub, link, satellite, staging, table;
  grain, note, flag, columns: [{name, type, key: pk, fk, bk; personal, note}]}];
- `relations` [{from, to, on, cardinality: 1:1, 1:n, n:1, n:n, label}].

A box shows its name, kind, primary key and "+ N more columns". A click opens a card with every
column and traces the related tables, as graphs do. Filter by area, `#table=` opens a state. Without
the script and in print: one table per entity. Layout uses the existing graph helpers.

**`reach` on the `architecture` block**, a second computed view beside the AI trust view:

```json
"reach": {"label": "Personal data", "from": ["crm"], "stops": ["mask"], "targets": ["bi", "export"]}
```

Walks links forward only, from `from`, stops at `stops`, and lists every target reached with its
shortest path. A toggle shows it on the drawing; `#reach=1` opens it. Used for personal data here and
for internet exposure in `cloud-architect`. No new `kind` is needed: sources are `system`, jobs are
`service`, layers are `store`, masking is `guard`, consumers are `user` or `channel`. For a data
platform, links point the way the data goes.

<a id="facts"></a>
**`facts` at the top of the page JSON,** validated but not drawn:

```json
"facts": {
  "version": 1,
  "scope": "the data platform of Acme Foods",
  "regions": [{"name": "EU", "why": "residency"}],
  "data": [{"name": "customer contact", "class": "personal", "where": ["silver.customers"], "rule": "EU only"}],
  "components": [{"id": "lake", "label": "Lakehouse", "tech": "not chosen", "kind": "store"}],
  "costs": [{"item": "…", "monthly": 420.0, "currency": "EUR", "as_of": "2026-11-09", "source": "…"}],
  "decisions": [{"title": "Platform", "chosen": "Lakehouse", "because": "…"}],
  "assumptions": ["…"],
  "open": ["…"]
}
```

Every skill that decides or maps fills it. `ai-pattern`, `ai-stack` and `ai-architecture` get one more
step, and their examples are filled by hand.

Tests: validation errors with their JSON path, escaping, same JSON gives same HTML, no external
URL, every relation and reach id resolves, `reach` stops where it should, the browser test covers
the model card and the toggle. Pages already rendered by other packs must not change.

## Fixture: `fixtures/acme-data/` (all fictional)

**`brief-reports.md`:** an ERP and a budget spreadsheet, 3 GB, refreshed daily, one analyst, no
engineer. The right answer is one database with scheduled SQL. This brief checks that the skill does
not overbuild.

**`brief-platform.md`:** 14 sources (ERP, CRM, web events, sensors, supplier PDFs), 35 TB, one stock
feed that must be two minutes fresh, models trained on images, EU only, six engineers in one team.
The right answer is a lakehouse with a streaming path for that one feed. A mesh is ruled out by the
single team.

**`extras/data/`:** sample CSVs, generated deterministically: orders, order lines, customers, products,
stores, promotions. Planted: duplicated customer keys, orphan order lines, decimal commas, mixed date
formats, fictional personal columns.

**`files/` + `history.py`:** a small dbt-style project with staging, intermediate and marts, a T-SQL
procedure, a Spark notebook and an export. Eight planted problems for `data-review`:
1. a fact joined to promotions on a key that is not unique, so rows multiply;
2. a procedure that inserts with no delete or merge, so a rerun doubles the day;
3. a report that reads the staging layer directly;
4. e-mail and a national ID served to a marketing export with no masking;
5. money stored as FLOAT;
6. a product price overwritten in place while past sales join to it;
7. no `unique` or `not_null` test on the keys of the main fact;
8. dynamic SQL built by concatenating a parameter.

The list also goes into a test, like `acme-assist`.

## Evals (`claude plugin eval`)

1. **platform-does-not-overbuild:** `brief-reports` ends in one database, with no lakehouse.
2. **platform-names-the-constraint:** `brief-platform` ends in a lakehouse with streaming on one path
   only, and the mesh is eliminated by the team count.
3. **model-grain-and-keys:** every fact has a grain, the duplicates come from the script, personal
   columns are marked, and no personal value appears on the page.
4. **map-lineage-from-code:** the planted edges are present and the dynamic SQL is tagged.
5. **review-finds-planted:** finds at least 6 of 8 and changes no file.

Each case also has a `skill-fired` grader. Evals run only when Stefan asks.

## Other

- `roles/data-architect.md`, a CLAUDE.md starter: simplest thing that passes, the confidence tags,
  dated facts, client data never in examples, no personal value on a page.
- `references/platforms.md`, `modeling.md` and `anti-patterns.md`: short, without prices.
- Descriptions must say "data platform" or "subject area", so `data-map` does not take requests from
  `codebase-map`, and `data-model` does not take them from `data:explore-data` or `data:sql-queries`.
- Pages follow the language of the request. Serbian pages in Latin script, because the fonts have no
  Cyrillic.
- Update the README table, the marketplace, `plugin.json` and the repo's CLAUDE.md.

## Order

- M1: references, fixture and fixture tests.
- M2: renderer (`model`, `reach`, `facts`), tests, `tools/sync_shared.py`, `facts` for `ai-architect`.
- M3: four scripts and their tests on the fixture.
- M4: four `SKILL.md` and `references/example.json`, from headless runs on the fixture, checked by
  hand (about $10).
- M5: evals written; run only on request.
- M6: README, marketplace, role starter, notices. Green at the end: pytest, ruff, mypy strict,
  `claude plugin validate .`.

## Decisions (Stefan, 2026-11-09)

1. Names as proposed.
2. Sizing only in this pack; `cloud-architect` summarises the prices for each cloud.
3. Table-level lineage only.
4. Thresholds as proposed: 2 TB after two years for one database, five minutes for a streaming path,
   three domain teams for a mesh. Each is printed on the page, so a reader can disagree.
5. The SQL reader covers T-SQL, PostgreSQL, Spark SQL, dbt and notebooks. Azure Data Factory and
   Fabric pipeline JSON can come later.
