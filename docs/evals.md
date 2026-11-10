# Eval results

Written by `python3 tools/eval_table.py` from `plugins/<pack>/evals/results/*/aggregate-result.json`.
A case passes a grader or not; **outcome** graders judge what was produced, **process** graders only
whether the skill fired (plain Claude cannot pass those, so they are not compared). Runs that ended in an
error are left out. "with skill" is the plugin loaded; "plain" is the ablation arm without it, when a run had one.
One run per case is a hint, not a result; the evals cost money and are run by hand.

## Latest full run per pack

| Pack | Version | Run (UTC) | Cases | Outcome, with skill | Outcome, plain | Skill fired | Cost |
|---|---|---|--:|---|---|---|--:|
| ai-architect | 0.1.0 | 2026-11-10 08:35 | 5 | 12 / 12 (100%) | — | 7 / 7 | $4.32 |
| cloud-architect | 0.1.0 | 2026-11-10 08:55 | 8 | 19 / 20 (95%) | — | 26 / 26 | $11.02 |
| data-analyst | 0.1.0 | 2026-11-10 08:46 | 5 | 15 / 15 (100%) | — | 10 / 10 | $3.53 |
| data-architect | 0.1.0 | 2026-11-10 08:39 | 5 | 12 / 12 (100%) | — | 11 / 11 | $4.97 |
| data-scientist | 0.1.0 | 2026-11-10 08:44 | 6 | 17 / 18 (94%) | — | 12 / 12 | $4.32 |
| software-architect | 0.1.0 | 2026-11-10 08:51 | 5 | 13 / 13 (100%) | — | 11 / 11 | $4.29 |
| software-engineering | 0.1.0 | 2026-11-10 08:31 | 5 | 9 / 10 (90%) | — | 6 / 6 | $3.17 |
| solutions-architect | 0.1.0 | 2026-11-10 09:20 | 3 | 6 / 6 (100%) | — | 4 / 4 | $1.75 |

## ai-architect

Run 2026-11-10 08:35 UTC, version 0.1.0, ablation `none`, $4.32.

| Case | Outcome, with skill | Outcome, plain | Missed (with skill) |
|---|---|---|---|
| architecture-page | 3 / 3 (100%) | — | — |
| pattern-does-not-overbuild | 2 / 2 (100%) | — | — |
| pattern-live-state | 3 / 3 (100%) | — | — |
| review-finds-planted | 3 / 3 (100%) | — | — |
| stack-cost-from-script | 1 / 1 (100%) | — | — |

## cloud-architect

Run 2026-11-10 08:55 UTC, version 0.1.0, ablation `none`, $11.02.

| Case | Outcome, with skill | Outcome, plain | Missed (with skill) |
|---|---|---|---|
| aws-map-from-code | 2 / 3 (67%) | — | map |
| aws-review-finds-planted | 3 / 3 (100%) | — | — |
| design-compares-clouds | 2 / 2 (100%) | — | — |
| design-does-not-overbuild | 2 / 2 (100%) | — | — |
| design-names-the-constraint | 2 / 2 (100%) | — | — |
| map-drift | 2 / 2 (100%) | — | — |
| map-from-code | 3 / 3 (100%) | — | — |
| review-finds-planted | 3 / 3 (100%) | — | — |

## data-analyst

Run 2026-11-10 08:46 UTC, version 0.1.0, ablation `none`, $3.53.

| Case | Outcome, with skill | Outcome, plain | Missed (with skill) |
|---|---|---|---|
| metric-spec-finds-conflict | 3 / 3 (100%) | — | — |
| moved-rules-out-late-data | 3 / 3 (100%) | — | — |
| moved-splits-mix-exactly | 3 / 3 (100%) | — | — |
| reconcile-accounts-for-gap | 3 / 3 (100%) | — | — |
| review-finds-planted | 3 / 3 (100%) | — | — |

## data-architect

Run 2026-11-10 08:39 UTC, version 0.1.0, ablation `none`, $4.97.

| Case | Outcome, with skill | Outcome, plain | Missed (with skill) |
|---|---|---|---|
| map-lineage-from-code | 3 / 3 (100%) | — | — |
| model-grain-and-keys | 2 / 2 (100%) | — | — |
| platform-does-not-overbuild | 2 / 2 (100%) | — | — |
| platform-names-the-constraint | 2 / 2 (100%) | — | — |
| review-finds-planted | 3 / 3 (100%) | — | — |

## data-scientist

Run 2026-11-10 08:44 UTC, version 0.1.0, ablation `none`, $4.32.

| Case | Outcome, with skill | Outcome, plain | Missed (with skill) |
|---|---|---|---|
| dataset-finds-the-leaks | 3 / 3 (100%) | — | — |
| evaluate-calls-noise-noise | 2 / 3 (67%) | — | numbers |
| experiment-reads-correctly | 3 / 3 (100%) | — | — |
| explore-finds-what-matters | 3 / 3 (100%) | — | — |
| frame-catches-overbuilding | 3 / 3 (100%) | — | — |
| frame-justifies-a-model | 3 / 3 (100%) | — | — |

