# Cloud architect

For cloud architects. The skills draw the cloud infrastructure that exists from code in a repository with no login or from a read-only export, compare a brief across options with real prices, and review it against the provider's Well-Architected pillars. Install it as `cloud-architect@claude-role-skills`; the skills are called as `/cloud-architect:<skill>`.

| Skill | Use it when | It writes |
|---|---|---|
| [cloud-map](../../../plugins/cloud-architect/skills/cloud-map/SKILL.md) | you inherit cloud infrastructure or must explain it, from code with no login or a saved export | the estate as boxes inside boxes, request flows, what the internet can reach and what stops it, what is in code but not deployed and deployed but not in code |
| [cloud-design](../../../plugins/cloud-architect/skills/cloud-design/SKILL.md) | a brief arrives, before a platform is picked | compute, data, network, region and availability, decided by elimination; up to two variants or two clouds costed from the provider's price list, each price with its date and source; an ADR draft |
| [cloud-review](../../../plugins/cloud-architect/skills/cloud-review/SKILL.md) | before a release, an audit or a take-over of infrastructure | problems tied to file:line or a resource, checked against the provider's Well-Architected pillars, marked on the drawing, with what to fix first |

One brief compared across clouds with real prices, drawn and reviewed the same way, from code in a repository with no cloud login. Azure and AWS are here; a provider is one pair of files, so Google Cloud can follow later. These skills do not deploy and do not write production infrastructure code. They read Terraform, Bicep, ARM and CloudFormation (JSON and YAML), make no cloud call of their own apart from the public price lists, which are opt-in with a timeout, and never bundle a vendor's icons: boxes carry their kind in text.

## More

- Each skill's scripts, shared copies and guard: [reference/skills.md](../../reference/skills.md#cloud-architect).
- [roadmap/cloud-architect.md](../../roadmap/cloud-architect.md): the plan of the pack, Azure and AWS.
- [roadmap/architect-packs.md](../../roadmap/architect-packs.md): the series of architect packs.
