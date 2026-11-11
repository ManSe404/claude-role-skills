# Development

How to work on the repository. The rules an agent follows here are in [CLAUDE.md](../../CLAUDE.md); this guide gives
the commands and the order of work. Tests and evals are in [testing.md](testing.md).

## Set up

You need `uv`, Python 3.11 or newer, and the Claude Code CLI for `claude plugin validate` and the evals.

```bash
uv sync
```

`pyproject.toml` carries only the dev tooling (pytest, ruff, mypy); the skills themselves need nothing installed.

## Checks before a push

```bash
uv run pytest
uv run ruff format --check .
uv run ruff check .
uv run mypy
python3 tools/sync_shared.py --check
claude plugin validate .
```

CI (`.github/workflows/ci.yml`) runs format, lint, types, the shared-file sync and the tests on every push to `main`
and every pull request. `claude plugin validate` and the evals stay out of it: they need the Claude CLI and money.

## Changing a shared file

`shared/` is the single source of `render_page.py`, `page-format.md`, `fonts/`, `guard.py`, `chain_status.py`, the
shared scripts and `shared/cloud/`. Edit the file there, then write the copies:

```bash
python3 tools/sync_shared.py
```

Never edit a copy under a skill: the next sync overwrites it and the check fails until it does. A skill gets a copy
when its `SKILL.md` names the file; the table of names is `SHARED` in `tools/sync_shared.py`.

A change to `render_page.py` or `guard.py` reaches every skill. Check a change to the page by rendering an
`example.json` and looking at it (headless Chrome `--screenshot` does):

```bash
python3 shared/render_page.py plugins/ai-architect/skills/ai-architecture/references/example.json -o "$(mktemp -d)/page.html"
```

## Adding or changing a skill

1. Follow "Rules for a skill" in [CLAUDE.md](../../CLAUDE.md): the sections and their order, the length, the
   `description` and `when_to_use` budget, standard-library scripts, the `hooks:` block, the example page.
2. Name the shared files the skill needs in its `SKILL.md`, then run `python3 tools/sync_shared.py`.
3. Add the skill's name to its pack's `plugin.json` description (a test checks every skill is named there). When the
   pack's version moves, change it in `plugin.json` and `.claude-plugin/marketplace.json` together (a test checks
   they agree).
4. Produce `references/example.json` by running the skill on a fixture, check it by hand, and render it.
5. Add an eval case under `plugins/PACK/evals/` (a test checks every skill has one).
6. Update the documents the change makes wrong, in the same commit:
   - the pack's page in [product/features/](../product/features/) (what the skill writes, in words);
   - [reference/skills.md](../reference/skills.md), regenerated: from the repository root,
     `` awk '/^```$/{f=0} f; /^```python$/{f=1}' docs/reference/skills.md | python3 - ``;
   - [architecture/](../architecture/) and [diagrams/](../diagrams/) when the way the parts fit together changes;
   - [roadmap.md](../roadmap.md) when a planned step is built.

A new pack also needs its entry in `.claude-plugin/marketplace.json`, its `skills` folder in the mypy `files` of
`pyproject.toml`, a feature page, a row in the roadmap and, when the role is new, a starter in `roles/`.

## Adding a cloud provider

A provider is `shared/cloud/PROVIDER.md` and `shared/cloud/PROVIDER.json`. Nothing provider-specific goes in a
`SKILL.md` or in the core of a script, and tests check that. Every skill that names `references/cloud/` gets all
provider files on the next sync, so `tools/sync_shared.py` needs no change.

## Fixtures

A fixture is a made-up project: `fixtures/NAME/files/` (the state after the last commit; a `.fixture` suffix is
dropped on build), `history.py` (the commits) and `extras/` (logs and data, not committed). Build one with its
history into an empty folder:

```bash
python3 fixtures/build_fixture.py acme-orders "$(mktemp -d)/acme-orders"
```

Nothing real goes into a fixture or an example: fictional names, `example.*` addresses, no client data.
