# ADR-0003: Tracking reads booking changes by polling

* Status: accepted
* Deciders: Bojan Ostojin, Ivana Kerac
* Date: 2026-10-14

## Context and problem statement

The Tracking service must learn about new bookings and about every status change of a shipment.
How does it get them?

## Considered options

* Subscribe to events on the message broker
* Poll the REST API of the Booking service

## Decision outcome

Chosen option: poll the REST API of the Booking service.
The Tracking service polls the REST API of the Booking service every minute, at `GET /bookings/changes?since=`.
From the changes it gets, the Tracking service updates `shipments.status`.

### Positive consequences

* The Tracking service does not depend on the event format or on a broker.
* Polling is easy to test and to replay after an outage.

### Negative consequences

* The tracking page can be up to a minute behind.
* The Booking service answers one more request every minute.
