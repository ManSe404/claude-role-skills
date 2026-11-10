# Reading the evaluation

Every number has an interval because a test set is a sample. A model is compared to the baseline on
the same rows, because two models scored on different rows are not a comparison.

## Which metric

- ROC-AUC: the chance a random positive outranks a random negative. It does not need a threshold and is not
  moved by the class balance. PR-AUC (average precision): how well the top of the list is the positive
  class; prefer it when positives are rare. Tied scores count half, or as one group, as everywhere here.
- Log loss and the Brier score: how good the probabilities are, not only the ranking; lower is better. They are
  computed only for columns inside 0..1, and a model that ranks well can score badly here if its probabilities
  are off.
- Regression: MAE is the typical error, RMSE punishes large errors, and bias is mean prediction minus mean label:
  zero bias with a big MAE means errors cancel out, a sign to look at.
- `--primary` is the one metric the choice rests on, chosen before looking at the results.

## Reading the comparison

`comparisons` gives each model's `improvement` over the baseline, in that metric's own units, positive meaning
better, and a percentile bootstrap interval for it. Every model is resampled with the same rows, so the
difference is paired. Reading: "better" when the whole interval is above zero, "worse" when it is below,
and otherwise "inside the noise". Say so plainly and do not report the point difference as a win. A noisy
difference is not nothing: it says the sample cannot tell the two apart.

The bootstrap is `--resamples` draws with `--seed`. It handles the row or (with a repeated id) the customer;
it does not fix a test set that leaks, was picked carefully, or is unlike production. Comparing many models
against one baseline flatters the best one by selection: note it when there are more than a few.

## Calibration

A probability is calibrated if, of the rows given 0.3, about 30 in 100 are positive. The table has ten
equal-count bins, ties kept together, with a Wilson interval on each bin's observed rate. A bin is outside if its
mean prediction is not in that interval: the `reading` says miscalibrated when several are. `ece` is the
row-weighted mean gap between predicted and observed. A model can rank very well and be badly calibrated; the
fix is a calibration step on held-out data, not a new model, but until then its probabilities cannot be read as
probabilities.

## A threshold from the costs

For a decision made at a threshold, the threshold follows from what the errors cost. The script tries every
distinct score and takes the cheapest, ties going to the higher threshold. `break_even_probability` is
cost of a false positive divided by the sum of both costs: the right cut only if the probabilities are
calibrated. If a model is miscalibrated, its `cost_per_1000_at_break_even` is worse than its best,
and that is the price of using probabilities as they are.

The "best" threshold was picked on the same rows it is costed on, so it flatters. Quote
`out_of_sample_cost_per_1000` as the honest number: the threshold chosen on one half, costed on the other, and
the other way round. `act_on_nobody` and `act_on_everyone` are the two trivial policies a model must beat.

## Slices

A number for the whole file hides a slice where the model fails. The worst slices are ranked by the shortfall
against the whole file on the primary metric (AUC or MAE), with an interval. A slice needs at least 100 rows
and 10 of each class to be ranked at all. `clearly_worse` means the slice's whole interval is below the model's
value on the whole file. Many slices means some will look bad by chance: about one in twenty of
the intervals, so a single mild flag is a thing to check, not a finding. The fair question is also whether the
model is worse than the baseline on that slice.

## Limits

- The interval covers sampling noise only. It says nothing of time, drift or a changed population.
- A model picked after trying many variants on this same test set is overrated. Use a final holdout that
  was not used for selection.
