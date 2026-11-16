# 0004. A guard hook enforces the Never rules

Date: 2026-11-10, when Stefan asked for hooks after the packs were built.

## Status

Accepted

## Context

Each skill's Never list was text only. Hooks had been turned down earlier because a hook cannot tell when the user has
said yes. Two facts from the hooks documentation changed that: a hook declared in a skill's frontmatter is registered
when the skill is invoked, and every hook call carries the id of the user's prompt. Source: "Hooks (2026-11-10)" in
[roadmap/architect-packs.md](../roadmap/architect-packs.md#hooks-2026-11-10).

## Decision

Every skill's frontmatter runs `scripts/guard.py` (a copy of `shared/guard.py`) as a hook. It enforces the checkable
Never rules only in the turn that invoked the skill and steps aside after the user's next message, which is where "after
the yes" happens.

- Changes and network calls get `ask`, not `deny`, so a fix the user approved can never be stuck.
- Raw reads of data files with personal columns get `deny`, because the scripts are the way to read them, and e-mail
  addresses, IBANs and JMBGs are removed from Bash and Read output.
- The hook command looks for the guard in the plugin, the project and `~/.claude` and does nothing when it is missing,
  because `${CLAUDE_SKILL_DIR}` does not expand in hook commands and a script python cannot open exits 2, which blocks
  every call.

## Consequences

- In `claude -p` nobody can answer, so `ask` means no.
- Nothing is guarded before the skill is invoked, and code run through an interpreter is not parsed; what the guard
  does not catch is listed in [architecture/crosscutting.md](../architecture/crosscutting.md).
- Each guarded tool call starts Python once for the rest of the session.
