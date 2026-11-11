# Vision

## What it is

Claude Code skills by role, in one marketplace with one plugin (a pack) per role. Each skill does one job that
keeps coming back, counts with its own scripts instead of estimating, and ends in one self-contained web page you can
read and share, or, when the result is text, in a Markdown note with the page beside it.

## Why

A skill that only tells Claude what a good review, map or decision looks like still leaves the facts to Claude's
reading, and two runs give two answers. These skills differ in method, not in topics:

- **Scripts do the counting.** Inventory, import graph, references, stack-trace mapping, coverage ranking, dependency
  lookups, corpus size, the hard rules of the AI pattern and data platform ladders, cost at volume, the AI inventory
  of a repository, data profiles, table lineage from SQL, dbt and notebooks, and module graphs with their history are
  scripts with fixed output, so two runs give the same numbers. Claude reads before it claims and tags what it did not check.
- **One page as the result.** Claude writes the content as JSON and a script draws the page, so every page of every
  skill has the same layout, every value is escaped and nothing is fetched from the network. The page is one file
  you can send to anyone.
- **The Never rules are enforced.** While a skill works, a hook makes Claude Code ask before a change or a step
  online, and keeps personal data out of what the data skills see and write.
- **The skills are tested.** Made-up projects with planted problems back the scripts' tests, the example pages and
  the evals that check the planted problem is found.

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

`roles/` holds a CLAUDE.md starter per role, to copy into a project and adapt.

## Principles

- One skill, one repeated job, in a fixed set of sections: the job, input, Steps, Output, Reads, Writes, Never.
- Read-only until the yes. None of the skills changes your code unless you say yes; bug-hunt and test-gap write tests
  and fixes only after that yes. A contract, an incident-log entry or an e-mail is a draft on the page until then.
- Nothing is posted: `change-review`, `incident-triage` and `postmortem` put their comments and the status update on
  the page, and the user sends them.
- Each skill works on its own, because an installed plugin has nothing outside its own folder.
- Nothing real in fixtures and examples: fictional names, `example.*` addresses, no client data. The only real data
  is the public Azure and AWS list prices saved in the cloud fixtures.

## What it is not

- Not a general assistant. A general question, a quick look at a table, one-off SQL and dashboards stay with the
  Anthropic `data` plugin; general statistics too.
- Not a deployer. The cloud skills do not deploy and do not write production infrastructure code.
- Not a replacement for Anthropic's `engineering` plugin. If you also have it, its `debug`, `testing-strategy`,
  `architecture` and `system-design` skills cover some of the same ground; the ai-architect skills are only for AI
  and LLM solutions. Call these by name when you want them.
- Not a model trainer. The data-scientist skills read files of data and predictions; training, tuning and serving
  are out of scope.
- LLM evals, error analysis, retrieval tuning and trace review are not covered yet; the plans name a later
  `ai-engineering` pack for them (see the [roadmap](../roadmap.md)).
