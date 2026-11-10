# 2. One Data Service for all tables

Date: 2026-10-14

## Status

Accepted

## Context

In the counter app every module opens its own connection to the one database, and nobody knows which module depends on which column.
Schema changes broke invoicing twice this year.
The data team wants one place where every schema change is made and reviewed.

## Decision

All tables except the tariff table of the Pricing service live behind one Data Service.
Every service reads and writes its data through the REST API of the Data Service, and no service connects to a database itself.
The data team owns the Data Service: it designs the tables, makes every schema change and adds the queries the services ask for.

## Consequences

- One team reviews every change to stored data.
- A service that needs a new column or a new query waits for the next release of the Data Service.
- The Data Service is on the path of every request that reads or writes data.
