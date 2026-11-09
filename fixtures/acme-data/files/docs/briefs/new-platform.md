# Brief: the next data platform for Acme Foods

From: Head of Data, Acme Foods
Date: 19 October 2026

Our reporting grew by hand around the store sales figures. It no longer covers what the business asks for, so we
want one platform for all of Acme Foods for the coming years.

## Sources

We have 14 sources: the ERP, the CRM, web events from the online shop, shelf sensors in the stores, supplier PDFs,
the loyalty app, the till systems, the delivery partner's files, shelf camera photos, the HR roster, the store
energy meters, the price comparison feed, the returns desk and the budget spreadsheets.

Together this is 35 TB today, growing about 1 TB a month.

## Freshness

One stock feed from the shelf sensors must be under 2 minutes fresh, so that the ordering team sees an empty shelf
while it can still act. Everything else is daily: every other source can arrive once a day.

## Data science

Our data scientists are training a shelf-image model on raw photos from the store cameras. They need the original
images, not summaries of them.

## Rules

- EU-only residency: all data must stay in the EU, including backups.
- The CRM holds personal data: names, contact details and purchase history of our loyalty customers.

## People

- Six data engineers in one central team build and run everything. The business units have no engineers of their
  own and we do not plan to add any.
- 120 BI users read the reports across head office and the stores.
