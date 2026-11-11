# Solutions architect

A small pack on top of the four specialist architect packs (`ai-architect`, `data-architect`, `software-architect`, `cloud-architect`) that owns the whole solution: `solution-brief` frames a client brief once and sends the right specialists with shared facts, and `solution-blueprint` joins their pages into one solution and names what contradicts. Install it as `solutions-architect@claude-role-skills`; the skills are called as `/solutions-architect:<skill>`.

| Skill | Use it when | It writes |
|---|---|---|
| [solution-brief](../../../plugins/solutions-architect/skills/solution-brief/SKILL.md) | a client brief arrives that may cross several areas, before any specialist runs | the brief framed once, which specialists are needed and in which order, why any is not needed, the exact calls to run next with the shared facts each must use |
| [solution-blueprint](../../../plugins/solutions-architect/skills/solution-blueprint/SKILL.md) | the specialist pages exist and must become one solution | the whole solution drawn as one picture, one list of decisions with where each came from, one cost summary per cloud or variant, every conflict between the pages with the side recommended, what nobody covered, what to do first |

Without this pack, specialist pages contradict each other unnoticed: a model in one region and the data in another, each page with its own cost total and nothing adding them up. Joining the pages and naming the conflicts is all it does: it never redoes a specialist's work and never recomputes a specialist's number. `join_facts.py` lists where the pages disagree, as places to read, and Claude reads them and recommends a side. Costs are grouped per currency and never added across currencies. Installing the pack installs the four specialist packs, because they come from the same marketplace.

## More

- Each skill's scripts, shared copies and guard: [reference/skills.md](../../reference/skills.md#solutions-architect).
- [roadmap/solutions-architect.md](../../roadmap/solutions-architect.md): the plan of the pack.
- [roadmap/architect-packs.md](../../roadmap/architect-packs.md): the series of architect packs.
