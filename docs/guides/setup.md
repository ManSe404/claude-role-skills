# Setup: install and use the skills

You need Claude Code, `git` and Python 3.11 or newer. The scripts use the standard library only, so nothing else is
installed. To work on the repository itself, see [development.md](development.md).

## As plugins

Inside Claude Code:

```text
/plugin marketplace add ManSe404/claude-role-skills
/plugin install software-engineering@claude-role-skills
/plugin install ai-architect@claude-role-skills
/plugin install data-architect@claude-role-skills
/plugin install data-engineer@claude-role-skills
/plugin install data-analyst@claude-role-skills
/plugin install data-scientist@claude-role-skills
/plugin install software-architect@claude-role-skills
/plugin install cloud-architect@claude-role-skills
/plugin install solutions-architect@claude-role-skills
/plugin install workflows@claude-role-skills
```

`solutions-architect` also installs `ai-architect`, `data-architect`, `software-architect` and `cloud-architect`, so on
its own it brings the four specialists. It only loads with them present: with `--plugin-dir` you must pass all five
folders, or Claude Code reports the dependency as unsatisfied and drops the pack. `workflows` installs every other
pack in the same way.

Then `/software-engineering:codebase-map`, `/software-engineering:impact order_total`,
`/ai-architect:ai-pattern brief.md`, and so on. Claude also picks a skill by itself when your request matches its
description. Each `SKILL.md` says its job, its input, its steps, its output, what it reads, what it writes and what it
never does: read a skill before you use it.

## Copied into one project

```bash
git clone https://github.com/ManSe404/claude-role-skills
cd claude-role-skills
mkdir -p /path/to/your-project/.claude/skills
cp -r plugins/software-engineering/skills/* plugins/ai-architect/skills/* plugins/data-architect/skills/* plugins/data-engineer/skills/* plugins/software-architect/skills/* plugins/cloud-architect/skills/* plugins/solutions-architect/skills/* plugins/data-analyst/skills/* plugins/data-scientist/skills/* /path/to/your-project/.claude/skills/
```

A skill copied this way still finds its guard (the hook looks under `$CLAUDE_PROJECT_DIR/.claude`), unless your
organization locks hooks to plugins; see [architecture/crosscutting.md](../architecture/crosscutting.md).

## Where the pages go

Outside your repository, to `$CLAUDE_PAGES_DIR/<repo>/`, or `~/claude-pages/<repo>/` when the variable is not set.
Each page sits next to its JSON, so a later run can compare. Every run refreshes `index.html` in the pages folder,
which lists every page under it.

| Setting | Default | What it does |
|---|---|---|
| `CLAUDE_PAGES_DIR` | `~/claude-pages` | the folder the skills write their pages, notes and JSON to; the guard lets writes there through |

## A CLAUDE.md for your project

`roles/` has one CLAUDE.md starter per role. Copy the part below the line into your project's CLAUDE.md and adapt it;
the project's own facts (stack, commands, standards) go above it.

## Open

- The copy command above leaves out `plugins/workflows/skills/*`; whether the workflow skills are meant to be copied
  into a project as well is not stated anywhere.
