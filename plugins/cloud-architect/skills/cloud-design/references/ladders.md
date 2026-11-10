# The cloud design ladders

Five ladders, each neutral and ordered by how much somebody has to run. Climb only for a requirement you can name. The
provider file maps each option to real services and states the limits that change the choice.

| Ladder | Options, simplest first | What the climb costs |
|---|---|---|
| Compute | a managed app platform; serverless containers; functions; Kubernetes; virtual machines | a platform to run, upgrades, on-call, skills |
| Data | one managed relational database; the same with read replicas; a managed document store; a self-managed database | consistency, cost, someone to run it |
| Network | public endpoints, restricted; private endpoints for the data; everything private behind one entry; hub and spoke | subnets, DNS, routes, cost of private endpoints |
| Region | one region; two regions | a tested failover, data replication, double the bill |
| Availability | one zone; zone redundant; multi-region | a higher SKU, at least two instances, less to go wrong at once |

## The questions that flip the decision

| Question | Fact | Why it matters |
|---|---|---|
| How many separately deployed services? | `services` | a managed platform holds a few |
| Does it ship as containers? | `containers` | functions or not |
| Does it need the Kubernetes API, or control of the operating system? | `needs_kubernetes_api`, `needs_os_control` | Kubernetes or VMs only for a reason like this |
| Who can run a platform? | `platform_engineers` | what this team can operate |
| Does work arrive as short events? How long is the longest job? | `event_driven`, `max_job_minutes` | functions or not |
| Peak load and data size? | `peak_rps`, `data_gb` | whether one database is enough |
| Is the data relational? | `relational` | which store |
| Must data stores, or everything, be private? | `private_data`, `private_everything` | the network rung |
| Must it survive a zone, or a region? | `survive_zone_loss`, `survive_region_loss` | availability and regions |
| Where may the data live? | `residency_area` | which regions |

## The order of elimination

1. **Can this team run it?** A managed service nobody has to patch beats one that needs on-call.
2. **What does it have to learn?** Every new platform is weeks of a person's time.
3. **How does it fail?** Single zone, one instance, a queue that loses messages.
4. **Cost.** Monthly, from the price list, per variant. Cost separates two options that both pass; it rarely eliminates
   one on its own unless the brief gives a budget.

## Bill of materials

One item per thing that costs money. Say where each quantity comes from: "730 hours × 2 instances", "400 GB from the
brief". Leave out what is too small to change the decision and say so in a line.

A variant is a real alternative: another compute option, another network, another cloud. If two variants cost within a
few percent, say so: the choice is not about money.

## ADR (Nygard)

```markdown
# ADR-NNN: <the decision>

Date: YYYY-MM-DD
Status: Proposed

## Context
The forces at play, with the facts from the brief and the monthly cost.

## Decision
We will ...

## Consequences
What becomes easier, what becomes harder, and what we accept.
```
