# claude-role-skills

Claude Code skills by role. Each skill does one job that keeps coming back, counts with its own
scripts instead of estimating, and ends in one self-contained web page you can read and share.

Two packs so far: one for software engineers and one for AI solutions architects. Packs for data
analysis and for AI engineering (evals, retrieval tuning, traces) will follow.

## Software engineering

| Skill | Use it when | It writes |
|---|---|---|
| [codebase-map](plugins/software-engineering/skills/codebase-map/SKILL.md) | you open a repository you do not know | a map: purpose, entry points, module graph, flows traced hop by hop, boundaries, health, open questions |
| [impact](plugins/software-engineering/skills/impact/SKILL.md) | before you change, rename or remove something | everything the change reaches, including dynamic calls, stored data and outside consumers, and the safe order of steps |
| [bug-hunt](plugins/software-engineering/skills/bug-hunt/SKILL.md) | an error, a failing test or a bug report needs its root cause | the cause with evidence, the commit that brought it, a failing regression test, the same weakness elsewhere, fix options |
| [test-gap](plugins/software-engineering/skills/test-gap/SKILL.md) | you need to know which tests to write first | code ranked by risk, change rate and missing coverage; missing cases with their expected results; weak and deleted tests |
| [dependency-audit](plugins/software-engineering/skills/dependency-audit/SKILL.md) | you inherit a project, before a release, or after an alert | vulnerabilities and whether the code reaches them, outdated, unused and abandoned packages, licences, upgrade waves |

## AI solutions architect

| Skill | Use it when | It writes |
|---|---|---|
| [ai-pattern](plugins/ai-architect/skills/ai-pattern/SKILL.md) | a brief arrives, before anything is built | what the solution should be (no LLM, one call, long context, RAG, workflow, agentic RAG, agent, multi-agent), decided by elimination against the brief's facts; the binding constraint, what would change it, acceptance criteria, an ADR draft |
| [ai-stack](plugins/ai-architect/skills/ai-stack/SKILL.md) | the pattern is chosen and the tools must be picked | the model per step, embeddings, store, orchestration, hosting, tracing, evals and guardrails, in two variants at most; monthly cost and latency from a dated price table; lock-in; checks before the offer |
| [ai-architecture](plugins/ai-architect/skills/ai-architecture/SKILL.md) | a solution must be shown to a client or a team | one interactive page: components in zones with their details, request flows played step by step, a switch between variants, and where untrusted text enters and what it can reach |
| [ai-review](plugins/ai-architect/skills/ai-review/SKILL.md) | before a release, a take-over or a hand-over | the design read from the code against eleven common failures, with file:line findings and fixes, and the problem spots on the architecture |

The architecture page is the one to try first: click a component, press Play on a flow, switch
between the routed workflow and agentic RAG, turn on the trust view.
[`ai-architecture/references/example.json`](plugins/ai-architect/skills/ai-architecture/references/example.json)
renders into it.

Each `SKILL.md` says its job, its input, its steps, its output, what it reads, what it writes and
what it never does. Read a skill before you use it. None of them changes your code unless you say
yes; bug-hunt and test-gap write tests and fixes only after that yes.

## Install

You need Claude Code, `git` and Python 3.11 or newer. The scripts use the standard library only.

As a plugin, inside Claude Code:

```text
/plugin marketplace add ~/Projekti/Personal/claude-role-skills
/plugin install software-engineering@claude-role-skills
/plugin install ai-architect@claude-role-skills
```

Then `/software-engineering:codebase-map`, `/software-engineering:impact order_total`,
`/ai-architect:ai-pattern brief.md`, and so on.
Claude also picks a skill by itself when your request matches its description.

Or copy the skills into one project:

```bash
mkdir -p your-project/.claude/skills
cp -r plugins/software-engineering/skills/* plugins/ai-architect/skills/* your-project/.claude/skills/
```

The pages go outside your repository, to `$CLAUDE_PAGES_DIR/<repo>/`, or `~/claude-pages/<repo>/`
when the variable is not set. Each page sits next to its JSON, so a later run can compare.

If you also have Anthropic's `engineering` plugin, its `debug`, `testing-strategy`,
`architecture` and `system-design` skills cover some of the same ground; the ai-architect skills
are only for AI and LLM solutions. Call these by name when you want them.

## How it is built

The format of the skills follows Baraa's
[claude-code-data-engineering-skills](https://github.com/DataWithBaraa/claude-code-data-engineering-skills):
one repeated job per skill, a fixed set of sections, and a result you can open in a browser. Three
things are different:

- **Claude writes the content, a script draws the page.** Claude fills a JSON file and
  `render_page.py` turns it into the HTML, so a skill reads a short format description and a
  small example, not a 250 KB reference page. Every value is escaped and nothing is fetched from
  the network: the fonts are inlined, so a page is one file you can send to anyone. Graphs are
  clickable: a node shows what leads to it and what it reaches, and `page.html#node=importer`
  opens the page traced. Long tables get a filter box, code blocks a copy button. The
  `architecture` block adds a panel per component, flows that play step by step, variants and a
  trust view, with links such as `#flow=order&step=3`; the `decision` block shows options against
  factors with the reason each one fell.
- **Scripts do the counting.** Inventory, import graph, references, stack-trace mapping, coverage
  ranking, dependency lookups, corpus size, the hard rules of the AI pattern ladder, cost at volume
  and the AI inventory of a repository are scripts with fixed output, so two runs give the same
  numbers.
- **The skills are tested.** `fixtures/acme-orders` is a made-up order service with a git history,
  a real bug, untested modules, old pins and a production log. `fixtures/acme-assist` is a made-up
  AI support prototype with two client briefs, a corpus in English and Serbian (Latin and
  Cyrillic, with PDFs and a duplicate) and eight planted design flaws. The scripts are tested
  against them, the example pages come from running the skills on them, and each pack's `evals/`
  checks the skills' behaviour.

```text
.claude-plugin/marketplace.json     the marketplace, one entry per pack
plugins/software-engineering/       a pack: plugin.json, skills/, evals/
plugins/ai-architect/               a pack: plugin.json, skills/, evals/
shared/                             render_page.py, page-format.md, fonts and ai_inventory.py, copied into the skills
tools/sync_shared.py                writes those copies, or checks them with --check
fixtures/                           the acme-orders and acme-assist fixtures and their builder
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
claude plugin eval plugins/ai-architect --scaffold --allow-tools Bash Write --runs 1
```

The evals start real Claude sessions and cost money; `--max-cost-usd` caps a run.

## License

MIT, see [LICENSE](LICENSE). The page design follows Data With Baraa's skills (MIT) and the fonts
are under the SIL Open Font License, see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Everything
in the fixture and the example pages is fictional.
