# BI metrics of the sales board

The sales board reads `gold.sales_daily` every hour. These are the definitions the board and its users rely on.

| metric | definition | column |
|---|---|---|
| Gross revenue | everything the stores ordered | `gold.sales_daily.gross_revenue` |
| Net revenue | gross revenue minus cancellations minus returns | `gold.sales_daily.net_revenue` |
| Orders | number of orders | `gold.sales_daily.orders` |
| Average order value | net revenue divided by orders | computed on the board |
| Tonnage | sum of the kilogram equivalent, in tonnes | `gold.sales_daily.kg_eq` / 1000 |

Amounts are shown in the store's currency; the board does not convert.
