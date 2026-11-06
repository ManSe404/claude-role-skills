# claude-role-skills

Claude Code skills by role, one marketplace with one plugin per role. Only the software
engineering pack exists so far.

## Layout

- `plugins/<role>/skills/<skill>/` holds `SKILL.md`, `scripts/` and `references/`. A skill must
  work on its own, because an installed plugin has nothing outside its own folder.
- `shared/` is the single source of `render_page.py`, `page-format.md` and `fonts/`. Edit them
  there, then run `python3 tools/sync_shared.py`. Never edit the copies under a skill.
- The page design is dark only, after Data With Baraa's skills; it lives in the CSS of
  `render_page.py`. Check a change by rendering an `example.json` and looking at it.
- `fixtures/<name>/` is a made-up project: `files/` (state after the last commit, `.fixture`
  suffix dropped on build), `history.py` (the commits) and `extras/` (logs and data, not committed).
- `plugins/<role>/evals/` holds the eval cases for `claude plugin eval`.

## Rules for a skill

- `SKILL.md` sections in this order: the job, input, Steps, Output, Reads, Writes, Never. The
  description starts with "Use when" or "Use before" and says when, not how. Under 120 lines.
- Scripts: Python 3.11+, standard library only, read-only, JSON on stdout, referenced as
  `${CLAUDE_SKILL_DIR}/scripts/<name>.py`. Every outbound call has a timeout and is opt-in.
- A page is JSON rendered by `render_page.py`; `references/example.json` is the filled example,
  produced by running the skill on the fixture and then checked by hand.
- Nothing real in fixtures and examples: fictional names, `example.*` addresses, no client data.

## Checks

`uv run pytest`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`,
`claude plugin validate .`. Evals cost money: run them only when asked.
