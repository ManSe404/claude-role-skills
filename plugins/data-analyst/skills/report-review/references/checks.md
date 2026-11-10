# Checks for a report

Each failure, how to confirm it, and how to get the corrected number. `report_check.py sql` names the
places to read; the `data` checks below and `measure.py` count them on the sample.

**Double counting.** A join to a table with several rows per key repeats the amounts, so a sum in a
report counts them twice. Confirm: the `fanout_candidate` hit, and the `fanout` check. Fix: pre-aggregate
the joined table or join on the full key.

```json
{"check": "fanout", "table": "orders", "join": "order_promotions", "key": "order_id", "value": "net_amount",
 "filters": [{"column": "status", "op": "=", "value": "completed"}],
 "window": {"column": "order_date", "from": "2026-10-01", "to": "2026-10-31"}}
```

**A filter that silently drops rows.** `col <> 'x'` and `NOT IN` drop NULL rows too. Confirm: the
`null_dropping_filter` hit shows the NULLs in that column of the sample. Corrected number: run the
measure with and without the filter (`measure.py`, its `filters` report how many rows a filter dropped).
Fix: `col IS DISTINCT FROM 'x'` or `(col <> 'x' OR col IS NULL)`, or say why NULL rows are out.

**Wrong denominator.** A rate whose bottom counts something other than the top's population. Confirm:
read the `ratio` hit, especially a conditional denominator, and compare with what the words say. Corrected
number: a `measure.py` ratio, numerator and denominator as measures.

**Mismatched or partial windows.** Two periods of unequal length, or one that stops short.
Confirm: `window_mismatch` and `partial_period`, and the `windows` check, which also gives the first common
number of days of each. Corrected number: the like-for-like sums or the full period.

```json
{"check": "windows", "table": "orders", "date": "order_date", "value": "net_amount",
 "filters": [{"column": "status", "op": "=", "value": "completed"}],
 "periods": [{"name": "September", "from": "2026-09-01", "to": "2026-09-24"},
             {"name": "October", "from": "2026-10-01", "to": "2026-10-31"}]}
```

**An average of averages.** A mean of group means weights every group the same. Confirm: the
`avg_of_avg` hit and the check. The corrected number is `true_average`.

```json
{"check": "avg_of_averages", "table": "orders", "group": "store_id", "value": "net_amount",
 "filters": [{"column": "channel", "op": "=", "value": "store"}, {"column": "status", "op": "=", "value": "completed"}],
 "window": {"column": "order_date", "from": "2026-10-01", "to": "2026-10-31"}}
```

**Small samples.** A rank or a rate that rests on a handful of rows. Confirm: the `small_groups`
check. Corrected statement: say the group is too small to rank, with its row count.

```json
{"check": "small_groups", "table": "orders", "group": "store_id", "min_rows": 30,
 "filters": [{"column": "channel", "op": "=", "value": "store"}, {"column": "status", "op": "=", "value": "completed"}],
 "window": {"column": "order_date", "from": "2026-10-01", "to": "2026-10-31"}}
```

**Simpson's reversal.** A group that wins overall loses inside every stratum, because the groups
differ in mix. Confirm: the `simpson` check: `reversal` true names the stratum column. Corrected
statement: the comparison per stratum, and what the overall number was really measuring.

```json
{"check": "simpson", "table": "sessions", "compare": "device", "numerator": "orders", "denominator": "sessions",
 "within": ["source"], "window": {"column": "day", "from": "2026-10-01", "to": "2026-10-31"}}
```

**Misleading charts.** An axis that does not start at zero on a bar chart, two scales, a chart that
compares a partial period, a percentage axis that hides the base. Confirm: `truncated_axis`, then read
the chart code. Say what the chart should show.

**Numbers that cannot be traced.** A number in the text with no query behind it, or that the
query does not produce: recount it and say so.

## How a finding is written

`where` is file:line. `evidence` is what the report says, what the code does and the number from the
script, with its corrected number: "Report: EUR 88,600.00. Sum after the join to order_promotions doubles
40 orders; correct sum on the sample: EUR 85,390.00 (the join adds EUR 3,210.00)". `fix` says the
change to the query or the sentence. A finding that changes a conclusion is high severity, and the
page says what the conclusion becomes.
