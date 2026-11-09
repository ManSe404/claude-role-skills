# Booking and invoicing for Acme Couriers

Acme Couriers, our sister company, wants an app for booking and invoicing.

## The facts

- 4 engineers will build and run it, in one team.
- There are 3 business areas: booking, dispatch and invoicing.
- Everything is released together once a week.
- The busiest part takes about twice the load of the rest.
- Load is steady during business hours.
- Everything runs on one runtime, .NET.
- A booking and its invoice must be saved in one transaction.
- There are no platform engineers.

## What we need

A recommendation for the shape of this system, and the reasons for it.
