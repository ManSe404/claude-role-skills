# Routing a brief to the specialists

Each row is a skill that decides one area. A brief usually needs only some of them. A skill is needed
when something in the brief asks for what it decides. It is not needed when the brief has no such
question, or when the answer is already fixed and written in the brief.

| Skill | Decides | Bring it in when the brief has | Not needed when |
|---|---|---|---|
| `ai-architect:ai-pattern` | what the AI part should be | language understanding, drafting, reading unstructured text or documents, a chat with people | no model, no text understanding, only rules or forms |
| `ai-architect:ai-stack` | the model, retrieval store, hosting and cost of the AI part | an AI part that will be built (it follows `ai-pattern`) | no AI part, or the stack is already fixed in the brief |
| `data-architect:data-platform` | the data platform: sources, layers, reporting, sizing | reporting over several sources, history, analytics, a warehouse or lake | one application database with its own screens and exports only |
| `software-architect:arch-style` | the shape of the software | an application with several business areas or teams, a monolith or services question | no custom software is built, or only a script |
| `cloud-architect:cloud-design` | what it runs on, region, availability, monthly cost | hosting or a region is open, cloud cost must be known, a comparison between clouds | hosting is already fixed and costed in the brief |

## The order

1. `ai-pattern`, because the AI shape decides what else is needed.
2. `data-platform`, because the data rules and sizes feed the rest.
3. `arch-style`, because the shape of the software decides what must be hosted.
4. `ai-stack`, because it needs the pattern and, for hosting, the regions and the data rules.
5. `cloud-design`, last, because it hosts and costs the output of all the others.

A later step may start before an earlier one finishes only when it does not need that page.

## Writing the calls

One call per needed specialist, in order, written so it can be copied and run. It names the
plugin and skill, the brief, and the shared facts that specialist must use, for example:

`/data-architect:data-platform docs/briefs/x.md Use these shared facts: personal data stays in the EU; ...`

A call never asks a specialist to add up other pages' costs or to compare a total with the budget: that is
`solution-blueprint`'s job, and doing it twice is how totals drift apart.

## Shared facts

Regions and data rules, budget (amount, currency, what it covers), team size, deadlines, and the assumptions the
specialists would otherwise each make differently. Use the same wording in every call and in `facts`, because
`solution-blueprint` compares them. A fact the brief does not state is marked unknown and listed under Unknown.

## Writing `facts`

- `regions` and `data` (with `rule`) carry where data may go.
- `budget`: `{"monthly": 6000, "currency": "EUR", "source": "docs/briefs/x.md"}`. Leave it out if the brief
  states none, and list it as unknown.
- `specialists`: the skill names in order, for example `["ai-pattern", "data-platform"]`.
- `assumptions`: every shared assumption, each with the same wording used in the calls.