## software-architect

Run 2026-11-10 08:51 UTC, version 0.1.0, ablation `none`, $4.29.

| Case | Outcome, with skill | Outcome, plain | Missed (with skill) |
|---|---|---|---|
| c4-from-code | 3 / 3 (100%) | — | — |
| evolve-safe-steps | 3 / 3 (100%) | — | — |
| review-finds-planted | 3 / 3 (100%) | — | — |
| style-does-not-overbuild | 2 / 2 (100%) | — | — |
| style-names-the-constraint | 2 / 2 (100%) | — | — |

## software-engineering

Run 2026-11-10 08:31 UTC, version 0.1.0, ablation `none`, $3.17.

| Case | Outcome, with skill | Outcome, plain | Missed (with skill) |
|---|---|---|---|
| dependency-audit-asks-before-going-online | 1 / 1 (100%) | — | — |
| impact-of-a-signature-change | 2 / 2 (100%) | — | — |
| map-unknown-repo | 2 / 3 (67%) | — | map |
| root-cause-of-the-failed-import | 2 / 2 (100%) | — | — |
| tests-to-write-first | 2 / 2 (100%) | — | — |

## solutions-architect

Run 2026-11-10 09:20 UTC, version 0.1.0, ablation `none`, $1.75.

| Case | Outcome, with skill | Outcome, plain | Missed (with skill) |
|---|---|---|---|
| blueprint-finds-conflicts | 2 / 2 (100%) | — | — |
| brief-routes-to-one | 2 / 2 (100%) | — | — |
| brief-routes-to-specialists | 2 / 2 (100%) | — | — |

## Every run

| Pack | Run (UTC) | Version | Ablation | Filter | Cases | Outcome, with skill | Cost |
|---|---|---|---|---|--:|---|--:|
| ai-architect | 2026-11-10 08:35 | 0.1.0 | none | — | 5 | 12 / 12 (100%) | $4.32 |
| ai-architect | 2026-11-10 11:04 | 0.2.0 | none | stack-cost-from-script | 1 | 1 / 1 (100%) | $0.87 |
| cloud-architect | 2026-11-10 08:55 | 0.1.0 | none | — | 8 | 19 / 20 (95%) | $11.02 |
| cloud-architect | 2026-11-10 09:16 | 0.1.0 | none | aws-map-from-code | 1 | 3 / 3 (100%) | $1.40 |
| cloud-architect | 2026-11-10 11:17 | 0.2.0 | none | design-compares-clouds | 1 | 2 / 2 (100%) | $1.88 |
| data-analyst | 2026-11-10 08:46 | 0.1.0 | none | — | 5 | 15 / 15 (100%) | $3.53 |
| data-analyst | 2026-11-10 11:10 | 0.2.0 | none | reconcile-accounts-for-gap | 1 | 3 / 3 (100%) | $0.77 |
| data-architect | 2026-11-10 08:39 | 0.1.0 | none | — | 5 | 12 / 12 (100%) | $4.97 |
| data-architect | 2026-11-10 11:06 | 0.2.0 | none | model-grain-and-keys | 1 | 2 / 2 (100%) | $1.32 |
| data-scientist | 2026-11-10 08:44 | 0.1.0 | none | — | 6 | 17 / 18 (94%) | $4.32 |
| data-scientist | 2026-11-10 09:11 | 0.1.0 | none | evaluate-calls-noise-noise | 1 | 3 / 3 (100%) | $0.83 |
| data-scientist | 2026-11-10 11:12 | 0.2.0 | none | dataset-finds-the-leaks | 1 | 3 / 3 (100%) | $0.67 |
| software-architect | 2026-11-10 08:51 | 0.1.0 | none | — | 5 | 13 / 13 (100%) | $4.29 |
| software-architect | 2026-11-10 11:14 | 0.2.0 | none | review-finds-planted | 1 | 3 / 3 (100%) | $1.01 |
| software-engineering | 2026-11-10 08:21 | 0.1.0 | none | — | 5 | 8 / 11 (73%) | $3.82 |
| software-engineering | 2026-11-10 08:31 | 0.1.0 | none | — | 5 | 9 / 10 (90%) | $3.17 |
| software-engineering | 2026-11-10 09:13 | 0.1.0 | none | map-unknown-repo | 1 | 3 / 3 (100%) | $0.90 |
| software-engineering | 2026-11-10 11:02 | 0.2.0 | none | root-cause-of-the-failed-import | 1 | 2 / 2 (100%) | $0.61 |
| solutions-architect | 2026-11-10 09:08 | 0.1.0 | none | — | 3 | 6 / 6 (100%) | $2.17 |
| solutions-architect | 2026-11-10 09:20 | 0.1.0 | none | — | 3 | 6 / 6 (100%) | $1.75 |
| solutions-architect | 2026-11-10 11:23 | 0.2.0 | none | blueprint-finds-conflicts | 1 | 2 / 2 (100%) | $0.80 |
