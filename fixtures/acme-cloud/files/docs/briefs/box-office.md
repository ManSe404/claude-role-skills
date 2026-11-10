# The box office

A small theatre company wants to sell its own tickets online instead of through a reseller.

## The facts

- 2 engineers build and run it, in one team. There are no platform engineers.
- It is one web application in .NET, with a page for each show and a checkout.
- Work arrives as web requests. There are no background jobs longer than a few seconds, and no events.
- Peak load is about 20 requests a second when a popular show goes on sale.
- The data is about 30 GB of relational data: shows, seats, orders. It grows slowly.
- Customers are in the EU and the data must stay in the EU.
- An hour of downtime during a sale is annoying but acceptable. Daily backups are enough.
- The budget is at most 200 USD a month.

## What we need

A recommendation for where this should run and what it would cost each month, and the reasons for it.
