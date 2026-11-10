# claude-role-skills

Claude Code skills by role. Each skill does one job that keeps coming back, counts with its own
scripts instead of estimating, and ends in one self-contained web page you can read and share.

Eight packs so far: software engineers, AI solutions architects, data architects, software architects, cloud architects, solutions architects, who join the specialists' work, data analysts and data scientists. The plan for
the next ones is in [docs/plans/architect-packs.md](docs/plans/architect-packs.md).

## Software engineering

| Skill | Use it when | It writes |
|---|---|---|
| [codebase-map](plugins/software-engineering/skills/codebase-map/SKILL.md) | you open a repository you do not know | a map: purpose, entry points, module graph, flows traced hop by hop, boundaries, health, open questions |
| [impact](plugins/software-engineering/skills/impact/SKILL.md) | before you change, rename or remove something | everything the change reaches, including dynamic calls, stored data and outside consumers, and the safe order of steps |
| [bug-hunt](plugins/software-engineering/skills/bug-hunt/SKILL.md) | an error, a failing test or a bug report needs its root cause | the cause with evidence, the commit that brought it, a failing regression test, the same weakness elsewhere, fix options |
| [test-gap](plugins/software-engineering/skills/test-gap/SKILL.md) | you need to know which tests to write first | code ranked by risk, change rate and missing coverage; missing cases with their expected results; weak and deleted tests |
| [dependency-audit](plugins/software-engineering/skills/dependency-audit/SKILL.md) | you inherit a project, before a release, or after an alert | vulnerabilities and whether the code reaches them, outdated, unused and abandoned packages, licences, upgrade waves |
| [code-audit](plugins/software-engineering/skills/code-audit/SKILL.md) | the code as it stands must be checked for bugs, before you build on it or release it | bugs read in the code, each with the scenario that triggers it and the test that would catch it; promises in the docs that no code keeps; what happens when a step fails halfway; cycles, layer breaks and hidden coupling |

`code-audit` reviews code that exists, not a change: a diff or a pull request goes to a change review such as the
built-in `/code-review`. A design that is not built yet goes to `arch-review`.

## AI solutions architect

| Skill | Use it when | It writes |
|---|---|---|
| [ai-pattern](plugins/ai-architect/skills/ai-pattern/SKILL.md) | a brief arrives, before anything is built | what the solution should be (no LLM, one call, long context, RAG, workflow, agentic RAG, agent, multi-agent), decided by elimination against the brief's facts; the binding constraint, what would change it, acceptance criteria, an ADR draft |
| [ai-stack](plugins/ai-architect/skills/ai-stack/SKILL.md) | the pattern is chosen and the tools must be picked | the model per step, embeddings, store, orchestration, hosting, tracing, evals and guardrails, in two variants at most; monthly cost and latency from a dated price table; lock-in; checks before the offer |
| [ai-architecture](plugins/ai-architect/skills/ai-architecture/SKILL.md) | a solution must be shown to a client or a team | one interactive page: components in zones with their details, request flows played step by step, a switch between variants, and where untrusted text enters and what it can reach |
| [ai-review](plugins/ai-architect/skills/ai-review/SKILL.md) | before a release, a take-over or a hand-over | the design read from the code against eleven common failures, with file:line findings and fixes, and the problem spots on the architecture |

## Data architect

| Skill | Use it when | It writes |
|---|---|---|
| [data-platform](plugins/data-architect/skills/data-platform/SKILL.md) | a brief or a list of sources arrives, before anything is built | what the platform should be (reports on the source, one database, a warehouse, a lakehouse, a streaming path, a mesh), decided by elimination, sized, with the layers, where personal data goes and an ADR draft |
| [data-model](plugins/data-architect/skills/data-model/SKILL.md) | a subject area must be modelled | the approach, the grain of every fact checked against the data, keys, history, personal data, a clickable model and DDL drafts |
| [data-map](plugins/data-architect/skills/data-map/SKILL.md) | you inherit a data platform or must explain one | layers, table lineage read from the code, owners, tables nobody reads, dynamic SQL, where personal data travels |
| [data-review](plugins/data-architect/skills/data-review/SKILL.md) | before a release, a take-over or a hand-over | the models and loads against the common failures, with file:line findings, what the data shows and the order of the fixes |

Prices are not part of this pack: it sizes a platform in GB and rows, and `cloud-architect` will
summarise the prices for each cloud.

## Data analyst

