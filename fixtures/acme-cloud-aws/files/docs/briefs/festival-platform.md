# The festival platform

The next platform of Acme Tickets, for three festivals a year with very large ticket drops. The group now runs
on two clouds, one from each company. The new platform can go on either; compare them and price both.

## The facts

- 8 engineers build and run it, in one team, with 1 platform engineer.
- It is 6 services that already ship as container images. None of them needs the Kubernetes API, an
  operator or a daemon on every node, and none needs control of the operating system.
- Work arrives as web requests. Peak load is about 600 requests a second during a ticket drop, for about
  20 minutes. The rest of the year load is steady and small.
- Background work (emails, seat holds) takes a few seconds per message.
- The data is about 400 GB of relational data, plus exported files.
- All data stores must be reachable only on private addresses. Only the web tier faces the internet.
- The system must survive the loss of one availability zone. The loss of a whole region is an accepted risk.
- Customer data must stay in the EU.
- The budget is at most 5,000 USD a month.

## What we need

A recommendation for where this should run and what it would cost each month on each cloud, and the reasons for it.
