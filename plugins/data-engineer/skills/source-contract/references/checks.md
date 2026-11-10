# Checks for a data contract

The clauses a contract with a source system needs, how to check each against the deliveries, and how
to rate a conflict. `contract_check.py check` counts them; `draft` proposes them from the data.

| Clause | It says | Checked against |
|---|---|---|
| Owner | who at the source answers for the data | the contract; empty or TBD is open |
| Change process | how a change is announced, how far ahead, who agrees | the contract; empty or TBD is open |
| Format | file type, delimiter, encoding, header, quoting | each delivered file |
| Schema | columns, types, formats, units, required, allowed values | each delivered file, every column |
| Key | the columns that identify a row, unique together | duplicated keys per delivery |
| Quality rules | conditions every delivery meets (`amount > 0`) | the rules the script reads; read the rest |
| Delivery | path, frequency, the time it must be there by, the time zone | the delivery log, every day |
| Consumers | the tables and jobs that read it | the loaders and the job definitions |

**Open clauses.** An owner or change process that is empty or TBD makes every other clause unenforceable:
nobody agreed to it and nobody is told before it changes. Confirm: `open_in_the_contract`, and the line in
the contract. Rate medium; say who should own it, from the source registry or the team that sends it.

**Columns missing or extra.** A contract column a delivery does not carry, or a delivered column the
contract does not list. Confirm: `missing_columns`, `extra_columns` per file, and `columns_over_time` for
when it changed. A column dropped in the latest delivery and present before is a change nobody announced:
rate high when a loader or a consumer selects it.

**Types, formats, units.** A value that breaks its column's type: an `integer` in cents that arrives as
`7110.00`, a decimal point that turns into a decimal comma from one day on (`9.99` then `9,99`), a date in
another format. Confirm: `column_problems.type` with `shapes` per delivery, and `breaking_shapes` over
time. Rate high: the loader rejects the delivery or loads amounts a hundred times too big or small.
Resolve it explicitly: change the contract to what the source sends, or ask the source to send what the
contract says, and name the day it changed.

**Allowed values and required columns.** Values outside an `allowed` list, required columns left empty.
A value the list allows is consistent even when it is rare: `allowed_values_seen` shows it with its rows.
Rate by what the loader does with it.

**Key.** Duplicated keys in a delivery break every merge. Confirm: `key.duplicated_keys`. Rate high.

**Quality rules.** The script tests a comparison with a number, a set of columns unique together and a
column that must be filled; it lists the rest as not checked. A rule the data breaks today is a conflict;
a rule that cannot be checked because the column's type is broken says so.

**Delivery window.** Arrivals after `deliver_by` in the contract's time zone. Confirm: `arrivals` with
`late`, `late_between`, `late_by_weekday` and `on_time_by_weekday`. A pattern matters more than a count:
late on every working day and on time only at weekends means the source's own job runs after the promised
time, and either the time or the job must move. Rate high when a scheduled job starts before the file is
due to arrive.

**The metadata document.** Columns the document lists that the contract leaves out and the other way
round, and its claims on delimiter, decimal separator, date format and delivery time against the
contract's. A document about other files of the same source (no section for this file) says nothing
about this one: do not compare its general claims.

## How a conflict is written

`where` holds both sides: the clause (contract file:line) and the evidence (a delivery file:line or the
delivery log line). `evidence` gives the numbers: "`deliver_by: 06:00`; the orders file arrived after 06:00
on 23 of 31 days, between 07:06 and 07:37, on every working day; on time only on the 8 weekend days".
`fix` names the resolution to agree and with whom. The proposed contract on the page carries every fix as
a changed clause with a comment.
