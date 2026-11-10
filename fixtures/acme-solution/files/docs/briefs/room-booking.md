# Room booking for the Acme Mutual offices

Our 40 office staff book meeting rooms on a shared spreadsheet and double bookings keep happening. We
want a small internal web page instead.

## The facts

- 2 engineers will build and run it, in one team.
- There is 1 business area: booking rooms.
- Everything is released together, every couple of weeks.
- The only personal data is staff names and e-mail addresses, already in the staff directory.
- It runs on our existing internal Kubernetes cluster. Hosting is decided and is not part of this request.
- It needs one PostgreSQL database and nothing else. No reporting beyond a monthly CSV export.
- No AI and no model of any kind.

## What we need

A recommendation for the shape of this small system, and the reasons for it.
