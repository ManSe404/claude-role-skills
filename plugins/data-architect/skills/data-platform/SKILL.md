---
name: data-platform
description: Use before building or rebuilding a data platform, when a brief or a list of sources arrives, to decide what it should be - reports on the source, one database with scheduled SQL, a warehouse, a lakehouse, a streaming path or a data mesh - by eliminating options against the brief's facts, ending in a decision page with sizing, the layers and an ADR draft.
argument-hint: "[brief file or text] [samples folder]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/data-platform/scripts/guard.py" ] && exec python3 "$d/skills/data-platform/scripts/guard.py" pre data-platform personal; done; true'
  PostToolUse:
    - matcher: "Bash|Read"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/data-platform/scripts/guard.py" ] && exec python3 "$d/skills/data-platform/scripts/guard.py" post data-platform personal; done; true'
---

# Data platform

The job: decide what a data platform should be before anyone builds it. Start from the option with
the fewest moving parts and climb only when the one below fails a named requirement. It writes
nothing but the page; the ADR goes into a repo only after the yes.

Input: a brief (a file or text), optionally a folder of sample files. Default: ask for the brief.

## Steps

1. Read [references/platforms.md](references/platforms.md): the ladder, what each option costs a
   team to run, the order of elimination and the ADR format.
2. Frame: the consumers and what they decide, the sources, volumes and growth, freshness per use,
   what is not negotiable (residency, retention, budget), and the team. Write each one with where
   it came from in the brief.
3. Ask what flips the decision. If facts from the table in platforms.md are open, ask for the two to
   four that matter most, in plain words, and wait. If the user says go on, assume, and put every
   assumption on the page next to the decision it drives.
4. Samples, if given: `python3 "${CLAUDE_SKILL_DIR}/scripts/data_profile.py" FOLDER`, output to your
   scratchpad. When the folder is a sample, size the full set from the brief and tag it [med].
5. Hard rules and sizing: write the facts as JSON in your scratchpad and run
   `python3 "${CLAUDE_SKILL_DIR}/scripts/platform_rules.py" FACTS.json` (`--facts` lists them). Every
   eliminated option keeps the rule that eliminated it. Never overrule a rule; fix the fact.
6. Weigh what is still open in the order: can this team run it, freshness, cost of wrong data,
   governance, cost. The first factor that rules an option out eliminates it; the factor that
   separates the chosen option from the next one up is the binding constraint. Name it.
7. Choose the lowest open option that passes. Climb above `lowest_open` only for a reason you can
   name from the brief.
8. Paths: only the paths that need streaming get it. One fast feed does not make the whole platform
   streaming.
9. Layers: what each one keeps, for how long, and who may read it.
10. What would change the decision: three to five conditions (volume ×10, a second domain team, a
    use that needs seconds), each with the option it would lead to.
11. Acceptance criteria: three to five, each with a threshold and how it is measured before launch.
12. ADR draft in Nygard's format as a code block. Offer to write it into the repo; write only after
    the yes.
13. Write the page JSON, with `facts`, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format, including
`facts` and `reach`, and [references/example.json](references/example.json) for a filled page.

Sections in this order: The brief (kv, with sources), Assumptions (list, each with the decision it
drives; omit when none), Sizing (table: today, after one and two years, daily ingest, and the
thresholds the rules used), Decision (a `decision` block: every option of the ladder, factors as
columns, each eliminated option with its rule or factor), Why this one (text: the binding
constraint), The platform (an `architecture` block, zones left to right: sources, ingest, the layers,
serving, consumers, operations; links point the way the data goes; `reach` from the sources with
personal data to the consumers, stopping at masking), Layers (table: layer, keeps, retention, who
reads it), What would change it (list), Acceptance criteria (table), ADR draft (code), Open questions.
Stats on top: size after two years, sources, tightest freshness, options left after the hard rules,
the chosen option. The verdict says the option and the binding constraint in two sentences.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/data-platform-<YYYY-MM-DD>.*`. Write the
page in the language of the request; Serbian pages in Latin script.

## Reads

- the brief and the samples folder, read-only

## Writes

- the page and its JSON, outside the repo; the ADR file only after the yes

## Never

- Never proposes a lakehouse where a database passes, and never a mesh without several domain teams
  that have their own engineers.
- Never quotes a vendor's price, limit or region without its date and source. This skill sizes in GB
  and rows; prices belong to the `cloud-architect` pack.
- Never prints a personal value from a sample, and never sends the brief or the samples anywhere.
