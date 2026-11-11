# claude-role-skills

[![CI](https://github.com/ManSe404/claude-role-skills/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ManSe404/claude-role-skills/actions/workflows/ci.yml)

Claude Code skills by role. Each skill does one job that keeps coming back, counts with its own
scripts instead of estimating, and ends in one self-contained web page you can read and share, or, when the
result is text, in a Markdown note with the page beside it.

| Pack | For | Skills |
|---|---|---|
| [software-engineering](docs/product/features/software-engineering.md) | software engineers | codebase-map, impact, bug-hunt, test-gap, dependency-audit, code-audit, change-review, docs-draft, incident-triage, postmortem |
| [ai-architect](docs/product/features/ai-architect.md) | AI solutions architects | ai-pattern, ai-stack, ai-architecture, ai-review |
| [data-architect](docs/product/features/data-architect.md) | data architects | data-platform, data-model, data-map, data-review |
| [data-engineer](docs/product/features/data-engineer.md) | data engineers who run a platform | source-profile, source-contract, pipeline-incident, data-quality, data-cost, data-migration, data-product |
| [software-architect](docs/product/features/software-architect.md) | software architects | arch-style, arch-c4, arch-review, arch-evolve |
| [cloud-architect](docs/product/features/cloud-architect.md) | cloud architects | cloud-map, cloud-design, cloud-review |
| [solutions-architect](docs/product/features/solutions-architect.md) | solutions architects, who join the specialists' work | solution-brief, solution-blueprint |
| [data-analyst](docs/product/features/data-analyst.md) | data analysts | metric-spec, number-moved, number-reconcile, report-review |
| [data-scientist](docs/product/features/data-scientist.md) | data scientists | ds-frame, ds-explore, ds-dataset, ds-evaluate, ds-experiment |
| [workflows](docs/product/features/workflows.md) | teams running a process over the skills above | take-over, ship-change, incident-run, data-incident, new-solution, platform-month, model-build |

## Try it

You need Claude Code, `git` and Python 3.11 or newer. The scripts use the standard library only. Inside Claude Code:

```text
/plugin marketplace add ManSe404/claude-role-skills
/plugin install software-engineering@claude-role-skills
```

Then, in a repository you do not know, `/software-engineering:codebase-map`. Claude also picks a skill by itself when
your request matches its description. The page goes outside your repository, to `$CLAUDE_PAGES_DIR/<repo>/`, or
`~/claude-pages/<repo>/` when the variable is not set.

The architecture page is the one to try first: click a component, press Play on a flow, switch
between the routed workflow and agentic RAG, turn on the trust view.
[`ai-architecture/references/example.json`](plugins/ai-architect/skills/ai-architecture/references/example.json)
renders into it.

Each `SKILL.md` says its job, its input, its steps, its output, what it reads, what it writes and
what it never does. Read a skill before you use it. None of them changes your code unless you say
yes; bug-hunt and test-gap write tests and fixes only after that yes.

Every pack, and copying the skills into one project: [docs/guides/setup.md](docs/guides/setup.md).

## Documentation

Start at [docs/README.md](docs/README.md): the vision, what each pack does, the roadmap, how it is built (packs,
shared files, the page renderer, the guard hooks, the evals), the list of every skill, and the guides for
development and testing. Rules for agents working here are in [CLAUDE.md](CLAUDE.md).

## License

MIT, see [LICENSE](LICENSE). Notices for the page design and the fonts are in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). Everything
in the fixtures and the example pages is fictional, except the public Azure and AWS list prices saved in
`fixtures/acme-cloud` and `fixtures/acme-cloud-aws`.
