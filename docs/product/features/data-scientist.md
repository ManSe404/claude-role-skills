# Data scientist

For data scientists. The skills decide before modelling whether a rule, a score or a real model should be built, explore what in a table relates to the target, audit a training set for leakage, compare models from files of predictions so noise is called noise, and read A/B tests so a broken split or a win that does not survive correction cannot pass. Install it as `data-scientist@claude-role-skills`; the skills are called as `/data-scientist:<skill>`.

| Skill | Use it when | It writes |
|---|---|---|
| [ds-frame](../../../plugins/data-scientist/skills/ds-frame/SKILL.md) | someone asks for a predictive model, before anything is trained | the decision it changes, the exact target, whether a label comes in time and what each error costs; a ladder from a lookup rule to deep learning with options ruled out against the brief, the baseline that must be beaten and acceptance criteria |
| [ds-explore](../../../plugins/data-scientist/skills/ds-explore/SKILL.md) | one table and a yes/no target, before anyone splits it or trains anything | the target rate over time, labels that cannot be known yet, codes for unknown values, how strongly each feature relates to the target with an interval and a test corrected across features, shapes a linear term would miss, segments, redundant features, columns to check for leakage |
| [ds-dataset](../../../plugins/data-scientist/skills/ds-dataset/SKILL.md) | before trusting a predictive model built on a training set | target leakage, timestamps from the future, the same entity on both sides of a split, duplicates across splits, class balance, missingness that differs by class, drift (PSI), personal columns, each with what to change |
| [ds-evaluate](../../../plugins/data-scientist/skills/ds-evaluate/SKILL.md) | comparing trained models from a file of predictions | ROC-AUC, PR-AUC, log loss, Brier, MAE, RMSE, bias with seeded bootstrap intervals, a paired comparison against the baseline that calls noise noise, a calibration table, a threshold from the cost of each error and the worst slices |
| [ds-experiment](../../../plugins/data-scientist/skills/ds-experiment/SKILL.md) | an A/B test must be sized, or has finished | sample size and minimum detectable effect, or a read-out: sample ratio mismatch first, intervals, correction for several metrics, guardrails with margins, a warning about peeking and a call of ship, do not ship or inconclusive |

The statistics are implemented in the standard library and checked in the tests against values known independently.
LLM evaluation is not part of this pack; `ds-frame` sends an LLM problem to `ai-pattern`, and the general statistics
of the Anthropic `data` plugin stay where they are.

## More

- Each skill's scripts, shared copies and guard: [reference/skills.md](../../reference/skills.md#data-scientist).
- [roadmap/data-scientist.md](../../roadmap/data-scientist.md): the plan of the pack.
