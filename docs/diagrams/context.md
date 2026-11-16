# Context view

Who uses the skills, what they run in and what they reach. The parts inside the repository are in the
[container view](container.md).

```mermaid
flowchart LR
  user["Person using Claude Code<br/>(an engineer, architect, analyst or scientist)"]
  maint["Maintainer of this repository"]
  cc["Claude Code<br/>installs the packs, picks a skill,<br/>runs its hook and its scripts"]
  repo["claude-role-skills<br/>marketplace of ten packs, 50 skills"]
  work[("The person's repository or data<br/>code, git history, logs, data files,<br/>briefs, infrastructure code")]
  pages[("Pages folder<br/>CLAUDE_PAGES_DIR, default ~/claude-pages")]
  registries["Package registries and OSV<br/>dependency-audit --online"]
  prices["Azure and AWS price lists<br/>cloud prices --online"]
  model["Claude models<br/>evals and the selection check"]

  user --> cc
  cc -- "/plugin marketplace add, /plugin install" --> repo
  cc -- "the skill's scripts read it, read-only" --> work
  cc -- "page JSON, HTML and Markdown note" --> pages
  user -- "opens and sends on" --> pages
  cc -. "opt-in, the guard asks first" .-> registries
  cc -. "opt-in, the guard asks first" .-> prices
  maint -- "claude plugin eval, tools/selection_check.py" --> model
  maint -- "edits, tests, CI" --> repo
```

- Nothing in the repository runs as a service. The scripts run on the person's machine with `python3` and the
  standard library.
- The only outbound calls are opt-in: `--online` in `plugins/software-engineering/skills/dependency-audit/scripts/deps.py`
  (OSV, PyPI, npm, NuGet) and in `shared/cloud_prices.py` (the endpoints in `shared/cloud/PROVIDER.json`). Every one
  has a timeout, and the guard asks before any of them during the skill's turn.
- The evals and the selection check start real Claude sessions through the `claude` CLI; the skills themselves call
  no model.
