# Architecture overview

How the packs, the skills, the shared files, the page renderer, the guard hooks and the evals fit together. The
drawings are in [diagrams/](../diagrams/): [container view](../diagrams/container.md),
[a skill run](../diagrams/skill-run.md) and [a workflow chain](../diagrams/workflow-chain.md).

## Context

Nothing here runs as a service. The repository is a Claude Code plugin marketplace: Claude Code installs a pack from
it, picks a skill when a request matches the skill's description (or when the person calls it as `/PACK:SKILL`),
and then follows the skill's `SKILL.md`. The skill's scripts run on the person's machine with `python3`, read the
repository or the data the person points at, and print JSON. Claude writes the page as JSON, and the skill's copy of
`render_page.py` draws it into a pages folder outside the repository.

## Goals and constraints

- **A skill works on its own.** An installed plugin has nothing outside its own folder, so every file a skill needs
  is inside `plugins/PACK/skills/SKILL/`. Shared code is copied in, never imported from outside.
- **Claude picks a skill from two lines.** The `description` and `when_to_use` in the frontmatter are all Claude sees
  before it loads the body; together they stay under 400 characters, because with many skills installed Claude Code
  cuts long descriptions.
- **Scripts count, Claude writes.** Scripts are Python 3.11+, standard library only, read-only, JSON on stdout. Every
  outbound call has a timeout and is opt-in.
- **One page, one file.** A page embeds its fonts and script and fetches nothing, so it can be sent to anyone.
- **Read-only until the yes,** enforced by a hook where a program can check it.
- **The same answer twice.** Fixtures are built deterministically, scripts have fixed output, and the tests pin both.

## Building blocks

| Block | Where | What it does |
|---|---|---|
| Marketplace | `.claude-plugin/marketplace.json` | one entry per pack: name, source folder, description, version |
| Pack | `plugins/PACK/.claude-plugin/plugin.json` | name, version, description, licence; `dependencies` makes installing `solutions-architect` or `workflows` install the packs they build on |
| Skill | `plugins/PACK/skills/SKILL/SKILL.md` | frontmatter (`name`, `description`, `when_to_use`, `argument-hint`, `hooks`), then the job, input, Steps, Output, Reads, Writes, Never |
| Skill scripts | `plugins/PACK/skills/SKILL/scripts/` | the skill's own counting scripts and its copies of the shared ones |
| Skill references | `plugins/PACK/skills/SKILL/references/` | `example.json` (a filled page from a run on a fixture), `page-format.md`, and the rules or tables the skill reads in its steps |
| Shared files | `shared/` | the single source of `render_page.py`, `page-format.md`, `fonts/`, `guard.py`, `chain_status.py`, the scripts several skills use, and `cloud/` (one `.md` and `.json` per cloud provider) |
| Sync | `tools/sync_shared.py` | copies each shared file into every skill whose `SKILL.md` names it; `--check` fails when a copy is missing or differs |
| Renderer | `shared/render_page.py` | validates a page JSON and draws it as HTML (`-o`), as a Markdown note (`--md`), as a set of pages with one header (`--site`), or as an index of a folder (`--index`); `--check` validates only |
| Guard | `shared/guard.py` | the hook behind every skill's Never rules, see [crosscutting.md](crosscutting.md) |
| Chain status | `shared/chain_status.py` | for a workflow: each step's newest page in a pages folder, with its date, verdict, findings and open items |
| Fixtures | `fixtures/acme-*/`, `fixtures/build_fixture.py` | made-up projects with planted problems, built with their git history into an empty folder |
| Evals | `plugins/PACK/evals/CASE/` | cases for `claude plugin eval`: `case.yaml`, `prompt.md`, `fixture.sh` and `graders/` |
| Selection check | `tools/selection_check.py`, `tools/selection_cases.json` | which skill Claude picks when every pack is loaded at once |
| Eval table | `tools/eval_table.py` | sums up the eval results under `plugins/PACK/evals/results/` into one Markdown page |
| Role starters | `roles/` | a CLAUDE.md starter per role, for a project that uses the skills |
| Tests and CI | `tests/`, `.github/workflows/ci.yml` | pytest for the scripts, the renderer, the guard, the fixtures and the skill files; CI runs format, lint, types, the sync check and the tests |

