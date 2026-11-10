---
name: cloud-design
description: Use before building or moving a system to the cloud, when a brief arrives or a platform is being picked, to decide what it should run on - a managed app platform, serverless containers, functions, Kubernetes or virtual machines, plus the data, network, region and availability - by eliminating options against the brief, with up to two variants or two clouds compared and costed from each provider's price list, each price with its date and source, and an ADR draft.
argument-hint: "[brief file or text] [saved price table]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/cloud-design/scripts/guard.py" ] && exec python3 "$d/skills/cloud-design/scripts/guard.py" pre cloud-design; done; true'
---

# Cloud design

The job: decide what cloud infrastructure a brief needs before anyone builds it, and what it costs. Start from the
option with the fewest moving parts and climb only when the one below fails a named requirement. It writes nothing but
the page; the ADR goes into a repository only after the yes. For the shape of the software use `arch-style`; for a data
platform use `data-platform`.

Input: a brief (a file or text), optionally a saved price table. Default: ask for the brief.

## Steps

1. Read [references/ladders.md](references/ladders.md): the ladders, what each option costs a team, the order of
   elimination and the ADR format. Read `references/cloud/<provider>.md` for each provider asked for.
2. Frame: the load and how it varies, what the team can run, the data, what must be private, what must survive what,
   where the data may live, and the budget. Write each one with where it came from in the brief.
3. Ask what flips the decision. If facts from the table in ladders.md are open, ask for the two to four that matter
   most, in plain words, and wait. If the user says go on, assume, and put every assumption on the page next to the
   decision it drives.
4. Hard rules: write the facts as JSON in your scratchpad and run
   `python3 "${CLAUDE_SKILL_DIR}/scripts/cloud_rules.py" FACTS.json` (`--facts` lists them). Every eliminated option
   keeps the rule that eliminated it. Never overrule a rule; fix the fact.
5. Weigh what is still open on each ladder in the order: can this team run it, what it has to learn, how it fails,
   cost. The factor that separates the chosen option from the next one up is the binding constraint. Name it.
6. Choose the lowest open option that passes on each ladder. Climb above `lowest_open` only for a reason you can name
   from the brief. The choice is neutral: it does not change with the cloud. Map it to real services with the provider
   file, once for each cloud, and check its limits there.
7. Variants: at most two, each on a page of its own only if a real choice is left. Two clouds are two variants of one
   decision: only when the user asks and a provider file exists for each. When a limit makes one cloud's service fail
   the requirement, say so; do not move that cloud to another option silently.
8. Bill of materials: one item per thing that costs money, with a `variant` and a `cloud`, quantities worked out once
   from the brief and used for every variant, and the fields each provider file gives. Run
   `python3 "${CLAUDE_SKILL_DIR}/scripts/cloud_prices.py" BOM.json --prices TABLE.json` (repeat `--prices` for each
   cloud's table), or `--online` only after the user's yes. Fix every `not_priced` item, or say on the page why it
   stays; an item a cloud has no equivalent for is said so, not left out silently.
9. What would change the decision: three to five conditions, each with the option it would lead to.
10. Acceptance criteria: three to five, each with a threshold and how it is measured before launch.
11. ADR draft in Nygard's format as a code block. Offer to write it into the repo; write only after the yes.
12. Write the page JSON, with `facts` (costs with date, source, `cloud` and `variant`, regions, decisions, assumptions, open), render it,
    and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format, including `nested`, `reach` and
`facts`, and [references/example.json](references/example.json) for a filled page.

Sections in this order: The brief (kv, with sources), Assumptions (list, each with the decision it drives; omit when
none), Decision (a `decision` block per ladder: every option, factors as columns, each eliminated option with its rule
or factor), Why this one (text: the binding constraint; show the thresholds the rules used), The design (a `nested`
block of the chosen variant, with `reach` from the internet; one level per variant when there are two, and with two
clouds one level per cloud), Monthly cost (table per variant: item, service and SKU, quantity, unit price, monthly, as
of, source; a total per cloud; with two clouds also a side-by-side table: what, each cloud's service, each cloud's
monthly, the difference),
What would change it (list), Acceptance criteria (table), ADR draft (code), Open questions. Stats on top: options left
after the hard rules, the chosen compute, monthly cost per variant, price date. The verdict says the option and the
binding constraint in two sentences.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both files in
`${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/cloud-design-<YYYY-MM-DD>.*`. Write the page in the language of the
request; Serbian pages in Latin script.

## Reads

- the brief and any saved price table, read-only

## Writes

- the page and its JSON, outside the repository; the ADR file only after the yes

## Never

- Never proposes Kubernetes where a managed platform or serverless containers pass, and never a second region
  without a requirement that names it.
- Never quotes a price without its date and source. The price comes from `cloud_prices.py`, never from memory.
- Never writes production infrastructure code and never deploys. Never goes online without a yes.
