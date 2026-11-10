# Checks for a new source

Each problem, how to confirm it, and how to rate it. `source_format.py` names the places to read and
counts them; `data_profile.py` adds types, keys and personal columns. A hit is a place to read: confirm it
in the file and in the vendor's document before it becomes a finding.

**Delimiter, encoding, quoting.** A file written with another delimiter than the others or than the
document says, a file that is not UTF-8, a byte order mark, values that hold the delimiter and arrive
quoted, rows with more or fewer fields than the header. Confirm: the file's `delimiter`, `encoding`,
`quoted_fields`, `ragged_rows`; the header line is line 1 of the file. Rate high when the loader would
split or decode the file wrong (a loader that assumes a comma reads a semicolon file as one column).

**Decimal separator and thousands.** `451.226,00` is a number with a point between thousands and a decimal
comma; a cast that expects `451226.00` rejects it or, worse, reads `451.226` as four hundred and fifty-one.
Confirm: `numbers` per column (`decimal_point`, `decimal_comma`, `thousands_separator`) and the document's
claim. Rate high: it rejects a load or changes amounts by a factor of a thousand.

**Date formats.** Two formats in one column (`2021-01-07` and `07.01.2021`), or a format the document does
not promise. Confirm: `date_formats` per column. Rate high when the loader parses one format only (the
other rows fail or, with day and month swapped, load wrong), medium when it only breaks sorting.

**No value written in several ways.** Empty, `NULL`, `N/A`, `-` in one column: a loader that treats only
empty as null keeps the words as text. Confirm: `null_tokens`. Rate medium; low when the column is free
text nobody filters on.

**Placeholders.** `9999-12-31` for "still open", `1900-01-01` for "unknown", `99999` as "no limit". A
placeholder where the document says the field is empty is a conflict; a placeholder date breaks every
"age" or "duration" computed from it. Confirm: `placeholders` per column, and `doc.conflicts` for
"placeholder where the document says empty". Rate medium; high when a metric is computed from the column.

**Duplicated keys.** The same id twice in a full extract. Read `key.columns_that_differ`: copies that
differ (another city, another limit) are two versions of one account and the loader must choose one;
identical copies are a plain double delivery. Confirm: `key.duplicated_keys`, `rows_in_duplicates`, and
Grep for one example id to cite its lines. Rate high when a join on the key would multiply rows downstream.

**Orphans.** Rows whose id points to no row of the parent file of the same delivery (a contact of an
account that is not in the accounts file). Confirm: `references` with `orphan_rows`. A parent file that
is incremental (only new rows each day) makes orphans normal: check the history first. Rate medium.

**Schema drift.** Columns added, removed or moved between deliveries, a delimiter or a number format that
changed. Confirm: `history.deliveries[].files` (`added`, `removed`, `moved`, `format_changes`). A change
the document announces (a column "delivered from release 2026.11") is still drift for the loader and for
history (earlier rows have no value), but it is not a broken promise: say both. Rate high for a removed
or renamed column a loader selects, medium for an added one.

**Deletes and gaps.** In a full extract, keys present yesterday and gone today are deletes nobody
announced (`keys_gone`); a delete marker column (`delete_marker`) tells the loader to remove rows. Weekdays
with no delivery folder, or with no rows in a date column that spans a few weeks, are gaps. An
incremental file (`incremental`: no key in common with the day before) has no `keys_gone` to read.

**Personal data.** Columns of e-mails, phones, IBANs, national ids, names, addresses, birth dates, found
by name or by value. Report per column the kind and how many rows hold a value; never a value. Say which
of them the platform needs for its purpose and which the document does not mention. Rate high when a
personal column has no stated purpose or would flow into a served table.

**The document against the data.** Columns it lists that did not arrive (`documented_not_delivered`),
columns that arrived and it does not list (`delivered_not_documented`), and its claims on delimiter,
decimal separator, date format and empty values (`doc.conflicts`). What the document allows is
consistent and goes in the consistent list, not in the findings: a column it calls optional that is empty
in every row, a code it lists (`doc.consistent`, "every value is documented"), a column it says arrives
from a given date.

## How a finding is written

`where` is file:line: the header is line 1, a row's line comes from Grep on its id, a document claim is
the line in the document. `evidence` is the count from the script and what the document says, for example
"`deal_value` holds 63 values with a decimal comma and a point between thousands (451.226,00); the vendor's
document, line 10, promises a decimal point". `fix` says what the contract must fix or what the loader must
do. Each finding also feeds one line of "What the contract must settle".