| Skill | Use it when | It writes |
|---|---|---|
| [metric-spec](plugins/data-analyst/skills/metric-spec/SKILL.md) | two teams or reports show different numbers for what should be one metric | where it is defined today, how far those definitions differ on sample data, step by step, and one definition: grain, filters, formula, window, currency, owner, what it leaves out |
| [number-moved](plugins/data-analyst/skills/number-moved/SKILL.md) | a reported number changed between two periods and someone asks why | checks that the data did not fake the change, then volume, mix and rate effects that add up exactly, ranked, with what is left unexplained and what the data cannot show |
| [number-reconcile](plugins/data-analyst/skills/number-reconcile/SKILL.md) | two numbers that should agree do not | the whole gap accounted for row by row (only in one, filters, duplicates, time zones, timing, rounding), adding up exactly, or the exact amount left unexplained |
| [report-review](plugins/data-analyst/skills/report-review/SKILL.md) | before a report with its SQL or notebook goes out | the counting checked against its data: double counting, wrong denominators, dropped rows, partial periods, averages of averages, small samples, a Simpson's reversal, misleading charts, each with file:line and the corrected number |

These skills do the repeated jobs that need the counting done by a script and a page someone can trust; general
questions, exploring a table and dashboards are left to the Anthropic `data` plugin. Sums are exact and read-only: a
personal value never reaches the output.

## Data scientist

| Skill | Use it when | It writes |
|---|---|---|
| [ds-frame](plugins/data-scientist/skills/ds-frame/SKILL.md) | someone asks for a predictive model, before anything is trained | the decision it changes, the exact target, whether a label comes in time and what each error costs; a ladder from a lookup rule to deep learning with options ruled out against the brief, the baseline that must be beaten and acceptance criteria |
| [ds-explore](plugins/data-scientist/skills/ds-explore/SKILL.md) | one table and a yes/no target, before anyone splits it or trains anything | the target rate over time, labels that cannot be known yet, codes for unknown values, how strongly each feature relates to the target with an interval and a test corrected across features, shapes a linear term would miss, segments, redundant features, columns to check for leakage |
| [ds-dataset](plugins/data-scientist/skills/ds-dataset/SKILL.md) | before trusting a predictive model built on a training set | target leakage, timestamps from the future, the same entity on both sides of a split, duplicates across splits, class balance, missingness that differs by class, drift (PSI), personal columns, each with what to change |
| [ds-evaluate](plugins/data-scientist/skills/ds-evaluate/SKILL.md) | comparing trained models from a file of predictions | ROC-AUC, PR-AUC, log loss, Brier, MAE, RMSE, bias with seeded bootstrap intervals, a paired comparison against the baseline that calls noise noise, a calibration table, a threshold from the cost of each error and the worst slices |
| [ds-experiment](plugins/data-scientist/skills/ds-experiment/SKILL.md) | an A/B test must be sized, or has finished | sample size and minimum detectable effect, or a read-out: sample ratio mismatch first, intervals, correction for several metrics, guardrails with margins, a warning about peeking and a call of ship, do not ship or inconclusive |

The statistics are implemented in the standard library and checked in the tests against values known independently.
LLM evaluation is not part of this pack; `ds-frame` sends an LLM problem to `ai-pattern`, and the general statistics
of the Anthropic `data` plugin stay where they are.

## Software architect

| Skill | Use it when | It writes |
|---|---|---|
| [arch-style](plugins/software-architect/skills/arch-style/SKILL.md) | a brief arrives or someone proposes microservices | what shape the system should have (one deployable, modular monolith, serverless, a few services, an event backbone, microservices), decided by elimination, with fitness rules and an ADR draft |
| [arch-c4](plugins/software-architect/skills/arch-c4/SKILL.md) | a system must be drawn and explained | context, containers and components as boxes inside boxes, with zoom between levels and requests traced hop by hop |
| [arch-review](plugins/software-architect/skills/arch-review/SKILL.md) | a design document, proposal or set of ADRs must be reviewed before it is approved or built | waiting chains checked against their latency goals, data written by two parts, promises with no mechanism, goals without numbers, dependencies with no failure plan, documents that contradict each other, open decisions; each shown from the documents, with what to decide first |

`arch-review` reads documents, not code. The structure of code that exists (cycles, layer breaks, hidden coupling) is
part of `code-audit`.
| [arch-evolve](plugins/software-architect/skills/arch-evolve/SKILL.md) | a system must move to a new structure | steps that each leave the system working, with how each is verified and undone, and where to stop |

## Cloud architect

| Skill | Use it when | It writes |
|---|---|---|
| [cloud-map](plugins/cloud-architect/skills/cloud-map/SKILL.md) | you inherit cloud infrastructure or must explain it, from code with no login or a saved export | the estate as boxes inside boxes, request flows, what the internet can reach and what stops it, what is in code but not deployed and deployed but not in code |
| [cloud-design](plugins/cloud-architect/skills/cloud-design/SKILL.md) | a brief arrives, before a platform is picked | compute, data, network, region and availability, decided by elimination; up to two variants or two clouds costed from the provider's price list, each price with its date and source; an ADR draft |
| [cloud-review](plugins/cloud-architect/skills/cloud-review/SKILL.md) | before a release, an audit or a take-over of infrastructure | problems tied to file:line or a resource, checked against the provider's Well-Architected pillars, marked on the drawing, with what to fix first |

