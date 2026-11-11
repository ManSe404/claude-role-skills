# claude-role-skills

Claude Code skills by role, one marketplace with one plugin per role: `software-engineering`,
`ai-architect`, `data-architect`, `data-engineer`, `software-architect`, `cloud-architect`, `solutions-architect` (on top of the
four specialist packs), `data-analyst` and `data-scientist` so far. `docs/plans/` holds the plans.

## Layout

- `plugins/<role>/skills/<skill>/` holds `SKILL.md`, `scripts/` and `references/`. A skill must
  work on its own, because an installed plugin has nothing outside its own folder.
- `shared/` is the single source of `render_page.py`, `page-format.md`, `fonts/`,
  `ai_inventory.py`, `data_profile.py`, `sql_inventory.py`, `measure.py`, `model_stats.py`, `guard.py`, `code_graph.py`, `containers.py`,
  `audit_scan.py`, `incident_timeline.py`,
  `cloud_inventory.py` and `cloud_prices.py`, and of `shared/cloud/`, one file per cloud provider. Edit them
  there, then run `python3 tools/sync_shared.py`; a skill gets a copy when its SKILL.md names the file.
  Never edit the copies under a skill. A cloud provider is `shared/cloud/<provider>.md` and `.json`:
  nothing provider-specific goes in a SKILL.md or in the core of a script.
- The page design is a hive (honey on dark amber, hexagons) and dark only; it lives in the CSS of `render_page.py` and in
  `_hex_plate`. Check a change by rendering an `example.json` and looking at it (headless Chrome `--screenshot` does).
  `render_page.py` also writes a folder index (`--index`) and a Markdown note of a page (`--md`).
- `fixtures/<name>/` is a made-up project: `files/` (state after the last commit, `.fixture`
  suffix dropped on build), `history.py` (the commits) and `extras/` (logs and data, not committed).
- `plugins/<role>/evals/` holds the eval cases for `claude plugin eval`.
  In that sandbox shell commands cannot write files, so `page-made` checks the page's JSON, not its HTML. A grader
  never reads `target: trace`: the trace holds the text of SKILL.md, so a pattern found there proves nothing. Use
  `tool_used` on `Bash` with `input_match`. An `llm` grader sees only the final reply and not the code or the page.

## Rules for a skill

- `SKILL.md` sections in this order: the job, input, Steps, Output, Reads, Writes, Never. Under 120 lines.
- Claude picks a skill from its `description` and `when_to_use` alone; the body loads after. `description` says
  in one sentence what the skill does. `when_to_use` starts with "Use when" or "Use before" and says in one or two
  sentences when, and where a neighbouring request goes. Together under 400 characters: with many skills installed
  the listing is over its budget and Claude Code cuts descriptions.
- Scripts: Python 3.11+, standard library only, read-only, JSON on stdout, referenced as
  `${CLAUDE_SKILL_DIR}/scripts/<name>.py`. Every outbound call has a timeout and is opt-in.
- Every SKILL.md frontmatter has the `hooks:` block that runs `scripts/guard.py` (a copy of `shared/guard.py`), with
  `personal` for the skills that ship `data_profile.py`. `tests/test_skill_files.py` holds its exact form. The
  command looks for the guard in the plugin, the project and `~/.claude`, and exits 0 when it is missing: a script
  python cannot open exits 2, and exit 2 blocks the call. `${CLAUDE_SKILL_DIR}` does not expand in hook commands.
- A page is JSON rendered by `render_page.py`; `references/example.json` is the filled example,
  produced by running the skill on the fixture and then checked by hand. A text-only skill renders the note
  (`--md`) first and the page beside it; `shared/page-format.md` lists those skills.
- Nothing real in fixtures and examples: fictional names, `example.*` addresses, no client data.

## Checks

`uv run pytest`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`,
`claude plugin validate .`. Evals cost money: run them only when asked.
