# What each bucket means, and how to narrow it down

| bucket | means | look at next |
|---|---|---|
| `only_in_a` / `only_in_b` | The key is nowhere in the other system | Slice by day or batch. Are these recent (not posted yet), or a type of row the other system never gets? |
| `filtered_a` / `filtered_b` | Only-in rows whose value in a `--filter-columns` column never reaches the other system | That column is a filter somewhere between the two systems: read the SQL or the interface between them |
| `duplicates_a` / `duplicates_b` | Second and later rows of a key inside the window | Look for a batch or a retried load; a job that ran twice |
| `time_zone_a` / `time_zone_b` | A row in one side's window whose twin is just outside it on the other side, a whole number of hours away | One clock is in UTC and the other in local time: the row falls on a different day near a month boundary. The two sides differ only by when the period ends |
| `timing_a` / `timing_b` | The same, but days away | Posting is later than the event: invoices, settlement, late loads |
| `rounding` | Amounts differ by less than the rounding unit | One system rounds per row; the sum of many small differences |
| `value_difference` | Same key, amounts differ by more than rounding | This is the unexplained part: the script cannot say why. A manual credit, a discount applied in one place, a currency conversion |

The gap is the sum of the buckets, exact. A bucket's amount is signed: positive when it makes A larger
than B. Time zone and timing have two sides: rows counted only in A's window (positive) and rows
counted only in B's window (negative); a period's end moves amounts between them, and only the net
stays in the gap.

## Narrowing further

- Slice each bucket's rows by whatever the data offers: day, batch, channel, status.
- A filter is a sentence about the data, not a column name: "staff orders never reach the ledger"
  needs the rows of `channel = staff` and none of them matched.
- Only the rows show a cause. Whether the ledger or the ERP is right is a question for the people who
  own them, unless a row or a definition says so.

## Before you reconcile, check

- Both numbers can be reproduced from the rows. If a number cannot, stop: the gap is unknown.
- The two numbers are for the same window and the same definition. If they are not, that is a
  finding of its own, and goes first.
