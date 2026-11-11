# Codebase map

What is where in the repository. Every pack and skill, with its scripts, is listed in [skills.md](skills.md); how the
parts work together is in [architecture/overview.md](../architecture/overview.md).

## Top level

| Path | What it is |
|---|---|
| `README.md` | what the repository is, install, the link to these documents |
| `CLAUDE.md` | rules for agents working in the repository: layout, rules for a skill, checks |
| `.claude-plugin/marketplace.json` | the marketplace: one entry per pack, with its source folder, description and version |
| `plugins/` | the packs, one folder each |
| `shared/` | the single source of the files copied into the skills |
| `tools/` | repository tools: the sync, the selection check, the eval table |
| `fixtures/` | made-up projects the tests, the example pages and the evals run on |
| `roles/` | a CLAUDE.md starter per role |
| `tests/` | pytest |
| `docs/` | these documents; [README.md](../README.md) is the index |
| `.github/workflows/ci.yml` | CI on every push to `main` and every pull request |
| `pyproject.toml`, `uv.lock` | the dev tooling only (pytest, ruff, mypy) and its settings; the skills need nothing installed |
| `LICENSE`, `THIRD-PARTY-NOTICES.md` | MIT; the notices for the page design and the fonts |

## A pack: `plugins/PACK/`

| Path | What it is |
|---|---|
| `.claude-plugin/plugin.json` | name, description (must name every skill of the pack), version, author, licence, keywords, and `dependencies` for a pack that builds on others |
| `skills/SKILL/SKILL.md` | the skill: frontmatter, then the job, input, Steps, Output, Reads, Writes, Never |
| `skills/SKILL/scripts/` | the skill's own scripts and its copies of shared scripts (`render_page.py` and `guard.py` in every skill) |
| `skills/SKILL/references/` | `example.json` (a filled page), `page-format.md` (a copy), the rules and tables the steps read, and `cloud/` for the cloud skills |
| `skills/SKILL/assets/fonts/` | copies of the fonts, inlined into every page |
| `evals/CASE/` | one eval case: `case.yaml`, `prompt.md`, `fixture.sh` (builds the fixture), `graders/` |
| `evals/results/` | what `claude plugin eval` writes; ignored by git |

## `shared/`

Edit these here, then run `python3 tools/sync_shared.py`. Never edit a copy under a skill.

| File | What it does |
|---|---|
| `render_page.py` | renders a skill's page JSON into one self-contained HTML file; also `--md`, `--site`, `--index`, `--check` |
| `page-format.md` | the page JSON format every skill writes |
| `fonts/` | Bricolage Grotesque and JetBrains Mono (Latin and Latin Extended) and their licence |
| `guard.py` | enforces a skill's Never rules while the skill is working; Claude Code runs it as a hook |
| `chain_status.py` | where a chain of skills stands in one pages folder: each step's newest page, date, verdict, findings and open items |
| `ai_inventory.py` | inventories the AI parts of a repository: what calls a model, with which settings, and what the model can reach |
| `audit_scan.py` | finds the places in a repository where a bug review should read first, and the promises its docs make |
| `code_graph.py` | measures the structure of a repository: the module graph, its cycles and layer breaks, and what git says |
| `containers.py` | finds what runs in a repository, what it talks to, and what deployables share |
| `data_profile.py` | profiles sample data files: shape, keys, overlaps between files and personal data |
| `incident_timeline.py` | one timeline from log files, the git history and deploy markers, with the counts an incident needs |
| `measure.py` | counts one measure on sample data: filters, a time window, one row per key, then a sum, a count or a ratio |
| `model_stats.py` | the statistics the data-scientist scripts share; imported, not run |
| `sql_inventory.py` | reads a repository's SQL, dbt models and notebooks into a table-level inventory and lineage |
| `cloud_inventory.py` | reads a repository's cloud infrastructure code into one normalised inventory |
| `cloud_prices.py` | prices a bill of materials against a provider's list prices |
| `cloud/PROVIDER.md`, `cloud/PROVIDER.json` | one pair per cloud provider (`azure`, `aws`): everything provider-specific |

## `tools/`

| File | What it does |
|---|---|
| `sync_shared.py` | copies the shared files into every skill that names them; `--check` exits 1 when a copy is missing or differs |
| `selection_check.py` | loads every pack and checks which skill Claude picks for each prompt; real model calls |
| `selection_cases.json` | the prompts for the selection check, each with the skills that are a right answer |
| `eval_table.py` | sums up the eval results under `plugins/PACK/evals/results/` into one Markdown page |

## `fixtures/`

`build_fixture.py NAME TARGET_DIR` builds a fixture with its git history into an empty folder. A fixture is
`files/` (the state after the last commit; a `.fixture` suffix is dropped on build), `history.py` (the commits) and
optional `extras/` (files on disk but not committed, such as logs and data exports). The build is deterministic and
ignores the machine's global git config.

| Fixture | What it is (all fictional) |
|---|---|
| `acme-orders` | an order service with a git history, a real bug, untested modules, old pins and a production log |
| `acme-assist` | an AI support prototype with two client briefs, a corpus in English and Serbian (Latin and Cyrillic, with PDFs and a duplicate) and eight planted design flaws |
| `acme-data` | a data platform with two briefs, sample data and eight planted problems |
| `acme-logistics` | a .NET, TypeScript and Python system with eight structural problems |
| `acme-cloud` | an Azure estate in Terraform and Bicep with eight planted problems and drift |
| `acme-cloud-aws` | an AWS estate in Terraform and CloudFormation with planted problems and drift |
| `acme-solution` | a client brief with the specialist pages written about it and ten planted conflicts between them |
| `acme-sales` | a sales analytics project with planted metric problems, a late day and two systems that disagree |
| `acme-churn` | a churn model with its training and scoring data |
| `acme-design` | design documents with eight planted flaws and three decoys |
| `acme-index` | an indexing service with seven planted bugs and four decoys |
| `acme-pipeline` | a food distributor's data platform with planted problems and decoys for every data-engineer skill |

The cloud fixtures hold the only real data in the repository: public Azure and AWS list prices.

## `tests/`

| Files | What they cover |
|---|---|
| `test_skill_files.py` | every SKILL.md, manifest and eval case: sections and frontmatter, links that resolve, the `hooks:` block and that the hook command finds the guard or steps aside, provider-free cloud skills, the shared sync, the marketplace against the manifests, an eval for every skill, graders that never read the whole trace, no real addresses in examples and fixtures |
| `test_render_page.py` | the renderer: validation and the blocks |
| `test_flow_index_md.py` | the `flowchart` block, the Markdown note (`--md`) and the folder index (`--index`) |
| `test_site_header.py` | a set of pages with one header (`--site`) |
| `test_page_script.py` | the page script in a real browser: click-to-trace, the table filter and the copy button; skipped when no Chrome or Chromium is installed |
| `test_guard.py` | the guard hook |
| `test_scripts*.py` | the skills' scripts, grouped by pack or theme |
| `test_fixture*.py` | each fixture builds as described and holds its planted problems |
| `test_selection_check.py` | the selection check: its cases name real skills and the judging is right; it calls no model |
| `conftest.py` | helpers that load and run the scripts, and session fixtures that build the acme fixtures |

## `roles/`

One CLAUDE.md starter per role (`software-engineer`, `ai-architect`, `data-architect`, `data-engineer`,
`software-architect`, `cloud-architect`, `solutions-architect`, `data-analyst`, `data-scientist`): how Claude works with
that role's skills, to copy into a project and adapt.
