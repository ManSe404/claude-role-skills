---
name: arch-review
description: Use before a major change, when you take over a codebase, or when a system has become hard to change, to review its software structure with measurements - cycles between modules, layer breaks, dumping grounds, files that always change together, hot spots, shared tables, synchronous loops between services, code only one person knows - with file:line findings and what to fix first.
argument-hint: "[repository] [layers, innermost first]"
---

# Architecture review

The job: find what makes a system's structure hard to change, prove each finding with a number or
file:line, and say what to fix first. It changes nothing. For one planned change use `impact`; for
a bug use `bug-hunt`; for an AI solution use `ai-review`; for a data platform use `data-review`.

Input: a repository, optionally its layers from the innermost out. Default: the current repository.

## Steps

1. Read [references/smells.md](references/smells.md): each problem, how to confirm it and how to fix it.
2. Measure: `python3 "${CLAUDE_SKILL_DIR}/scripts/code_graph.py" REPO --git` (add
   `--layers domain,application,infrastructure,api` to name them) and
   `python3 "${CLAUDE_SKILL_DIR}/scripts/containers.py" REPO`, output to your scratchpad.
3. Confirm every hit by reading it. A number shows where to look; the finding is what you read there.
4. Walk what a script cannot see: boundaries around layers instead of business areas, a shared
   library that carries business rules, failure handling between services, and two or three quality
   scenarios that matter here ("a release of billing with shipments unchanged").
5. Findings: severity by what it costs the next change, file:line, the number, the fix, and what
   makes the fix safe. A hot spot or a one-person module is a risk to manage, not a defect.
6. Order: what blocks everything else first, then what grows worse with time, then the rest. Say
   what you would leave alone.
7. Write the page JSON, with `facts`, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: Findings (a `findings` block, high first), Where they sit (a `nested` block with
the problem spots flagged, or a `graph` of the modules), Measurements (tables: modules by fan-in, fan-out
and instability; hidden coupling; hot spots; owners), Quality scenarios (table: scenario, what happens
today, what stops it), Order of the fixes (list), What to leave alone (list), What this review did not
cover (list). Stats on top: modules, cycles, layer breaks, hidden couplings. The verdict says in two
sentences whether this structure can take the next change, and what it most needs.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/arch-review-<YYYY-MM-DD>.*`. Write the
page in the language of the request; Serbian pages in Latin script.

## Reads

- the repository and its git history, read-only

## Writes

- the page and its JSON, outside the repo

## Never

- Never changes a file.
- Never reports a finding it did not read in the code; a number alone is a place to look.
- Never judges a person: authors appear only to show where knowledge is concentrated. Never shows a
  secret or opens a `.env` file.
