# Vision

## The problem or opportunity

People who use Claude Code for work that keeps coming back (mapping a repository they do not know, reviewing code,
deciding what an AI solution or a data platform should be, explaining why a number moved) get answers that rest on
Claude's reading. A skill that only says what a good review, map or decision looks like still leaves the facts to
that reading: numbers are estimated, two runs can give two answers, a claim nobody checked reads like one that was, and
the result is chat text that is hard to pass on or compare with the next run.

How we know, from the repository:

- **The skills that existed were templates.** Anthropic's `engineering` plugin (v1.2.0: `architecture`,
  `code-review`, `documentation`, `incident-response` and six more) is 765 lines of templates and checklists, with no
  scripts and no evals, and relies on connectors to bring the facts in
  ([engineering-pack-v2.md](../roadmap/engineering-pack-v2.md#what-the-comparison-showed)). Community C4, arc42 and ADR
  skills are text or LikeC4 templates ([software-architect.md](../roadmap/software-architect.md)).
  `wjlgatech/data-architecture` has no scripts, so nothing is measured
  ([data-architect.md](../roadmap/data-architect.md)).
- **The tools that measure cover one slice.** The vendor cloud skills (`microsoft/azure-skills`, 88 SKILL.md;
  `awslabs/agent-plugins`, 34) cover one cloud each and deploy; the community multi-cloud skills give text tables with
  no real prices and no drawings ([architect-packs.md](../roadmap/architect-packs.md#3-cloud-architect)). The search
  before the AI pack found nothing public that combines the decision and the page
  ([ai-architect.md](../roadmap/ai-architect.md)); the one before the data pack found nothing that joins the decision,
  a model checked against the data, lineage from the code and a page
  ([data-architect.md](../roadmap/data-architect.md)).
- **The failures each pack is aimed at,** as its plan names them: a number that does not survive being checked
  ([data-analyst.md](../roadmap/data-analyst.md)); a confident model number that is wrong, such as a training set that
  leaks or noise called a win ([data-scientist.md](../roadmap/data-scientist.md)); specialist pages that contradict
  each other unnoticed, such as the model in one region and the data in another, each with its own cost total that
  nothing adds up ([solutions-architect.md](../roadmap/solutions-architect.md)).
- **A real run.** On a real repository `arch-review`, a design review, was asked to review code. The bugs that
  mattered there, a value read from a key that is never written and a re-index that deletes before it writes, were
  code-review findings, and the packs had no skill for one ([code-audit.md](../roadmap/code-audit.md)). With many
  skills installed, which one Claude picks is part of the problem: five skills match "draw the architecture"
  ([architect-packs.md](../roadmap/architect-packs.md#settled-early-because-they-are-expensive-to-change-later)).

Open: the repository records no measurement that plain Claude gives two answers in two runs, or misses what a skill
finds; the evals can make that comparison (see [How we know it works](#how-we-know-it-works)). Open: the repository
records no user reports or interviews, so who besides the owner has this problem, and how often, is not written down.

## How we solve it

Claude Code skills by role, in one marketplace with one plugin (a pack) per role. Each skill does one job that
keeps coming back, counts with its own scripts instead of estimating, and ends in one self-contained web page you can
read and share, or, when the result is text, in a Markdown note with the page beside it. The skills differ from the
templates in method, not in topics:

- **Scripts do the counting.** Inventory, import graph, references, stack-trace mapping, coverage ranking, dependency
  lookups, corpus size, the hard rules of the AI pattern and data platform ladders, cost at volume, the AI inventory
  of a repository, data profiles, table lineage from SQL, dbt and notebooks, and module graphs with their history are
  scripts with fixed output, so two runs give the same numbers. Claude reads before it claims and tags what it did
  not count: `[high]`, `[med]` or `[guess]`.
- **One page as the result.** Claude writes the content as JSON and a script draws the page, so every page of every
  skill has the same layout, every value is escaped and nothing is fetched from the network. The page is one file
  you can send to anyone, and its JSON stays beside it so a later run can compare.
- **The Never rules are enforced.** While a skill works, a hook makes Claude Code ask before a change or a step
  online, and keeps personal data out of what the data skills see and write.
- **The skills are tested.** Made-up projects with planted problems back the scripts' tests, the example pages and
  the evals that check the planted problem is found.
- **The pages join.** A page carries a `facts` section in one shape, so `solution-blueprint` can join the
  specialists' pages and name their conflicts, and a workflow step can read the previous step's page instead of its
  prose. `codebase-map`, `impact`, `bug-hunt`, `test-gap`, `dependency-audit`, `code-audit` and `ai-review` do not
  write `facts` yet.

What the user does differently: instead of asking in a chat and reading prose, they install the pack for their role
and call a skill (or Claude picks it from the request). They get a page whose numbers come from scripts and whose
other claims carry a tag, read it, and send the file on. Nothing in their code changes until they say yes, and
nothing is posted: comments, status updates and e-mails are drafts on the page that they send themselves. For a
process that needs several skills in order, such as a take-over or an incident, they run one workflow that chains
them, resumes where it stopped and ends in one page.

## Why this way

There is no `docs/adr/` in this repository. The choices below and the options that lost are recorded in the plans
in [roadmap/](../roadmap/); turning them into ADRs is open.

| Chosen | What lost, and why | Where it is recorded |
|---|---|---|
| Scripts count, Claude reads and tags | Templates and checklists Claude fills from memory, as in the `engineering` plugin: they leave the facts to Claude's reading. The rule taken from that comparison: take the jobs and the lists, not the method. | [engineering-pack-v2.md](../roadmap/engineering-pack-v2.md#what-the-comparison-showed) |
| Read files and the repository on the user's machine | Connectors (source control, tracker, monitoring, chat) bringing the facts in: deferred to a phase 3 plan, reading first and posting last, and not before phases 1 and 2 are used. | [engineering-pack-v2.md](../roadmap/engineering-pack-v2.md#phase-3-connectors) |
| One cloud pack with a pair of files per provider, starting from infrastructure code with no login | The vendor skills, one cloud each and deploying: they cannot compare one brief across clouds with real prices. | [architect-packs.md](../roadmap/architect-packs.md#3-cloud-architect), [cloud-architect.md](../roadmap/cloud-architect.md) |
| Deciding skills start at the simplest option of a ladder; their rule script only rules options out and never chooses, and Claude weighs what is left | Climbing to a bigger option without a requirement the skill can name. Each architect fixture holds a brief where the right answer is boring, so an eval catches a skill that overbuilds. | [architect-packs.md](../roadmap/architect-packs.md#settled-early-because-they-are-expensive-to-change-later), [ai-architect.md](../roadmap/ai-architect.md) |
| A `facts` section in every architect page's JSON, decided at the first step of the architect series | Joining pages from text written for people: `solutions-architect` could not, and every pack would have been reworked at the end. | [architect-packs.md](../roadmap/architect-packs.md#settled-early-because-they-are-expensive-to-change-later) |
| Descriptions that name their subject, checked by a selection check with every pack loaded | Trusting `claude plugin eval`, which loads one pack at a time and cannot show which skill Claude picks among all of them. | [architect-packs.md](../roadmap/architect-packs.md#settled-early-because-they-are-expensive-to-change-later), [guides/testing.md](../guides/testing.md#selection-check) |
| Separate skills for reviewing code (`code-audit`) and reviewing a design (`arch-review`) | One review skill for both: a real run sent code to `arch-review`, which was not written for it. | [code-audit.md](../roadmap/code-audit.md) |
| Never rules enforced by a hook that asks (`ask`) for changes and network calls, and refuses (`deny`) raw reads of personal data | Never rules as text only. Hooks were first turned down because a hook cannot tell when the user has said yes; a skill's hook registers when the skill is invoked and every hook call carries the prompt's id, so the guard steps aside after the user's next message. `ask` rather than `deny` for changes, so a fix the user approved can never be stuck. | [architect-packs.md](../roadmap/architect-packs.md#hooks-2026-11-10) |
| Shared files copied into every skill that names them, with a check in CI | Importing shared code from outside the skill: an installed plugin has nothing outside its own folder. | [architecture/overview.md](../architecture/overview.md#how-a-shared-file-reaches-a-skill) |
| Workflows as one workflow skill per process | The plan weighed three ways: one skill per process (cheapest, works wherever a skill works, but one context and nothing in parallel), Claude Code `Workflow` scripts, and Mission Control missions. It recommended the second and third; the first was built, the other two are still plans. A fourth runner was ruled out: the pages' `facts`, the naming rule and the folder index already give the hand-over. | [workflows.md](../roadmap/workflows.md#three-ways-to-run-them) |

Open: the reason the first workflow way was built before the two the plan recommended is not recorded. Open: why
one pack per role rather than one pack with every skill, why a page drawn from JSON rather than a report Claude
writes directly, and why scripts use the standard library only are taken as given in the plans; the options weighed
are not recorded.

## For whom

| Role | Pack | What it covers |
|---|---|---|
| Software engineer | [software-engineering](features/software-engineering.md) | the daily work on code, from mapping a repository to the postmortem |
| AI solutions architect | [ai-architect](features/ai-architect.md) | what an AI solution should be, its stack and price, its drawing and its review |
| Data architect | [data-architect](features/data-architect.md) | what a data platform should be, its model, its map and its review |
| Data engineer | [data-engineer](features/data-engineer.md) | running a platform: sources, contracts, failed runs, checks, cost, migration, served tables |
| Software architect | [software-architect](features/software-architect.md) | a system's shape, its C4 drawing, design reviews and safe steps to a target |
| Cloud architect | [cloud-architect](features/cloud-architect.md) | where a system runs: the estate from code, a costed design, a review |
| Solutions architect | [solutions-architect](features/solutions-architect.md) | one solution from the specialists' pages, with every conflict named |
| Data analyst | [data-analyst](features/data-analyst.md) | numbers that must survive being checked |
| Data scientist | [data-scientist](features/data-scientist.md) | models and experiments, where the usual failure is a confident wrong number |
| A team running a process | [workflows](features/workflows.md) | chains of the skills above, from a take-over to a model build |

They work in Claude Code, with `git` and Python 3.11 or newer ([guides/setup.md](../guides/setup.md)). `roles/` holds
a CLAUDE.md starter per role, to copy into a project and adapt.

Who decides:

- **In a run, the person using the skill.** They own the design and the decisions; the skill does the work, reports
  it and waits for the yes before any change ([roles/](../../roles/)).
- **About the project, the repository owner.** The plans in [roadmap/](../roadmap/) record the owner's decisions,
  and the open decisions in [docs/README.md](../README.md#open-decisions) and
  [roadmap.md](../roadmap.md#open-decisions) wait for the owner.

Open: who in a team decides to adopt a pack, and on what evidence, is not written down.

## What it is not

- Not a general assistant. A general question, a quick look at a table, one-off SQL and dashboards stay with the
  Anthropic `data` plugin; general statistics too.
- Not a service. Nothing here runs as a service: Claude Code installs the packs and the scripts run on the user's
  machine ([architecture/overview.md](../architecture/overview.md#context)).
- Not a deployer. The cloud skills do not deploy and do not write production infrastructure code.
- Not a messenger. Nothing is posted and no tracker, chat or monitoring tool is connected; connectors are a phase 3
  plan ([roadmap.md](../roadmap.md#planned-not-built)).
- Not a replacement for Anthropic's `engineering` plugin. If you also have it, its `debug`, `testing-strategy`,
  `architecture` and `system-design` skills cover some of the same ground; the ai-architect skills are only for AI
  and LLM solutions. Call these by name when you want them.
- Not a model trainer. The data-scientist skills read files of data and predictions; training, tuning and serving
  are out of scope.
- LLM evals, error analysis, retrieval tuning and trace review are not covered yet; the plans name a later
  `ai-engineering` pack for them (see the [roadmap](../roadmap.md)).

## How we know it works

Results are not kept in this file. Each check below says where and how it is measured.

- **The parts hold, on every pull request.** The CI job `checks` runs `ruff format --check`, `ruff check`, `mypy`,
  `python3 tools/sync_shared.py --check` and `uv run pytest`. The tests pin the scripts' output on fixtures built
  deterministically, which is what "two runs give the same numbers" rests on, and they check the renderer, the guard
  and the form of every skill file ([guides/testing.md](../guides/testing.md#unit-tests)).
- **A skill finds the planted problem.** `claude plugin eval` runs each pack's cases in `plugins/<pack>/evals/` on a
  built fixture and grades what was produced (outcome graders) and whether the skill fired (process graders). The
  evals cost money and are run by hand; the commands are in [guides/testing.md](../guides/testing.md#evals), and
  `tools/eval_table.py` sums up a run.
- **The skill beats plain Claude.** Without `--ablation none`, each eval case also runs without the plugin, which is
  the comparison the problem above needs.
- **Claude picks the right skill.** `tools/selection_check.py` loads every pack and checks which skill Claude picks
  for each prompt in `tools/selection_cases.json`, including prompts where none of ours may fire
  ([guides/testing.md](../guides/testing.md#selection-check)).

Open:

- Where eval results are kept is an open decision ([docs/README.md](../README.md#open-decisions)).
- What counts as "beats plain Claude" (which run, how many runs per case, what difference is enough) is not defined.
- Whether two runs of a skill on the same input give the same page is not measured: the tests pin the scripts, not
  Claude's reading and writing.
- The `workflows` evals have no documented command ([guides/testing.md](../guides/testing.md#open)).
- The selection check has not been run on an account whose own plugins include `engineering`
  ([code-audit.md](../roadmap/code-audit.md#measuring-it-against-the-accounts-own-plugins)).
- No measure of real use (findings confirmed, time saved) is defined; phase 2 of software-engineering waits until
  phase 1 has run on a real repository at least once
  ([engineering-pack-v2.md](../roadmap/engineering-pack-v2.md#phase-2-engineering-lead-the-orchestrator)).

## Principles

- One skill, one repeated job, in a fixed set of sections: the job, input, Steps, Output, Reads, Writes, Never.
- Read-only until the yes. None of the skills changes your code unless you say yes; bug-hunt and test-gap write tests
  and fixes only after that yes. A contract, an incident-log entry or an e-mail is a draft on the page until then.
- Nothing is posted: `change-review`, `incident-triage` and `postmortem` put their comments and the status update on
  the page, and the user sends them.
- Each skill works on its own, because an installed plugin has nothing outside its own folder.
- Nothing real in fixtures and examples: fictional names, `example.*` addresses, no client data. The only real data
  is the public Azure and AWS list prices saved in the cloud fixtures.
