# Plan: process workflows on top of the skills

Status: proposed on 2026-11-11, Stefan's idea for the next step. Nothing is built; this page says what a
workflow is here, which ones are worth having first, three ways to run them, and what the skills need before
any of it.

## What a workflow is

A process that keeps coming back and needs several skills in order, where the output of one step feeds the next
and one place says whether the process is done. The skills stay single-job; a workflow is the recipe. A step
reads the previous step's page JSON (its `facts`, findings and tables), never its prose, so the hand-over is
checkable and the same recipe gives the same shape every time.

## The processes worth having first

| Workflow | Starts when | Skills, in order | What passes between them | Done when |
|---|---|---|---|---|
| take-over | a repository arrives | codebase-map → code-audit → dependency-audit → test-gap → docs-draft | the map's entry points and flows; the audit's findings rank the test gaps; everything into the onboarding draft | the four pages exist and validate, and docs-draft has written the onboarding guide |
| ship-a-change | a branch is ready | impact → change-review → bug-hunt (only when a test fails) → docs-draft (changelog, docs that mention what changed) | impact's affected list narrows the review; a failing test opens a hunt | change-review's verdict is ok and the documents it named are updated |
| incident | an alert fires | incident-triage → bug-hunt → change-review (the fix) → postmortem | the error signature and timeline; the fix branch; every page into the postmortem | the postmortem has owners and dates on every action |
| data incident | a load fails | pipeline-incident → source-contract (when the source changed) → data-quality (after the rerun) | the root cause and the weakness list; the contract conflicts; the tables held back | data-quality says the held-back tables are safe |
| new solution | a client brief arrives | solution-brief → the specialists it names (ai-pattern → ai-stack → ai-architecture; data-platform → data-model; arch-style → arch-c4; cloud-design) → solution-blueprint → the reviews (ai-review, arch-review, cloud-review, data-review) | `facts.specialists` from the brief; each specialist's `facts` into the blueprint; the blueprint's conflicts into the reviews | the blueprint has no real conflict open and each review is ok |
| platform month | once a month | data-quality → data-cost → data-product (for tables that gained consumers) | the tables and their checks; the spend per table; the consumers | the three pages are dated this month and their open lists are assigned |
| a model | someone asks for a prediction | ds-frame → ds-explore → ds-dataset → ds-evaluate → ds-experiment | the decision and baseline; the leakage columns; the chosen threshold; the experiment read-out | ds-experiment says ship, do not ship or inconclusive |

The specialists of a new solution are independent of each other, so that workflow runs them in parallel; the
others are chains.

## Three ways to run them

1. **A workflow skill per process**, in a `workflows` pack. A SKILL.md lists the steps, runs each skill in turn
   in the same session, hands over page paths, and ends in one page that joins them (as `solution-blueprint`
   does). Cheapest to build and works everywhere a skill works. One context for the whole process, so a long
   take-over hits the context limit, and nothing runs in parallel.
2. **Claude Code `Workflow` scripts**, one per process. Deterministic orchestration: one subagent per step with a
   schema for its result, steps in parallel where they are independent, resumable after a failure. Each agent
   starts fresh and knows only its prompt, so the script must give it the previous pages' paths and what to read
   from them. Fits the new solution and the take-over.
3. **Mission Control missions.** A `mission.toml` whose checks are the "done when" column: the page exists and
   validates, its verdict is ok, the tests it named exist. Participants work on branches, the checks run on every
   commit, a person finishes the mission. Works across sessions, days and people. Fits ship-a-change and the
   incident, where the work is commits on a branch.

Recommendation: build 2 for the new solution and the take-over, where parallel specialists and resumability pay
off at once, and use 3 as the "done" layer for ship-a-change and the incident. Keep 1 only for people without the
Workflow tool. Do not build a fourth runner: the pages' `facts`, the naming rule and the folder index already give
the hand-over.

## What the skills need before a workflow can use them

- **`facts` on every page a later step reads.** Today the decision and map skills write it; the engineering
  skills mostly do not. Add `facts` to codebase-map, code-audit, test-gap, incident-triage, bug-hunt and
  change-review: scope, the findings as `decisions` and `open`, the components touched.
- **Finding the latest page of a skill for a repository.** The naming rule and the index exist; a small
  `render_page.py --latest <skill> <folder>` that prints the newest JSON path saves every runner the same code.
- **Inputs named in the request.** A skill reads earlier pages when the request names them; its `Reads` section
  must say which pages it takes and what it uses from them. `solution-blueprint` already does; the others do not.
- **One fixture per process** with a planted problem that only the chain finds, and an eval that runs the chain.
  The acme fixtures cover the single skills; none covers a hand-over.
- **A cost line before the run.** A take-over of a mid-size repository is five skills, about 10 to 15 dollars on
  Opus by the evals so far. A runner should say the expected cost and the budget cap before it starts.

## Open questions

- Where the workflow definitions live: a `workflows` pack in this repository, or missions in Mission Control.
- Who says "done": the last check of the workflow, or a person after reading the last page.
- Whether a workflow may change code (ship-a-change and the incident do) or only write pages; the guard hooks
  ask for confirmation on every write today.
