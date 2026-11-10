# 1. Split parcel booking into services

Date: 2026-10-13

## Status

Accepted

## Context

The counter app books, prices, tracks and invoices parcels in one .NET deployable.
Four teams change it: booking, pricing, tracking and billing.
Every release waits for all four teams, and a change in invoicing can hold back a fix in booking.
Customers want to book on the web and in a mobile app, which the counter app cannot serve.

## Decision

We split parcel booking into the Booking service, the Pricing service, the Carrier Gateway, the Tracking service and the Billing service, each owned by one team.
The Web app and the Mobile app call the Booking service over REST.
The services keep their data in the Data Service (ADR-0002) and exchange events through a message broker (ADR-0004).

## Consequences

- Each team releases its service on its own schedule.
- Calls between services cross the network, so every call adds to the time a request takes.
- The platform team runs the services, the Data Service and the broker.
