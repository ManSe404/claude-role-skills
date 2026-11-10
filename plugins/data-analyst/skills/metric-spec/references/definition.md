# What a metric definition must say

Each field is a sentence someone can compute from, not a description.

- **Name and one sentence.** What the number means to the people who use it.
- **Grain.** What one unit counted is: one row per order, per order line, per customer per month.
  Say the column or key that makes it unique. If the data has several rows per unit, say what
  happens: "one row per `order_id`, the first by `loaded_at`".
- **Filters.** Every condition, written as a condition on columns, in the order they apply. Say what
  happens to rows with an empty value: a filter written `col <> 'x'` also drops those rows.
- **Formula.** The arithmetic on named columns: `sum(net_amount)`, `sum(a) / count(distinct b)`.
- **Time window.** Which date the row counts by (order date, shipping date, posting date), the time
  zone, whether a period is a calendar month or rolling 30 days, and when a period closes, meaning
  when late rows stop changing the number.
- **Currency.** The currency of the amount, which rate is used for others, and on which date.
- **Owner.** A team or a person who decides changes to this definition.
- **What it does not include.** The cases a reader might assume are in: staff orders, returns, tax,
  shipping. A definition without this field gets recomputed differently later.

## When definitions disagree

Every difference gets one choice and one sentence of reason. Reasons that count:

- which number the business actually acts on (close, invoice, target, payout);
- which definition matches the source system's meaning of the word (a sale is a completed order, a
  shipment is a shipped order);
- what the metric is compared with over time (keep the definition stable, or restate the history).

A difference nobody can decide from the data or the docs stays an open question with its owner. The
page states the proposed definition and what it would change, and the owner decides.

## What not to do

- Do not average definitions or take a compromise number; pick and say why.
- Do not say a definition is wrong because it gives a different number; say what it counts.
- Do not leave currency, time zone or grain unstated because "everyone knows".