The full map of the repository is [reference/codebase.md](../reference/codebase.md); every pack and skill, with its
scripts and guard, is [reference/skills.md](../reference/skills.md).

## How a shared file reaches a skill

`shared/` is the only place a shared file is edited. `tools/sync_shared.py` holds a table of markers: when a skill's
`SKILL.md` names a marker (for example `render_page.py`, `data_profile.py` or `references/cloud/`), the skill gets the
files behind it at fixed places (`scripts/`, `references/`, `assets/fonts/`). Every skill names `render_page.py` and
`guard.py`, so every skill carries both. The copies are committed, because the installed plugin is the folder as it
is in git. `tests/test_skill_files.py` and CI run the sync with `--check`, so a shared file edited without a sync fails
the build.

A cloud provider is one pair of files, `shared/cloud/PROVIDER.md` and `.json`. Nothing provider-specific goes in a
`SKILL.md` or in the core of a script; a test checks that the cloud skills and the core cloud scripts name no
provider.

## How a skill runs

See [the skill run diagram](../diagrams/skill-run.md).

1. Claude Code lists every installed skill by its `description` and `when_to_use`. When a request matches, or the
   person calls the skill by name, Claude loads the body of `SKILL.md` and Claude Code registers the skill's `hooks:`.
2. The steps run the skill's scripts as `python3 "${CLAUDE_SKILL_DIR}/scripts/NAME.py"`; most skills keep the output in
   Claude's scratchpad, never in the repository. The numbers on the page come from the scripts.
3. Claude reads what the scripts point at, tags every claim it did not count (`[high]`, `[med]`, `[guess]`) and
   writes the page as JSON in the pages folder.
4. `render_page.py` validates the JSON, prints each problem with its JSON path, and draws the page. A text-only skill
   renders the Markdown note first and the page beside it. Then `--index` refreshes the folder's index.
5. During that turn the guard runs on every tool call. After the person's next message it steps aside, so what a
   skill does "after the yes" runs under the person's normal permissions.

## The page and its JSON

A page is JSON: `skill`, `title`, `sections` of typed blocks, and on top a `verdict` and `stats`. The format, every
block type and the rule that a page never holds a path from the machine that made it are in
[shared/page-format.md](../../shared/page-format.md). The look and the interactions are in
[design/page-design.md](../design/page-design.md).

Pages go outside the repository, to `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/REPO/SKILL-DATE.json`, with the `.html`
(and the `.md` note) beside it. The JSON is kept so a later run can compare.

`facts`, at the top level of the JSON, is not drawn. It holds what a page decided or found in one shape (scope,
regions, data classes, components, dated costs, decisions, assumptions, open items), so a later skill can join pages:
`solution-blueprint` reads the specialists' `facts`, and a workflow step reads the previous step's.

## Workflows

A workflow is a skill whose steps call other skills with the Skill tool, in order. See
[the workflow chain diagram](../diagrams/workflow-chain.md). `chain_status.py` lists which steps already have a valid
page from today, so a chain resumes where it stopped; each step reads the previous step's page JSON, never its prose;
the chain ends in one note and page with each step's verdict, what was found, what is still open, and whether the
chain is done by the rule written in the skill. The `workflows` pack depends on every other pack, so installing it
installs them.

## How it is checked

- **Unit tests** (`uv run pytest`) cover the scripts, the renderer, the guard, the page script, the fixtures, the
  selection check and the skill files: the frontmatter, the exact form of the `hooks:` block, the sync, and that the
  marketplace and the pack manifests agree on names, versions and the skills each description lists.
- **Fixtures** are made-up projects with planted problems and decoys. The scripts are tested against them, the
  example pages come from running the skills on them, and the evals run on them.
- **Evals** (`claude plugin eval`) start real Claude sessions on a built fixture and grade what came out. They cost
  money and are run by hand.
- **The selection check** loads every pack at once and asks which skill Claude picks for each prompt, which one-pack
  evals cannot show.

How to run each is in [guides/testing.md](../guides/testing.md).

## Open

- `pyproject.toml` lists every pack's `skills` folder for mypy except `plugins/workflows/skills`. The workflow skills
  have no scripts of their own, only shared copies, so nothing goes unchecked as long as that holds.
- The `plugin.json` description of `cloud-architect` ends in "Azure first", while AWS is built too.
