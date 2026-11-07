# claude-role-skills

Claude Code skills by role. Each skill does one job that keeps coming back, counts with its own
scripts instead of estimating, and ends in one self-contained web page you can read and share.

The first pack is for software engineers. Packs for data analysis and for AI engineering and data
science will follow.

## Software engineering

| Skill | Use it when | It writes |
|---|---|---|
| [codebase-map](plugins/software-engineering/skills/codebase-map/SKILL.md) | you open a repository you do not know | a map: purpose, entry points, module graph, flows traced hop by hop, boundaries, health, open questions |
| [impact](plugins/software-engineering/skills/impact/SKILL.md) | before you change, rename or remove something | everything the change reaches, including dynamic calls, stored data and outside consumers, and the safe order of steps |
| [bug-hunt](plugins/software-engineering/skills/bug-hunt/SKILL.md) | an error, a failing test or a bug report needs its root cause | the cause with evidence, the commit that brought it, a failing regression test, the same weakness elsewhere, fix options |
| [test-gap](plugins/software-engineering/skills/test-gap/SKILL.md) | you need to know which tests to write first | code ranked by risk, change rate and missing coverage; missing cases with their expected results; weak and deleted tests |
| [dependency-audit](plugins/software-engineering/skills/dependency-audit/SKILL.md) | you inherit a project, before a release, or after an alert | vulnerabilities and whether the code reaches them, outdated, unused and abandoned packages, licences, upgrade waves |

Each `SKILL.md` says its job, its input, its steps, its output, what it reads, what it writes and
what it never does. Read a skill before you use it. None of them changes your code unless you say
yes; bug-hunt and test-gap write tests and fixes only after that yes.

## Install

You need Claude Code, `git` and Python 3.11 or newer. The scripts use the standard library only.

As a plugin, inside Claude Code:

```text
/plugin marketplace add ~/Projekti/Personal/claude-role-skills
/plugin install software-engineering@claude-role-skills
```

Then `/software-engineering:codebase-map`, `/software-engineering:impact order_total`, and so on.
Claude also picks a skill by itself when your request matches its description.

Or copy the skills into one project:

```bash
mkdir -p your-project/.claude/skills
cp -r plugins/software-engineering/skills/* your-project/.claude/skills/
```

The pages go outside your repository, to `$CLAUDE_PAGES_DIR/<repo>/`, or `~/claude-pages/<repo>/`
when the variable is not set. Each page sits next to its JSON, so a later run can compare.

If you also have Anthropic's `engineering` plugin, its `debug` and `testing-strategy` skills cover
some of the same ground. Call these by name when you want them.

## How it is built

The format of the skills follows Baraa's
[claude-code-data-engineering-skills](https://github.com/DataWithBaraa/claude-code-data-engineering-skills):
one repeated job per skill, a fixed set of sections, and a result you can open in a browser. Three
things are different:

- **Claude writes the content, a script draws the page.** Claude fills a JSON file and
  `render_page.py` turns it into the HTML, so a skill reads a 3 KB format description and a 17–30 KB
  example, not a 250 KB reference page. Every value is escaped and nothing is fetched from the
  network: the fonts are inlined, so a page is one file you can send to anyone. Graphs are
  clickable: a node shows what leads to it and what it reaches, and `page.html#node=importer`
  opens the page traced. Long tables get a filter box, code blocks a copy button.
- **Scripts do the counting.** Inventory, import graph, references, stack-trace mapping, coverage
  ranking and dependency lookups are scripts with fixed output, so two runs give the same numbers.
- **The skills are tested.** `fixtures/acme-orders` is a made-up order service with a git history,
  a real bug, untested modules, old pins and a production log. The scripts are tested against it,
  the example pages come from running the skills on it, and `evals/` checks the skills' behaviour.

```text
.claude-plugin/marketplace.json     the marketplace, one entry per pack
plugins/software-engineering/       the pack: plugin.json, skills/, evals/
shared/                             render_page.py and page-format.md, copied into each skill
tools/sync_shared.py                writes those copies, or checks them with --check
fixtures/                           the acme-orders fixture and its builder
roles/                              CLAUDE.md starters, one per role
tests/                              pytest for the scripts, the renderer, the fixture and the skill files
```

## The page design

The pages use the dark violet design of Baraa's skills: a violet ground with a radial glow and a
faint grid, panels with a purple edge, Bricolage Grotesque for text and JetBrains Mono for labels,
purple for what leads to a change and orange for what it reaches. All of it lives in one place, the
CSS in `shared/render_page.py`, so every skill's page changes with it. The fonts are under the SIL
Open Font License ([shared/fonts/OFL.txt](shared/fonts/OFL.txt)) and include Latin Extended, so
pages can be written in Serbian. See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

## Development

```bash
uv sync
uv run pytest
uv run ruff format --check . && uv run ruff check . && uv run mypy
python3 tools/sync_shared.py                                  # after editing shared/
python3 fixtures/build_fixture.py acme-orders /tmp/acme       # the fixture, with its history
claude plugin validate .
claude plugin eval plugins/software-engineering --scaffold --allow-tools Bash Write --runs 1
```

The evals start real Claude sessions and cost money; `--max-cost-usd` caps a run.

## License

MIT, see [LICENSE](LICENSE). The page design follows Data With Baraa's skills (MIT) and the fonts
are under the SIL Open Font License, see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Everything
in the fixture and the example pages is fictional.
