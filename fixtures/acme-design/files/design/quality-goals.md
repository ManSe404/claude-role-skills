# Quality goals: Parcel booking v2

The design in `proposal.md` must meet these goals.
Each goal has an owner who decides whether a design meets it.

| Goal | Statement | Owner |
|---|---|---|
| Fast booking | A booking is confirmed in under 500 ms at p95. | Jelena Savkov |
| Availability and scale | The platform must be highly available and scale for peak season. | Bojan Ostojin |
| Tariff consistency | Quotes are eventually consistent with the tariff table, at most 15 minutes behind it. | Milan Tadin |
| Address check latency | Checking an address adds at most 50 ms of latency to a booking. | Jelena Savkov |
| Correct charges | A customer is never charged twice for one booking. | Ivana Kerac |
| Tracking latency | A carrier scan shows on the tracking page within 2 minutes. | Ivana Kerac |

## How the goals are measured

- Fast booking: from the moment the Booking service receives the booking request to the moment it sends the confirmation, over all bookings of a day.
- Tariff consistency: the commercial team accepted the 15 minutes on 2026-10-29, because tariffs change at most once a week.
- Address check latency: inside the Booking service, around the call to the Address Validator.
- Tracking latency: from the carrier's scan time to the status on the tracking page.

## Peak season

Peak season runs from mid-November to the New Year holidays.
