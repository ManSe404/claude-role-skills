# Plan: the architect packs

Status: agreed with Stefan on 2026-11-09. Each pack gets its own detailed plan before it is built;
`data-architect` was the first, see [data-architect.md](data-architect.md).

## Goal

One specialist pack per area of architecture, and one small `solutions-architect` pack on top that
installs them and joins their work. Each specialist answers the same four questions for its area:
what should it be, what is there now, what does it look like, what is wrong with it.

## Order

| Step | Pack | Skills | New work |
|---|---|---|---|
| done | `ai-architect` | ai-pattern, ai-stack, ai-architecture, ai-review | committed as 5569e48 |
| 1 | `data-architect` | data-platform, data-model, data-map, data-review | built; `model` block, `reach` view, `facts`, SQL and dbt reader |
| 2 | `software-architect` | arch-style, arch-c4, arch-review, arch-evolve | built; nested boxes, coupling from code and git |
| 3a | `cloud-architect`, Azure | cloud-map, cloud-design, cloud-review | built, see [cloud-architect.md](cloud-architect.md); Terraform, Bicep and ARM reader, Azure prices |
| 3b | `cloud-architect`, AWS | the same three | built; CloudFormation reader, AWS offer files as prices, one design compared across both clouds |
| 4 | `solutions-architect` | solution-brief, solution-blueprint | built, see [solutions-architect.md](solutions-architect.md); joins the pages, finds conflicts, installs the others (dependency install tested 2026-11-10) |
| later | data analyst, data scientist, `ai-engineering` | to be planned | |

`software-engineering` stays as it is: it is the daily work on code, not architecture.

The order helps the build. Nested boxes are the biggest drawing job and C4 needs them too, so they
are built and tested in step 2 and step 3 reuses them. `reach` is built in step 1 for personal data
and reused in step 3 for internet exposure.

## Settled early, because they are expensive to change later

