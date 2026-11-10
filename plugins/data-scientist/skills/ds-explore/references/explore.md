# Reading the exploration

Everything here is an association in one extract. A flag is a place to look, not a verdict: each problem ends as a
finding with what to do, or cleared with a reason on the page.

## The target over time

`periods` is the rate per month or week with a Wilson interval. `moves` is a chi-square test across the periods, on rows
whose label can already be known. A rate that moves means the older rows describe a different world: find what changed
(a price, a product, a definition of the label) before training across it.

`labels` needs `--horizon-days`. A churn label decided 60 days later cannot be known for the last 60 days of the file.
The script takes the last date in the file as the day of the extract, which may be wrong, so say so if the brief gives
another date. `looks_unfinished` compares those rows with the same length of time just before them. Those rows look like
good news and are not: drop them from training, because each one is labelled "no" only because the answer is not in yet.

## How strongly a feature relates to the target

`strength` is how well the feature alone orders the rows by the target (ROC-AUC, folded so 0.5 is none and 1.0 is
perfect). The script takes the best of three readings and names it in `via`: the rank of the values, an out-of-fold rate
per bin or category, or whether the value is present at all.

Because of the folding and the choice of the best of three, strength is always a little above 0.5, even for noise, and
so is its interval. An interval above 0.5 is not evidence. **`signal` is**: a test per feature, corrected by Holm across
all features. For a number there are two tests, one for a trend (Mann-Whitney) and one for any shape (chi-square over the
bins), so the smaller p-value is doubled first. A feature without `adjusted_p` has groups too small to test.

| strength | reading |
|---|---|
| 0.95 and up | treat as a leak until proven otherwise |
| 0.85 to 0.95 | suspiciously strong: read where it comes from |
| 0.70 to 0.85 | strong for one feature: check it is known at prediction time |
| 0.55 to 0.70 | a useful feature |
| below 0.55 | little on its own; it may still help in combination, which this does not test |

A weak feature here is not useless. This looks at one feature at a time, so it cannot see interactions.

## Shapes

- `rising` and `falling`: the rate moves one way with the value. A linear term is a fair start.
- `not monotone`: the rate changes direction, so a linear term misses it. Compare `binned_strength` with `rank_strength`:
  a large gap with a rank near 0.5 is a U or a hump. Read `bins`. Bin it, add a squared term or use trees.
- `flat`: nothing the tests support.

## Codes for unknown

`sentinels` are a spike at the very top, at least twice the next value, or the only negative value. They are taken out of
the distribution and shown as their own bin, so read that bin's rate: unknown often behaves differently from any real
value. Replace the code with a missing value and, if the rate differs, keep a flag for it. A cap at the top is not flagged
because it has no gap below it. A code in the middle of the range, such as 0 meaning unknown, cannot be seen from the
numbers: read the data dictionary.

## Segments

Each level against all the other rows, corrected across every level tested, at least 30 rows and 2 points apart. Levels
are numbered instead of named when the column's name suggests people, and they stay numbered on the page.

## Missing values

`carries_signal` means the rate differs between rows where the value is missing and where it is present, after correction.
Ask why it is missing and whether it will be missing in the same way at the moment of the prediction. A field filled in
only after the event is a leak, even when the values themselves say nothing.

## Redundant features

Pairs at 0.9 or above: Spearman for two numbers, Cramer's V for two categories, a correlation ratio on ranks for one of
each. Keep one, or know why you keep both: redundant columns make a linear model's coefficients unstable and split
importance between them in trees. A table over 20,000 rows is sampled and only the 60 strongest columns are compared;
`redundant_scope` says so.

## Check for leakage next

`leak_suspects` is a list of questions, not findings: unusually strong, filled for one class only, a name that suggests
an outcome, or dated after the prediction moment. Read where the column comes from. Everything left here after that goes
through `ds-dataset` once the split exists.

## What this does not tell you

- Relations between features and the target taken together: one feature at a time only.
- Whether a feature is known at prediction time: that takes the code and the brief.
- Cause: nothing here is an experiment.
- A numeric target: not covered.
- With several rows per entity, the intervals resample whole entities but the chi-square p-values treat rows as
  independent, so they are too small. Trust the interval first.
- Numeric codes such as product or postal codes are read as numbers. If the shape looks odd, exclude the column or treat
  it as a category.
