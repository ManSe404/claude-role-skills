---
name: ai-pattern
description: Decides what an AI or LLM solution should be, from no LLM to RAG, a workflow or agents, by ruling options out against the brief, with acceptance criteria and an ADR draft.
when_to_use: Use before building an AI or LLM solution, when a brief or use case arrives and the approach is still open.
argument-hint: "[brief file or text] [documents folder]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/ai-pattern/scripts/guard.py" ] && exec python3 "$d/skills/ai-pattern/scripts/guard.py" pre ai-pattern; done; true'
---

# AI pattern

The job: decide what an AI solution should be before anyone builds it. Start from the simplest
option and climb only when the one below fails a named requirement. It writes nothing but the
page; the ADR goes into a repo only after the yes.

Input: a brief (a file or text), optionally a folder of the documents the solution must know or
a repository. Default: ask for the brief.

## Steps

1. Read [references/patterns.md](references/patterns.md): the ladder, the two rules that decide
   most briefs, the order of elimination and the ADR format.
2. Frame: users, the job, volume and peak, success, and what is not negotiable (law, where data
   may go, latency, budget). Write each one with where it came from in the brief.
3. Ask what flips the decision. If the facts in the table of questions in patterns.md are open,
   ask for the two to four that matter most, in plain words, and wait. If the user says go on,
   assume, and put every assumption on the page next to the decision it drives.
4. Split the work: every step the solution does, and who does it (the model, an existing system
   or a person) and why. A step with a number, a status or a rule is a system's, not the model's.
5. Documents, if given: `python3 "${CLAUDE_SKILL_DIR}/scripts/corpus_stats.py" FOLDER --window N`
   with N your context budget. When the folder is a sample, size the full set from the brief and
   tag it [med].
6. Hard rules: write the facts as JSON in your scratchpad and run
   `python3 "${CLAUDE_SKILL_DIR}/scripts/decide.py" FACTS.json` (`--facts` lists them). Every
   eliminated option keeps the rule that eliminated it. Never overrule a rule; fix the fact.
7. Weigh what is still open in the order predictability, cost of an error, observability,
   latency, cost. The first factor that rules an option out eliminates it; the factor that
   separates the chosen option from the next one up is the binding constraint. Name it.
8. Choose the lowest rung that passes. Climb above `lowest_open` only for a reason you can name
   from the brief.
9. What would change the decision: three to five conditions (volume ×10, writes to the ERP, a new
   language, the corpus outgrowing the budget), each with the option it would lead to.
10. Acceptance criteria: three to five, each with a threshold and how it is measured before launch.
11. ADR draft in Nygard's format as a code block. Offer to write it into the repo; write only after
    the yes.
12. Write the page JSON, with `facts`, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page before you write.

Sections in this order: The brief (kv: users, job, volume, constraints, with sources), Assumptions
(list, each with the decision it drives; omit when none), Split of the work (graph: requests on
the left, steps in the middle, model, systems and people on the right), Documents (stats, when
given), Decision (a `decision` block: every rung of the ladder as an option, factors as columns,
each eliminated option with its rule or factor), Why this one (text: the binding constraint), What
would change it (list), Acceptance criteria (table), ADR draft (code), Open questions.
Stats on top: requests per day, documents (tokens), options left after the hard rules, the chosen
rung. The verdict says the pattern and the binding constraint in two sentences.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/ai-pattern-<YYYY-MM-DD>.*`. Write the
page in the language of the request; Serbian pages in Latin script.

## Reads

- the brief, the documents folder and the repository, read-only

## Writes

- the page and its JSON, outside the repo; the ADR file only after the yes

## Never

- Never proposes an agent where a workflow passes, and never multi-agent without independent
  subtasks.
- Never quotes a price, a model version or a context window without its date and source; leave
  prices to the `ai-stack` skill.
- Never sends the brief or the documents anywhere: no web lookups, no uploads.
