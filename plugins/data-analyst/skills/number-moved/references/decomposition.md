# Reading a decomposition

## The effects

For a summed metric, with V the volume (units or orders), R the value and r = R / V per segment:

- **Volume:** the total volume changed, at last period's average value per unit. Every segment moved
  together.
- **Mix:** the share of a segment in the volume changed. Selling more of a cheap segment and less of an
  expensive one lowers the total even at the same volume and the same prices. A positive mix effect for
  a segment means its share moved in a way that raises the total, because its value per unit is above
  average; a segment losing share while below average also shows a positive mix.
- **Rate:** the value per unit inside a segment changed.
- **New and gone:** a segment that exists in only one period; its whole value is its effect.

The script computes them on exact fractions, so they add up to the change exactly. `adds_up` must be
true, and `rounding_residual` is the difference between the sum of the rounded effects and the rounded
change (zero or a cent or two).

For a ratio (`--ratio`: value per order, conversion, margin %) there is no volume effect: the change
of the ratio is mix plus rate.

## Which segment to choose

Run several segmentations (`--by product_line`, `--by channel`, `--by region`). The useful one
concentrates the change: a few drivers cover most of it, and the rest is small. If every segmentation
scatters the change, say that; there may be no single driver.

## Data problems come first

- **Late or missing rows.** `--loaded-at` and `--as-of` show what a report made at that moment could
  not have seen. A late day looks like a fall that is not real. Missing and thin days show up in
  `checks` without those flags.
- **Duplicates.** `duplicates_removed` shows what `--dedupe` took out.
- **Definition or scope change.** `git log` on the definition's file across the two periods; segments in
  `new` or `gone`, a filter added, a source swapped. A definition change inside the window means the two
  numbers were not computed the same way: the page says so before any decomposition.
- **Unequal periods.** September has 30 days and October 31. Say it; a per-day figure may be the better
  comparison.

The fake or doubtful part is taken out before the decomposition, and it is a named step in the
waterfall.

## What a decomposition cannot say

It says which segment's volume, share or value per unit moved, by how much. It does not say why. A rate
effect says the value per unit moved, not that someone changed a price: it can equally be discounts, a
different sub-mix inside the segment, or a data change. A mix effect says customers bought a different
mix, not why they did.

On the page, write what was measured and keep the "why" out of it, or tag a suggestion with [guess] and
say what would test it. "The premium line lost share; [guess] the autumn range launched late; check
the launch date against the daily sales of the line."
