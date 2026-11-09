# Architecture styles: the ladder

Simplest first, by moving parts somebody has to run. Climb only for a requirement you can name.

| Option | What it is | What it costs | Stops being enough when |
|---|---|---|---|
| One deployable | One process, simple folders | discipline only | several business areas start tangling |
| A modular monolith | One deployable, modules with enforced boundaries and their own data | boundary checks in CI | parts must ship or scale on their own, or need another runtime |
| Serverless functions | Short stateless handlers, billed per call | cold starts, limits, local testing | work runs long, holds state, or load is steady |
| A few services | Two to six deployables around real boundaries | deployment, contracts, tracing | several consumers must react to the same things |
| Services with an event backbone | Services publish facts; others react | a broker, eventual consistency, replays | many teams need full autonomy |
| Microservices | Many small services, one team each | a platform team, on-call per service | (top of the ladder) |

Splitting a system is paid for in operations and in lost transactions. The reasons that justify it
are few: release independence, very different scale, a different runtime, and team autonomy.

## The questions that flip the decision

| Question | Fact | Why it matters |
|---|---|---|
| How many teams would ship separately? | `teams` | microservices need several |
| Must parts release on their own schedules? | `ship_separately` | one deployable or not |
| How much more load does the busiest part take? | `scale_ratio` | whether one part must scale alone |
| Does a part need another language or runtime? | `runtimes_differ` | one deployable or not |
| Must one transaction span business areas? | `one_transaction_across` | a split loses it |
| Does work run long or hold state? Is it idle most of the time? | `long_running`, `idle_most_of_the_time` | functions or not |
| Must several consumers react to the same events? | `many_react_to_events` | an event backbone or not |
| Who runs deployment, tracing and on-call? | `platform_engineers` | what this team can operate |

## The order of elimination

1. **Can this team run it?** Every service needs a deployment, a dashboard and someone on call.
2. **Consistency:** what must be true at the same moment. Between services it is gone.
3. **Change independence:** what must change without the rest.
4. **Operations:** failure modes, tracing, recovery.
5. **Cost:** relative here; prices need a vendor and a region.

## Boundaries

Draw them around business areas, not technical layers. Each boundary owns its data: a table with two
writers is one boundary in disguise. Decide what crosses a boundary: a call, an event or nothing.

## ADR (Nygard)

```markdown
# ADR-NNN: <the decision>

Date: YYYY-MM-DD
Status: Proposed

## Context
The forces at play, with the facts from the brief.

## Decision
We will ...

## Consequences
What becomes easier, what becomes harder, and what we accept.
```