**1. A `facts` section in every page's JSON, from step 1.** `solutions-architect` comes last but has
to join the pages. It cannot do that from text written for people: it needs regions, data classes,
components, dated costs, decisions and assumptions in one shape. Without this, every pack is
reworked at the end. `ai-architect` gets it during step 1. Format in
[data-architect.md](data-architect.md#facts).

**2. Five skills will match "draw the architecture".** `codebase-map`, `ai-architecture`, `data-map`,
`arch-c4` and `cloud-map`. Every description must name its subject (a repository, an AI solution, a
data platform, a system's structure, cloud infrastructure). `tools/selection_check.py` measures whether Claude
picks the right one with every pack loaded, which `claude plugin eval` cannot do, because it loads one pack at a time.

**3. The simplest thing that passes.** Every deciding skill starts at the bottom of a ladder and
climbs only for a requirement it can name. Every fixture includes a brief where the right answer is
boring, so the eval catches a skill that overbuilds.

## The shape every specialist follows

- Decide, draw, review, as in `ai-architect`: a rule script that eliminates options and never
  chooses, a `decision` block, an `architecture` page with flows and variants, findings with file:line.
- Stdlib-only scripts that count; anything the scripts did not count is tagged `[high]`, `[med]` or
  `[guess]`.
- Facts that change (prices, quotas, regions, versions) carry their date and source.
- A fictional fixture with planted faults, five evals with a skill-fired grader, examples made by
  running the skills on the fixture and checked by hand.

## 2. software-architect

Exists elsewhere: `engineering:architecture` and `engineering:system-design` (generic frameworks and
ADR text), community C4, arc42 and ADR skills. Ours differs by measuring: the structure and its
problems come from the code and the git history, and end in a clickable page.

- `arch-style`: monolith, modular monolith, services, event-driven, serverless, ruled out from the
  simplest up against the team, deployment, scale and consistency needs.
- `arch-c4`: context, containers and components, from a brief or from code, as nested boxes.
- `arch-review`: a design reviewed from its documents and ADRs before it is built: waiting chains against latency
  goals, data written by two parts, promises with no mechanism, goals without numbers, contradictions, open
  decisions. Since 2026-11-10; the structure of existing code (cycles, layer breaks, hot spots) moved to the
  software-engineering skill `code-audit`, see [code-audit.md](code-audit.md).
- `arch-evolve`: from the current design to a target in safe steps, with ADRs.

## 3. cloud-architect

Vendors cover one cloud each, and both deploy:
- `microsoft/azure-skills` (88 SKILL.md, MIT): deployment, cost estimates, compliance, reliability,
  infrastructure planning, Mermaid diagrams of live resources.
- `awslabs/agent-plugins` (34 SKILL.md, Apache-2.0): deploy-on-aws with architecture recommendations,
  cost estimates, infrastructure code and `aws-architecture-diagram` (draw.io).
- `azure-architecture-autopilot` (github/awesome-copilot): interactive diagrams with official icons
  and nested boxes, from chat or from a subscription behind `az login`, then Bicep and deployment.
- Community multi-cloud skills, going by their listings: text tables, no real prices, no drawings.

The gap, and so the job of this pack: **one brief compared across clouds with real prices, drawn and
reviewed the same way**, starting from Bicep, Terraform or CloudFormation in a repository with no
cloud login. It does not deploy and does not write production infrastructure code.

One pack with a file per provider, because comparing needs both in the same skill:
- `cloud-map`: what exists, from code or read-only after a yes: nested boxes, flows, internet
  exposure, code against what is deployed.
- `cloud-design`: options ruled out against a brief, up to two variants or two clouds, monthly cost
  from each provider's price list summarised per cloud, an ADR.
- `cloud-review`: problems tied to file:line or a resource, checked against the provider's
  Well-Architected pillars (five for Azure, six for AWS), marked on the drawing.

| | Azure | AWS | Google (later) |
|---|---|---|---|
| Code | Terraform, Bicep | Terraform, CloudFormation | Terraform |
| Nesting | subscription, resource group, VNet, subnet | account, region, VPC, zone, subnet | project, VPC, subnet |
| Live, read-only | `az` | `aws` | `gcloud` |
| Prices | Retail Prices API, no login (tested 2026-11-09) | Price List API, no login (tested 2026-11-09) | needs an API key (403 without one) |

Open for step 3: try `azure-architecture-autopilot` on a test resource group first, asking only for
a diagram because it can also deploy. Official icons or our own: Microsoft allows its icons in
architecture diagrams and documentation only, so they cannot fall under our MIT licence; AWS's terms
are not checked yet.

## 4. solutions-architect

About two skills, plus `dependencies` in `plugin.json` so that installing it installs the others
(documented for plugins in one marketplace; not yet tried here).

- `solution-brief`: frames the brief, decides which specialists are needed and in what order.
- `solution-blueprint`: joins their pages through `facts`: one drawing, one cost total, and a script
  that lists conflicts, such as a model in one region and the data in another.

It is built last because what needs joining is only known once two specialists produce real pages.

## Cost

Example pages have cost about $2.50 per skill run ($6.55 for 5, $10.93 for 4 plus reruns). 16 runs
across these packs: about $40. Evals are extra and run only when Stefan asks.

## Hooks (2026-11-10)

Stefan asked for hooks after the packs were built. Earlier the answer was no, because a hook cannot tell when the user
has said yes. Two facts from the hooks documentation changed that. A hook declared in a skill's frontmatter is
registered when the skill is invoked. Every hook call carries the id of the user's prompt. So `shared/guard.py`
enforces a skill's checkable Never rules only in the turn that invoked the skill, and steps aside after the user's
next message, which is where "after the yes" happens.

- Changes and network calls get `ask`, not `deny`. Interactively the user gets a prompt, and a fix the user already
  approved can never be stuck. In `claude -p` an `ask` is refused, as the probes showed, including with
  `--permission-mode bypassPermissions`.
- Raw reads of data files with personal columns get `deny`, because the scripts are the way to read them.
  E-mail addresses, IBANs and JMBGs are replaced in Bash and Read output with `updatedToolOutput`.
- `${CLAUDE_PLUGIN_ROOT}` expands in a plugin skill's hook command and `${CLAUDE_SKILL_DIR}` does not. A missing script
  made python exit 2, which blocked every call. The command therefore looks in the plugin, the project and `~/.claude`,
  and does nothing if the guard is not there.

Each rule was checked in a live session, as a plugin and as a skill copied into a project. Nothing is guarded before
the skill is invoked, even later in the same turn.
