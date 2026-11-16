# 0002. Shared files are copied into each skill

Date: 2026-11-09, with the ai-architect pack, when a second pack first needed the renderer.

## Status

Accepted

## Context

An installed plugin has nothing outside its own folder, and a skill copied into a project has nothing outside its own
folder either. A skill that imported `render_page.py` or `guard.py` from elsewhere in the repository would break once
installed. Source: the docstring of `tools/sync_shared.py` and "Layout" in [CLAUDE.md](../../CLAUDE.md).

## Decision

`shared/` is the single source of the renderer, the page format, the fonts, the guard, the scripts several skills use
and the cloud provider files. `tools/sync_shared.py` copies each file into every skill whose `SKILL.md` names it, at
fixed places, and the copies are committed. Nobody edits a copy.

## Consequences

- Every skill works on its own, installed or copied.
- `sync_shared.py --check` runs in CI and in `tests/test_skill_files.py`, so a shared file edited without a sync fails
  the build.
- A change to a shared file changes every copy in the same commit: a change to `render_page.py` touches 51 files.
- mypy must skip the copies (the `exclude` in `pyproject.toml`), or it sees the same module twice.
