# gold.sales_daily

What each Acme Market franchise store bought from Acme Foods per day: orders, revenue and weight.

Grain: one row per store and day.
Built by: job `build_sales_daily`, from `silver.orders`, `ref.stores` and `silver.customers`.
Refreshed: daily, after the ERP load.
Questions: the data platform team.

## Who reads it

- Finance reads it each morning for the cash plan and to chase the franchise invoices.
- The BI sales board, the store operations app, the franchise portal and the regional managers' report refresh
  from it every hour.

## Columns

| column | meaning |
|---|---|
| `sales_date` | the day the store ordered |
| `store_id` | the store, as in `ref.stores` |
| `store_name` | the store's name |
| `currency` | the currency of the amounts: RSD for the Serbian stores, EUR for the Szeged stores |
| `orders` | number of orders |
| `order_lines` | number of order lines |
| `gross_revenue` | sum of the order line amounts |
| `cancelled_amount` | amount of the cancelled lines |
| `net_revenue` | gross revenue minus the cancelled lines; returns are not deducted, they are in `silver.returns` |
| `kg_eq` | kilogram equivalent: the weight of all lines in kilograms, pieces converted by product weight |
| `customer_id` | the franchisee's ERP customer id |
| `customer_email` | the franchisee's e-mail, for finance's follow-ups |
| `built_at` | when the table was built |

## Starter query

```sql
select store_id, sum(net_revenue) as net_revenue
from gold.sales_daily
where sales_date >= date '2026-10-01'
group by store_id
order by net_revenue desc;
```
