# The ladder and the frame

The cost of a model is not training it: it is building a pipeline around it, serving it, monitoring
it and retraining it for as long as it runs. Each rung adds to that. Start at the bottom and climb only
when the rung below fails a requirement you can name.

## The rungs

| rung | what it is | enough when | moves up when |
|---|---|---|---|
| a lookup or a business rule | an `if` on a field, a threshold, a table by segment | the outcome follows a rule that can be written down and measured on history | the rule cannot reach the bar, and more conditions make it unmaintainable |
| a simple score | a few signals with weights a person set | there are no labels, or the score must be explainable to the people using it | labels exist: then a linear model gives the weights for free, from the data |
| a linear or logistic model | weights learned from labels | the relationship is roughly monotone, or the features are few and tested | interactions matter and a held-out test shows the linear model falls short of the bar |
| gradient-boosted trees | many shallow trees learned on labels | tabular data, interactions, a few hundred positive cases or more | almost never for tabular data; only unstructured input goes further |
| deep learning | neural networks | images, audio, sequences, raw signals | it is the end of the ladder |

Free text and conversation are not on this ladder: reading or writing language is an LLM question, and
that goes to `ai-pattern`.

## What the script reads, and how to get each fact

Answer in the words of the brief; a fact is either stated, measured or an assumption you label.

- `decision_named`: who does what differently depending on the prediction. "The dashboard would show it" is not
  a decision.
- `label_exists`, `label_delay_days`, `feedback_budget_days`: the outcome must exist in history, and it must
  arrive soon enough to matter. A label that takes a year cannot steer a monthly model. For a churn label the
  delay is the observation window.
- `signals_known_at_decision`: everything the prediction would use is known at the moment the decision is
  made. If a feature only exists after the outcome, it is a leak, not a signal (see `ds-dataset`).
- `rule_meets_bar`: measure the rule on history before saying this. Use `measure.py`: the rule as a filter on the
  history, a count of how many cases it fires on, and the precision and recall it gets. A rule that meets
  the bar ends the ladder: everything above it is overbuilding.
- `minority_rows`, `candidate_features`: the rules ban a model with under 10 positive cases per feature
  (linear) and under 500 positive cases (trees). These are rules of thumb: cut features or wait for more data.
- `decisions_per_year`, `base_rate`, the two costs, `learned_model_cost_per_year`: the economics. The ceiling is
  what a perfect model could save over the cheaper of the two trivial policies, per year. If that is below
  what running a model costs, a learned model cannot pay for itself no matter how good it is.

## The baseline that must be beaten

A model is only worth building if it beats the cheapest honest alternative. Name it with numbers:

- classification: the base rate as a score, the best of "act on everyone" and "act on nobody" at the stated
  costs, and the current rule if there is one;
- regression: the mean or median of the target from the training period;
- forecasting: the last value, or the value a year ago if the series has a yearly cycle;
- ranking: sorting by the one strongest signal.

Then write what beating it means, on what metric, measured how. "Better" with no number is not a criterion.

## Acceptance criteria

Three to five, each one a number and a way of measuring it before launch:

- a ranking or error metric with a floor, measured on a held-out period, not on a random row split;
- the cost per case at the chosen threshold against the baseline's;
- a calibration limit if the output is used as a probability;
- the worst acceptable slice;
- a data check that must pass first (the `ds-dataset` audit).

Use a threshold from the brief or the costs. If you assume one, write `[guess]` next to it.

## Before you climb

When a rung is open but below the option you want, the reason has to be a sentence the brief supports. These are
not reasons: "it is more accurate" (measure it first), "it is standard for this problem", "we have the data
for it", "the team knows gradient boosting".
