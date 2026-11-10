# Claims platform for Acme Mutual

Acme Mutual is a home insurer in Slovenia and Austria. About 120 claims handlers settle 30,000 claims a
year from shared mailboxes and spreadsheets, and every claim letter is read by hand. We want one
platform for handling claims.

## What we want

- Claims handlers work in one web application: they see a claim, its documents and its history.
- An assistant reads the claim documents (letters, photos of damage, invoices) and drafts a summary and
  a proposed settlement for the handler. A handler reviews every draft before anything goes to a customer.
- Management gets monthly reporting over all claims: paid amounts, time to settle, fraud cases.

## Users

- 120 claims handlers and 15 managers.
- About 30,000 policyholders a year upload documents.

## Constraints

- Personal data (claim documents, customer contacts, health details after an injury) must stay in the EU.
  This is not negotiable.
- Budget: EUR 6,000 a month in total for the running cost, everything included.
- Team: 5 engineers. There is no platform team and none is planned.
- Handlers sign in with the insurer's existing single sign-on.
- Every AI draft and the handler's decision on it must be kept for seven years for the auditors.
- Live before 1 April 2027.

## What we do not know yet

- Whether fraud reporting has to be close to real time or once a month is enough.
- Which of the two countries goes live first.
