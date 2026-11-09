# Brief: support assistant v2

From: Jelena Radin, Head of Customer Service, Acme Devices (jelena.radin@example.com)
Date: 14 October 2026

## Why

The prototype (`acme-assist`) showed that customers are happy to ask a chat assistant, but it is
not ready for all our customers. It sometimes told customers that items were in stock when they
were not, and we had to apologise and cancel orders. We want a version we can put in front of
every customer in Serbia and the EU.

## Who asks, and how

- Customers ask via the web chat on the shop and by e-mail, in Serbian (Latin and Cyrillic) and
  English.
- About 3,000 questions per day, with a peak of about 400 per hour (Monday mornings and the days
  after a campaign).

## What they ask

| Share | Topic | Where the answer is today |
|-------|-------|---------------------------|
| ~55% | How-to and troubleshooting | The manuals, cleaning guides and error codes |
| ~25% | Order status and delivery | Our ERP, OrderDesk. It has a read-only REST API. An order's status changes within minutes |
| ~12% | Returns and warranty claims | The policies; every decision is made by our staff |
| ~8% | Other | Partnerships, invoices, press, complaints |

## The documents

- The `knowledge/` folder in this repo is a representative sample.
- The full library is 41 manuals, about 2,400 pages, in English and Serbian. Some manuals exist
  only as PDF.
- Manuals change monthly (new firmware, new parts). Policies change quarterly.

## Rules we cannot bend

- A wrong answer about warranty or returns is expensive. Consumer protection law applies in Serbia
  and in the EU, and a wrong promise ends in a refund we did not plan for.
- Never promise a return without an RMA number. Returns and refunds are approved only by our staff.
  6 support agents handle escalations.
- Customer data must stay in the EU. Acme already has an Azure tenant in West Europe.
- We have no GPU servers on-prem. A local model is acceptable for internal tools.

## Targets

- Latency: the first answer in the chat within 5 seconds.
- Budget: about €1,500 per month for models and hosting together.
- Success, three months after launch:
  - 50% of how-to questions answered without an agent (deflected)
  - zero wrong warranty or return promises
  - CSAT at least 4.2 out of 5

## What we expect back

A proposal for how to build it, what it costs per month at our volume, what can go wrong and how
we will know that it works before we switch it on for everyone.
