# Plan: pack `solutions-architect`

Status: Stefan asked for it on 2026-11-10, as step 4 of [architect-packs.md](architect-packs.md). The
choices made without him are at the end.

## Goal

A small pack that sits on top of the four specialist packs and owns the whole. A real project crosses
specialties, and without an owner of the whole, specialist pages contradict each other unnoticed:
`ai-stack` puts the model in one region and `cloud-design` the data in another; each page has its
own cost total and nothing adds them up. Joining those pages and naming the conflicts is this pack's
only job.

Out of scope, on purpose:
- deciding one area: `ai-pattern`, `ai-stack`, `data-platform`, `arch-style`, `cloud-design`;
- drawing or reviewing one area, and any number a specialist computed: those stay on the specialist's
  page and are read from its `facts`;
- running the specialists: the brief writes the calls, the user runs them.

## Skills

### 1. `solution-brief`: frame it once, send the right specialists

Reads a client brief that may span several areas, before any specialist runs. Frames it once: goals,
users, constraints, what cannot be negotiated, budget, regions and where data may go, what is
unknown. Decides which specialists are needed and in which order, and says why any is not needed: a
small brief may need only one, and the page says so. Writes the exact skill calls to run next, each
with the shared assumptions it must use, so the specialists start from the same facts. `facts`
carries the shared regions, data rules, budget, assumptions and the list of specialists.

Never: runs a specialist itself, decides what one of them decides, invents a budget or a region the
brief does not state (it says it is unknown).

### 2. `solution-blueprint`: join the pages, name what contradicts

Reads the page JSON files in the project's pages folder, runs `join_facts.py`, reads every conflict
and decides what is real. Writes one page: the whole solution as one `nested` drawing, one decision
list with where each came from, one cost summary per cloud or variant with dates and sources, the
conflicts as `findings` with which page says what and what to change, what no specialist covered,
open questions, and what to do first.

Never: recomputes a specialist's number, silently resolves a conflict (it names the side it recommends
and why, and a person decides), adds costs across currencies, converts a currency.

## Script

Standard library, read-only, JSON on stdout.

| script | skill | what it does |
|---|---|---|
| `join_facts.py` | solution-blueprint | Reads page JSON files or a folder. Lists what was read, what is missing and what has no `facts`. Merges components, regions, data rules, decisions, assumptions and open questions, each with its source page. Groups costs per currency, then per cloud and variant, never across currencies. Lists `conflicts`, each with type, pages and values: a place to read, not a verdict. Thresholds are named and printed. |

Conflict types: `region_forbidden`, `regions_disagree`, `decision_differs`, `stale_cost`,
`mixed_currencies`, `over_budget`, `budget_other_currency`, `budgets_differ`, `component_technology`,
`assumption_numbers`. A later run of the blueprint is skipped, not joined, and an older page of the same
skill is reported as superseded so old and new do not conflict with each other.

## Facts: what is added

All optional, so every page written so far stays valid, and only what the join needs:
`budget` and `specialists` on the shared facts, `region` on a component, `cloud` and `variant` on a
cost. `shared/render_page.py` checks their shape.

## Fixture: `fixtures/acme-solution/` (all fictional)

Acme Mutual, a home insurer: one client brief (`docs/briefs/claims-platform.md`), a `pages/` set of
hand-written specialist page JSON files that validate against the renderer (`ai-pattern`, `ai-stack`,
`data-platform`, `arch-style`, `cloud-design`), and a small second brief (`docs/briefs/room-booking.md`)
that needs only one specialist.

Planted in the pages (`PLANTED_CONFLICTS` in `tests/test_fixture_acme_solution.py`):
1. the model endpoint and the search index in a US region while the data rule says EU only;
2. the backup store in a US region;
3. regions that disagree across the pages;
4. the same decision title with different choices;
5. prices dated more than 90 days back;
6. costs in USD and EUR;
7. a total over the budget;
8. the same store as PostgreSQL on one page and Azure SQL on another;
9. two team sizes;
10. a USD total that cannot be compared with the EUR budget.

Planted in the brief: requirements no page covers (`PLANTED_GAPS`).

## Evals

`brief-routes-to-specialists`, `brief-routes-to-one`, `blueprint-finds-conflicts`. Each with a
`skill-fired` grader. Run only when Stefan asks.

## Order

M1 facts fields and tests. M2 script and tests. M3 fixture and tests. M4 skills, plugin manifest and
marketplace. M5 install test in a throwaway config. M6 evals. M7 two real runs, checked by hand,
copied as the examples. M8 README, CLAUDE.md, role starter. Green at the end.

## Choices made without Stefan

1. Names: `solutions-architect`; `solution-brief`, `solution-blueprint`; the script `join_facts.py`.
2. `STALE_COST_DAYS = 90`. Prices older than a quarter are treated as worth another look. Override with
   `--stale-days`.
3. Costs in a total: if a page states a line with "total" in its name, that line stands for the page,
   otherwise the lines are added; lines with no cloud or variant and more than one option on the page
   are not added. Pages are added per cloud and variant only inside one currency, and the page says
   which pages were added so a reader can check nothing was priced twice.
4. Budgets are compared only in their own currency. Totals in other currencies are listed, not converted.
5. A data rule is read as a geographic restriction when it names an area and says "only", "stay",
   "must be in", "not leave" or similar. Anything else is left for Claude to read.
6. Regions are put into areas by words in their names (`europe`, `eu`, `us`, `asia` and so on), so the
   script holds no provider's region table and needs no change for a new cloud. A name it cannot place
   is listed as unplaced, never assumed to be fine.
7. Team size and a few other numbers are the only assumptions compared mechanically. Everything else
   goes to Claude to read.

## What the install test showed

`plugin.json` lists the four specialists as `dependencies`. On 2026-11-10, in a throwaway `CLAUDE_CONFIG_DIR`,
`claude plugin marketplace add` then `claude plugin install solutions-architect@claude-role-skills` installed all
five, and `claude plugin list` showed each enabled. `--plugin-dir` is stricter: pointing it at this pack alone
leaves the dependencies unsatisfied and Claude Code drops the pack, so a local run must pass all five folders.
