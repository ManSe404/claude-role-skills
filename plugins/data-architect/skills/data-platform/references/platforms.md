# Data platforms: the ladder

Simplest first, by moving parts somebody has to run. Climb only for a requirement you can name.

| Option | What it is | Stops being enough when |
|---|---|---|
| Reports on the source or a replica | BI reads the system of record or its read replica | sources must be joined, the source overwrites history, or it cannot take the load |
| One database with scheduled SQL | A relational database, loaded by scheduled jobs, modelled in SQL | it outgrows one server (a few TB), or files and images must be processed |
| A managed warehouse | Separate storage and compute for SQL, loaded by ELT | files, images or model training on raw data enter the picture |
| A lakehouse in layers | Open files with table formats, in raw, cleaned and served layers | a use needs data within minutes on some path |
| A lakehouse with a streaming path | The same, plus a streaming path for the feeds that need it | several domains must own and publish their own data |
| A data mesh | Domain teams own data products on a shared platform | (top of the ladder: it needs real domain teams and a platform team) |

## The questions that flip the decision

Ask these first. Each maps to a fact of `platform_rules.py`.

| Question | Fact | Why it matters |
|---|---|---|
| How big is it today, and how fast does it grow? | `data_gb`, `growth_gb_per_month` | one database or not |
| Must sources be joined? Does the source keep history? Can it take the load? | `joins_across_sources`, `source_keeps_history`, `source_can_take_load` | whether a platform is needed at all |
| Are there files, images or documents to process? Models trained on raw data? | `files_or_images`, `ml_on_raw` | a warehouse is enough or not |
| What is the tightest freshness anyone truly needs, and why? | `freshness_minutes` | a streaming path or not |
| Who will run it? Which domains have their own engineers? | `data_engineers`, `domain_teams` | what the team can operate; a mesh or not |

Ask for the real need behind a freshness number: "real time" often means "this morning".

## The order of elimination

After the hard rules, weigh the open options in this order. The first factor that rules one out
decides it.

1. **Can this team run it?** A platform nobody can operate fails on the first bad night.
2. **Freshness:** per use, not for the platform as a whole.
3. **Cost of wrong data:** who acts on it, and what a wrong number costs.
4. **Governance:** residency, retention, personal data, audit.
5. **Cost:** relative here. Prices need a vendor and a region, and come later.

## Layers

Name each layer for what it guarantees, not for fashion:
- **Raw:** as delivered, append-only, kept so a load can be replayed.
- **Cleaned:** typed, deduplicated, keys mapped, personal data classified.
- **Served:** modelled for its consumers. Consumers read only this layer.

Personal data is masked or dropped at a named point, and that point appears on the drawing.

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
