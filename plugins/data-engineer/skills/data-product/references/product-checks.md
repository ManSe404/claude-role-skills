# What a consumer guide must hold, and how to check it

`product_facts.py` gathers the facts; `data_profile.py` profiles the sample. Each part of the guide is checked
against the table itself, and each gap or conflict becomes a finding.

| Part of the guide | Where the truth is | The script's field | Finding when |
|---|---|---|---|
| Grain | the sample, the SQL's GROUP BY, the key the checks test | `sample.grain_tested`, `sample.smallest_unique_keys`, `definition.group_by`, `checks.on_the_table[].key_columns` | the documented key is not unique on the sample; the key check tests other columns than the document names |
| Columns | the SQL and the sample | `definition.columns`, `sample.columns`, `product_document.documented_not_in_table` and `in_table_not_documented` | a column is missing from one side; a documented value set (such as the currencies) does not match `sample.value_counts` |
| Metric definitions | every document, report and the SQL | `definitions[column]`, with `term_conflicts` as leads | two places define one metric differently; the SQL computes one of them, so the other readers are misled |
| Personal data | the sample and the SQL | `sample.personal_columns`, `definition.personal_by_name` | any personal column in a served table, unless the document names a legal reason and the readers are restricted |
| Consumers | the query log | `consumers.by_consumer` | a document's "who reads it" differs from the log; a heavy reader nobody knows about |
| Freshness | the job's SLA, the run records, the freshness check | `job.sla`, `freshness`, `checks.results` | the document promises no time; builds missed or late; the SLA in the job is not in the document |
| Quality | the checks on the table and on its sources | `checks.on_the_table`, `checks.on_its_sources`, `checks.test_cases` | a part of the table no check covers; a check never tried on bad data; a check that warns every day |
| Owner | the document | `product_document.names_an_owner`, `stated` | no person or team that answers for the content and agrees changes |
| Releases | the history of the SQL and the document | `history` | no release notes or change process; a breaking change without notice |
| Contract | contracts in the repository | `contract` | no contract of its own (a source contract that lists the table as a consumer does not count) |

## The grain, step by step

1. Write the documented grain as columns: "one row per store and day" is `store_id,sales_date`.
2. If `grain_tested` shows keys with more than one row, `columns_that_differ_inside_a_key` names the column
   that splits them (for instance a second currency for some stores). That column belongs in the grain.
3. The real grain is the smallest unique key that makes sense to a reader, usually the documented key plus
   that column. Confirm it against the SQL's GROUP BY and the key check.
4. Say what it does to consumers: a sum over the documented key mixes the rows that the split column keeps
   apart (amounts in two currencies added together). Starter queries group by the real grain.

## Definitions

- For each metric, list every definition with file:line: the product document, BI or report definitions,
  dbt descriptions, and the SQL expression.
- A conflict is two definitions that give different numbers on the same rows: one deducts returns and the
  other does not; one counts cancelled lines and the other does not. Wording alone is not a conflict.
- Say which definition the SQL computes; that is what every reader gets today. Who settles it is the owner
  of the metric; when the numbers themselves differ between teams, `metric-spec` writes the one definition.
- A documented column that matches its SQL is not a finding, even if the wording is short or unusual.
- Before saying the SQL does not do what a document promises (a conversion, a deduction), check what the source
  column already holds: a weight or an amount the source delivers already converted needs no step in the SQL.
  Divide it by the quantity on a source file, or read the source's contract.

## Personal data in a served table

A column such as an e-mail, phone, IBAN or a person's name in a served table reaches every consumer and every
copy they make. Write: the column, the rows that carry it (count), the SQL line that brings it in, the readers.
The fix is to drop it from the served table, or serve it from a separate table with restricted access, and to
say whose purpose it served. Never print a value.

## Freshness

The document should promise a time ("built by 08:00 on working days"), the job should carry the same SLA, and a
freshness check should test it. Give the last good build, the days without one, and why (the run records'
reasons). A promise the document does not make cannot be relied on, even when the job meets it.

## Severity

- **High:** consumers get wrong or unsafe results today: a grain that splits rows the document says are one, two
  definitions of a metric in use, personal data served to everyone, the table not refreshed for days.
- **Medium:** a promise nobody makes or keeps: no owner, no SLA in the document, a check never tried on bad data.
- **Low:** gaps in the guide itself: no release notes, missing starter queries, columns documented loosely.
