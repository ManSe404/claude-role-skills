# ADR-0004: Message broker

* Status: proposed
* Deciders: Bojan Ostojin, Ivana Kerac, Jelena Savkov
* Date: 2026-10-22

## Context and problem statement

The services publish `ShipmentBooked`, `CarrierScan` and `ShipmentDelivered` events, and the Tracking service and the Billing service consume them.
Acme has not run a message broker before.
Which broker should carry the events?

## Considered options

* RabbitMQ, run by the platform team on the cluster
* Apache Kafka, as a managed service of the hosting provider
* The queue service of the hosting provider

## Decision outcome

To be decided later, after the platform team has tried each option.
Until then the services publish through a small interface of their own, so the choice can be made late.

## Open questions

* Who is on call for the broker at night?
* Do we keep events for replay, and for how long?