One brief compared across clouds with real prices, drawn and reviewed the same way, from code in a repository with no cloud login. Azure and AWS are here; a provider is one pair of files, so Google Cloud can follow later. These skills do not deploy and do not write production infrastructure code. They read Terraform, Bicep, ARM and CloudFormation (JSON and YAML), make no cloud call of their own apart from the public price lists, which are opt-in with a timeout, and never bundle a vendor's icons: boxes carry their kind in text.

## Solutions architect

| Skill | Use it when | It writes |
|---|---|---|
| [solution-brief](plugins/solutions-architect/skills/solution-brief/SKILL.md) | a client brief arrives that may cross several areas, before any specialist runs | the brief framed once, which specialists are needed and in which order, why any is not needed, the exact calls to run next with the shared facts each must use |
| [solution-blueprint](plugins/solutions-architect/skills/solution-blueprint/SKILL.md) | the specialist pages exist and must become one solution | the whole solution drawn as one picture, one list of decisions with where each came from, one cost summary per cloud or variant, every conflict between the pages with the side recommended, what nobody covered, what to do first |

Without this pack, specialist pages contradict each other unnoticed: a model in one region and the data in another, each page with its own cost total and nothing adding them up. Joining the pages and naming the conflicts is all it does: it never redoes a specialist's work and never recomputes a specialist's number. `join_facts.py` lists where the pages disagree, as places to read, and Claude reads them and recommends a side. Costs are grouped per currency and never added across currencies. Installing the pack installs the four specialist packs, because they come from the same marketplace.

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
/plugin marketplace add ManSe404/claude-role-skills
/plugin install software-engineering@claude-role-skills
/plugin install ai-architect@claude-role-skills
/plugin install data-architect@claude-role-skills
/plugin install data-analyst@claude-role-skills
/plugin install data-scientist@claude-role-skills
/plugin install software-architect@claude-role-skills
/plugin install cloud-architect@claude-role-skills
/plugin install solutions-architect@claude-role-skills
```

`solutions-architect` also installs `ai-architect`, `data-architect`, `software-architect` and `cloud-architect`, so on its own it brings the four specialists. It only loads with them present: with `--plugin-dir` you must pass all five folders, or Claude Code reports the dependency as unsatisfied and drops the pack.

Then `/software-engineering:codebase-map`, `/software-engineering:impact order_total`,
`/ai-architect:ai-pattern brief.md`, and so on.
Claude also picks a skill by itself when your request matches its description.

Or copy the skills into one project:

```bash
git clone https://github.com/ManSe404/claude-role-skills
cd claude-role-skills
mkdir -p /path/to/your-project/.claude/skills
cp -r plugins/software-engineering/skills/* plugins/ai-architect/skills/* plugins/data-architect/skills/* plugins/software-architect/skills/* plugins/cloud-architect/skills/* plugins/solutions-architect/skills/* plugins/data-analyst/skills/* plugins/data-scientist/skills/* /path/to/your-project/.claude/skills/
```

The pages go outside your repository, to `$CLAUDE_PAGES_DIR/<repo>/`, or `~/claude-pages/<repo>/`
when the variable is not set. Each page sits next to its JSON, so a later run can compare.

If you also have Anthropic's `engineering` plugin, its `debug`, `testing-strategy`,
`architecture` and `system-design` skills cover some of the same ground; the ai-architect skills
are only for AI and LLM solutions. Call these by name when you want them.

## Hooks

Every skill carries a hook in its frontmatter, so the parts of its "Never" list that a program can check are enforced
by Claude Code rather than only asked for. Claude Code registers the hook when the skill is invoked. It runs
`scripts/guard.py`, a copy of [shared/guard.py](shared/guard.py).

During the turn in which the skill was invoked:

- **Changes ask first.** A Write or Edit outside the pages folder, a temp folder or the skill's own page file, and a
  shell command that changes files, git or the installed packages, bring up a permission prompt.
- **Going online asks first.** This covers WebFetch, WebSearch, `curl`, `wget`, `git fetch`, `pull` and `clone`,
  `az`, `aws`, `gcloud`, `terraform init` and `plan`, dependency audits, and any `--online` flag.
- **Personal data (the 12 skills that read data files).**
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

## How it is built

Each skill does one repeated job, in a fixed set of sections, and ends in a page you open in a browser.

- **Claude writes the content, a script draws the page.** Claude fills a JSON file and
  `render_page.py` turns it into the HTML, so a skill reads a short format description and a
  small example. Every value is escaped and nothing is fetched from
  the network: the fonts are inlined, so a page is one file you can send to anyone. Graphs are
  clickable: a node shows what leads to it and what it reaches, and `page.html#node=importer`
  opens the page traced. Long tables get a filter box, code blocks a copy button. The
  `architecture` block adds a panel per component, flows that play step by step, variants and a
  trust view, with links such as `#flow=order&step=3`; the `decision` block shows options against
  factors with the reason each one fell; the `model` block draws tables with their keys and opens
  each one's columns, a `reach` view shows how far personal data travels, and the `nested` block
  draws boxes inside boxes with zoom between levels.
- **Scripts do the counting.** Inventory, import graph, references, stack-trace mapping, coverage
  ranking, dependency lookups, corpus size, the hard rules of the AI pattern and data platform
  ladders, cost at volume, the AI inventory of a repository, data profiles, table lineage from
  SQL, dbt and notebooks, and module graphs with their history are scripts with fixed output, so two runs give the same numbers.
- **The skills are tested.** `fixtures/acme-orders` is a made-up order service with a git history,
  a real bug, untested modules, old pins and a production log. `fixtures/acme-assist` is a made-up
  AI support prototype with two client briefs, a corpus in English and Serbian (Latin and
  Cyrillic, with PDFs and a duplicate) and eight planted design flaws. `fixtures/acme-data` is a
  made-up data platform with two briefs, sample data and eight planted problems, and
  `fixtures/acme-logistics` a made-up .NET, TypeScript and Python system with eight structural ones,
  and `fixtures/acme-cloud` a made-up Azure estate in Terraform and Bicep with eight planted problems and drift, and `fixtures/acme-cloud-aws` a made-up AWS estate in Terraform and CloudFormation with the same, `fixtures/acme-solution` a client brief with the specialist pages written about it and ten planted conflicts between them, and `fixtures/acme-sales` a made-up sales analytics project with planted metric problems, a late day and two systems that disagree. The scripts are tested
  against them, the example pages come from running the skills on them, and each pack's `evals/`
  checks the skills' behaviour.

```text
.claude-plugin/marketplace.json     the marketplace, one entry per pack
plugins/software-engineering/       a pack: plugin.json, skills/, evals/
plugins/ai-architect/               a pack: plugin.json, skills/, evals/
plugins/data-architect/             a pack: plugin.json, skills/, evals/
plugins/data-analyst/               a pack: plugin.json, skills/, evals/
plugins/data-scientist/             a pack: plugin.json, skills/, evals/
plugins/software-architect/         a pack: plugin.json, skills/, evals/
plugins/cloud-architect/            a pack: plugin.json, skills/, evals/
plugins/solutions-architect/        a pack: plugin.json, skills/, evals/, on top of the four above
shared/                             render_page.py, page-format.md, fonts and the shared scripts, copied into the skills
tools/sync_shared.py                writes those copies, or checks them with --check
fixtures/                           the acme-* fixtures and their builder
roles/                              CLAUDE.md starters, one per role
tests/                              pytest for the scripts, the renderer, the fixture and the skill files
```

## The page design

Dark, with neutral grays, one blue accent and flat panels, IBM Plex Sans for text and IBM Plex Mono for labels. In
graphs, blue marks what leads to a change and orange what it reaches. The CSS lives in `shared/render_page.py`, so
every skill's page changes with it. The fonts are inlined, include Latin 2 for Serbian, and are under the SIL Open
Font License ([THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)).

## Development

```bash
uv sync
uv run pytest
uv run ruff format --check . && uv run ruff check . && uv run mypy
python3 tools/sync_shared.py                                  # after editing shared/
python3 fixtures/build_fixture.py acme-orders /tmp/acme       # the fixture, with its history
claude plugin validate .
claude plugin eval plugins/software-engineering --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins/ai-architect --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins/data-architect --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins/data-analyst --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins/data-scientist --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins/software-architect --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins/cloud-architect --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins --eval-dir solutions-architect/evals --scaffold --allow-tools Bash Write --runs 1 --ablation none
```

The evals start real Claude sessions and cost money, about 80 cents a case; `--max-cost-usd` caps a run. Without
`--ablation none` each case also runs without the plugin, for comparison, which about doubles the cost. The
`solutions-architect` command differs because its cases must load the four specialist packs, and the eval tool only
loads plugins from inside the folder it is pointed at.

Those evals load one pack at a time, so they cannot show whether Claude picks the right skill among all of them.
`uv run python tools/selection_check.py` does: it loads every pack and makes one model call per prompt, about 15 cents
each (`--all-tools` to offer Claude's ordinary tools as well as Skill, `--budget` to cap it).

## License

MIT, see [LICENSE](LICENSE). Notices for the page design and the fonts are in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Everything
in the fixtures and the example pages is fictional, except the public Azure and AWS list prices saved in
`fixtures/acme-cloud` and `fixtures/acme-cloud-aws`.
