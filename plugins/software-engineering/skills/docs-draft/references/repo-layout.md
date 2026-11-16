# The repository layout

Every document this skill drafts has a place in one layout, so a person or an agent finds the same thing in
the same place in every repository. A repository that already follows another documented convention (a
company standard, a docs site) keeps it; the fixed paths below (`docs/adr/`, `docs/diagrams/`) match the
common ADR and C4-as-code conventions.

```
README.md              what it is and who it is for, run in five minutes, link to docs/README.md
CLAUDE.md / AGENTS.md  rules for agents working in the repository
docs/
  README.md            the index: reading order (numbered), each document with status and last checked date
  product/             WHY and WHAT: vision.md, users-and-problems.md, glossary.md,
                       features/README.md (the feature catalogue), features/<feature>.md
  roadmap.md           goals and phases with status, linking to product/features
  design/              product and UX design only: screens, flows, design system, mock-ups (visuals/);
                       never software architecture
  architecture/        HOW it is built: overview.md (context, goals, constraints), building-blocks.md,
                       runtime.md (the flows that matter), data.md, deployment.md, crosscutting.md
                       (security, observability, errors), risks.md
  diagrams/            diagrams as code (Mermaid or C4): context, container, flows
  adr/                 NNNN-short-title.md, Nygard (Status, Context, Decision, Consequences), immutable once
                       accepted; a new ADR supersedes an old one
  reference/           what exists, checkable against the code: codebase.md, services/<name>.md, api.md,
                       configuration.md, data-model.md, cli.md
  guides/              how to: setup.md, development.md, testing.md, release.md, onboarding.md
  operations/          runbooks, deployment, monitoring: only for something that runs somewhere
```

## Where each kind goes

| Kind | Path |
|---|---|
| README | `README.md` |
| Runbook | `docs/operations/<symptom-or-job>.md` |
| API reference | `docs/reference/api.md` |
| Feature catalogue | `docs/product/features/README.md` |
| Onboarding | `docs/guides/onboarding.md` |
| Architecture document | `docs/architecture/overview.md`, its diagrams in `docs/diagrams/` |
| Docs set | the whole layout, as far as it applies |

## Rules

- No numbers in folder or file names: links, ADR registers and tools point at these paths, and renumbering
  breaks them. Reading order is the numbered list in `docs/README.md`.
- Only what applies: a script or small tool has a README alone; a small app, a template or a personal site
  has README, `docs/README.md`, `roadmap.md` while work on it continues, `architecture/` and `adr/` once a
  decision exists; a larger project (a product, a service, a library others build on, client work) has the
  full set, with `product/vision.md` as its introduction.
- In a larger project, `product/vision.md` is the introduction, first in the reading order, and the README's first
  paragraph links to it. Its sections, in order: the problem or opportunity (what is wrong or missing, for
  whom, how we know), how we solve it, why this way (the options that lost, linking to `adr/`), for whom, what
  it is not, how we know it works (the measure; its current value stays out of the repository). Unknowns are
  marked as open.
- Every repository with a `docs/` folder has a feature catalogue, `product/features/README.md`, linked from
  `README.md` and `docs/README.md`: one line on what it covers, a table *Feature | What you can do | Status |
  Where in code | Doc*, then a short paragraph per group. Status is shipped, partial (with the limit named),
  planned or broken, and every row is checked against an entry point (a page, a route, a command, a worker,
  a public function) and its tests. A template lists what a service gets by starting from it, a library
  its public capabilities. Larger features keep their own `features/<feature>.md`, linked from the table.
- A project that is finished or frozen has no `roadmap.md`; its status is one line in `README.md` and
  `docs/README.md`.
- `roadmap.md` holds the project's next items in priority order, each with status, what it touches and what is
  still open.
- Visuals sit with their topic: UX images in `design/visuals/`, architecture in `diagrams/`. A diagram is
  text (Mermaid or C4); an image is allowed only for a mock-up or a screenshot, with its source linked.
- `reference/` and `architecture/` change in the same commit as the code they describe.
- The repository holds the current truth that ships with the code. Dated status, snapshots, reports, eval
  results, meeting notes and drafts belong to the owner's notes, not to the repository.
- Moving an existing document into the layout keeps its history (`git mv`) and its content, and the links
  to it are fixed in the same change.
- The language is the one the repository's documents use; when the owner sets a rule (for example English
  for personal repositories, the company language for company ones), that rule wins.
