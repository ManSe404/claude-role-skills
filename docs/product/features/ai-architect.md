# AI solutions architect

For AI solutions architects. The skills decide what an AI solution should be, pick and price its stack, draw it as an interactive page and review one that exists. Install it as `ai-architect@claude-role-skills`; the skills are called as `/ai-architect:<skill>`.

| Skill | Use it when | It writes |
|---|---|---|
| [ai-pattern](../../../plugins/ai-architect/skills/ai-pattern/SKILL.md) | a brief arrives, before anything is built | what the solution should be (no LLM, one call, long context, RAG, workflow, agentic RAG, agent, multi-agent), decided by elimination against the brief's facts; the binding constraint, what would change it, acceptance criteria, an ADR draft |
| [ai-stack](../../../plugins/ai-architect/skills/ai-stack/SKILL.md) | the pattern is chosen and the tools must be picked | the model per step, embeddings, store, orchestration, hosting, tracing, evals and guardrails, in two variants at most; monthly cost and latency from a dated price table; lock-in; checks before the offer |
| [ai-architecture](../../../plugins/ai-architect/skills/ai-architecture/SKILL.md) | a solution must be shown to a client or a team | one interactive page: components in zones with their details, request flows played step by step, a switch between variants, and where untrusted text enters and what it can reach |
| [ai-review](../../../plugins/ai-architect/skills/ai-review/SKILL.md) | before a release, a take-over or a hand-over | the design read from the code against eleven common failures, with file:line findings and fixes, and the problem spots on the architecture |

## More

- Each skill's scripts, shared copies and guard: [reference/skills.md](../../reference/skills.md#ai-architect).
- [roadmap/ai-architect.md](../../roadmap/ai-architect.md): the original plan of the pack.
- [roadmap/architect-packs.md](../../roadmap/architect-packs.md): the series of architect packs.
