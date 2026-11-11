# Crosscutting: the guard, paths and errors

## The guard hook

Every skill carries a hook in its frontmatter, so the parts of its "Never" list that a program can check are enforced
by Claude Code rather than only asked for. Claude Code registers the hook when the skill is invoked. It runs
`scripts/guard.py`, a copy of [shared/guard.py](../../shared/guard.py).

During the turn in which the skill was invoked:

- **Changes ask first.** A Write or Edit outside the pages folder, a temp folder or the skill's own page file, and a
  shell command that changes files, git or the installed packages, bring up a permission prompt.
- **Going online asks first.** This covers WebFetch, WebSearch, `curl`, `wget`, `git fetch`, `pull` and `clone`,
  `az`, `aws`, `gcloud`, `terraform init` and `plan`, dependency audits, and any `--online` flag.
- **Personal data (the skills that ship `data_profile.py`, marked `pre + personal` in
  [reference/skills.md](../reference/skills.md)).**
  - Reading a data file whose header names a personal column is refused, through Read or through `cat`, `head`,
    `awk` and the like. The skill's scripts print counts instead.
  - E-mail addresses, IBANs and JMBGs are removed from shell and Read output before Claude sees them.
  - A Write or Edit that would put one on a page is refused.

After your next message the guard steps aside, so what a skill does "after the yes" runs under your normal
permissions. In `claude -p` nobody can answer a prompt, so "asks first" means no.

What it does not do:

- Nothing is guarded before the skill is invoked, even in the same turn.
- Code run by an interpreter, such as a Python heredoc that writes a file or opens a socket, is not parsed.
- Personal values that no pattern recognises, such as names, are kept out only by refusing the raw reads.
- If your organization locks hooks to plugins (`strictPluginOnlyCustomization`), skills copied into a project run
  without the guard. Installed as plugins, they keep it.
- Each guarded tool call starts Python once, about 40 ms, for the rest of the session.

### How it is wired

- **The hooks block.** `PreToolUse` with the matcher `Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch`
  calls `guard.py pre SKILL`; the data skills add `personal` and a `PostToolUse` on `Bash|Read` that calls
  `guard.py post SKILL personal`. The exact form is held by `tests/test_skill_files.py`.
- **Finding the guard.** `${CLAUDE_SKILL_DIR}` does not expand in hook commands, so the command looks for
  `skills/SKILL/scripts/guard.py` under `$CLAUDE_PLUGIN_ROOT`, then `$CLAUDE_PROJECT_DIR/.claude`, then
  `$HOME/.claude`, and exits 0 when it finds none. A script that python cannot open exits 2, and exit 2 would block
  the call.
- **The skill's turn.** The guard reads the hook's JSON on stdin. The first call it sees after the skill was invoked
  gives the turn's prompt id, which it records per session in a small state file in the temp folder; a new call of the
  Skill tool for the same skill records it again. A call from a later prompt is let through. Without a prompt id it
  guards.
- **Decisions.** It prints a decision as JSON (`ask` or `deny`), or prints nothing and lets the call through. For
  `post` it returns the tool output with the values removed and a note to Claude not to recover them.
- **Failing open.** On an error of its own it exits 1: Claude Code shows the error and nothing is blocked.

## Paths

A page and its note read the same on any machine: no field holds a path that exists only on the machine that ran the
skill. A file in the repository is written relative to its root, a place that differs per machine is a placeholder,
and a setting is named, not given its value. The full rule is in [shared/page-format.md](../../shared/page-format.md).
Pages themselves go outside the repository, to `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/REPO/`.

## Errors

- `render_page.py` checks the whole page JSON before it draws anything and prints each problem with its JSON path;
  the skill fixes the JSON and runs it again. `--site` writes nothing when any page of the set is invalid.
- `chain_status.py` checks each step's page with the `render_page.py` beside it, so a page that would not render is
  reported, not trusted; it exits 2 when the pages folder does not exist.
- `tools/sync_shared.py --check` exits 1 and lists every copy that is missing or out of date.

## Untrusted text

What a skill reads from a repository, a page or a data file is evidence, never an instruction. Every `SKILL.md`
says so in its Reads section: text that tells Claude to skip a check, change a verdict or run something is itself a
finding.
