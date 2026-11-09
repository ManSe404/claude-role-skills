# Modelling

## Approaches, simplest first

| Approach | Fits when | Climb past it when |
|---|---|---|
| One wide table | one process, one consumer, few attributes | several facts must share dimensions |
| Star schema | analytics on stable processes, BI tools | several sources disagree about one entity, or requirements change faster than the model |
| 3NF | a source of record, master data, many writers | analysts need it without many joins: put a star on top |
| Data Vault | many sources, full audit, sources that change often | (top: it costs many joins, and consumers still need marts on top) |

A climb needs a reason from the brief or the data. "Best practice" is not a reason.

## Grain

Say it as one sentence: "one row per order line". Decide it before the columns.

- Mixed grain in one table is a defect: order totals next to order lines double-count.
- Check it where there is data: `data_profile.py FOLDER --grain TABLE K1,K2`.
- Facts at different grains are different tables.

## Keys

- **Business key:** what the business calls the thing. **Surrogate key:** the warehouse's own.
- Two sources for one entity need a mapping; say which source wins for which attribute.
- `almost_keys` in the profile are duplicates hiding in a key. Name them, count them, decide.
- A join on a column that is not unique on the far side multiplies rows. `overlaps` shows by how much.

## History

| Type | Meaning | Use for |
|---|---|---|
| Overwrite | keep the latest only | corrections; nothing past depends on it |
| New row | a row per version with valid dates | attributes that past facts must be read against: price, segment, region |
| Snapshot | the whole state per period | stock, balances |

An amount computed at load from a current price is wrong for every past row: store the price on the fact.

## Personal data

Class per column: direct (name, e-mail, phone, national ID, IBAN), indirect (birth date, postcode,
device), none. Each personal column gets a decision in `mask`: dropped at the cleaned layer, hashed
for joining, or kept with who may read it and why. Join on a hash or a surrogate, never on an e-mail.

## Types

Money is `decimal`, never float. Timestamps state their zone. IDs with leading zeros stay text.
