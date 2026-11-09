# What goes wrong in data platforms

`family` is the name in the output of `sql_inventory.py --checks`. A family is a place to read.

| Failure | Family | Confirm by | Fix |
|---|---|---|---|
| A join multiplies rows | `fanout_candidate` | is the join column unique on the far side? `overlaps` shows `multiplies_by` | join on the real key, or aggregate the far side first |
| A load cannot be rerun | `rerun_unsafe` | run it twice in your head: does the day double? | delete the window first, or MERGE, in one transaction |
| A layer is skipped | `layer_skip` | does a report or export read raw or staging? | serve it from the last layer |
| Personal data served unmasked | `personal_served` | who reads this column, and may they? | drop it, hash it, or restrict and record why |
| Money as float | `float_money` | the column's type in DDL | `decimal(p,s)` and a migration |
| History overwritten | `overwrite_history` | do past facts read this attribute today? | new row with valid dates, or store the value on the fact |
| Keys without tests | `no_key_tests` | is there a `unique` and `not_null` on the key? | add them on every fact and dimension key |
| Dynamic SQL | `dynamic_sql` | is a value concatenated into it? can a caller set it? | parameters, or an allow-list of identifiers |
| Wide selects into modelled layers | `select_star` | does a new source column change the table? | name the columns |

## What a script cannot see

- **Mixed grain:** a table that holds order totals and order lines. Read the fact's select and say
  its grain as one sentence. If you cannot, that is the finding.
- **Amounts computed from current values:** a past sale priced with today's list price.
- **Nobody owns it:** no owner, no contact for a source, no one who gets the failed-load alert.
- **Silent freshness:** nothing notices when a source stops arriving.
- **Consumers outside the repository:** a dashboard reading a table this repo calls unused.
- **Time zones:** timestamps with no zone, joined across systems.
- **Keys mapped by hope:** two sources joined on a column that only looks the same.

## Severity

- **High:** numbers are wrong today, or personal data reaches someone who should not have it, or a
  caller can run their own SQL.
- **Medium:** it will go wrong on the next rerun, schema change or new consumer.
- **Low:** it makes the platform harder to change, and is wrong in no number today.
