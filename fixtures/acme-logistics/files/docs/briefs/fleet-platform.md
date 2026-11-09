# The fleet platform

This is the next system of Acme Logistics, for its vehicle fleet.

## The facts

- 30 engineers will work on it in 4 product teams, plus 2 platform engineers.
- There are 5 business areas.
- Vehicle telemetry ingestion takes about 200 times the load of the rest.
- The teams ship on their own schedules.
- Route optimisation is in Python, while the rest is .NET.
- Several teams must react to the same vehicle events.
- No transaction spans two business areas.
- Load is steady day and night.
- Route computations run for up to 40 minutes.

## What we need

A recommendation for the shape of this system, and the reasons for it.
