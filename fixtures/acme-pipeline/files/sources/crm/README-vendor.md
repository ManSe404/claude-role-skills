# Salaš CRM: daily export for Acme Foods

From Salaš Software, the vendor of the CRM. Questions about the export: support@example.org.

## Delivery

- Every day by 05:00, into the landing folder `crm/<YYYY-MM-DD>/`, one folder per day.
- Three files: `customers.csv` and `contacts.csv` are full extracts; `activities.csv` holds the activities of the
  previous day.
- Format of every file: CSV, UTF-8, comma-separated, a header line, a decimal point, dates as YYYY-MM-DD.

## customers.csv

| column | type | meaning |
|---|---|---|
| `customer_id` | text | the CRM account id, unique |
| `company_name` | text | the account's registered name |
| `tax_id` | text | PIB, 9 digits |
| `segment` | text | retail, horeca, franchise or prospect |
| `status` | code | A active, I inactive, X closed by credit control (kept for the history) |
| `city` | text | |
| `country` | text | ISO code |
| `credit_limit` | decimal | in RSD |
| `created_on` | date | when the account was opened |
| `closed_on` | date | when the account was closed; empty while it is open |
| `parent_customer_id` | text | optional: the head office of a chain account; empty for single accounts |
| `key_account_manager` | text | code of the Acme key account manager |

## contacts.csv

| column | type | meaning |
|---|---|---|
| `contact_id` | text | unique |
| `customer_id` | text | the account the person works for |
| `first_name` | text | |
| `last_name` | text | |
| `job_title` | text | as typed by the account manager; may be empty |
| `email` | text | |
| `phone` | text | |
| `iban` | text | for sole traders who receive the yearly bonus; empty otherwise |
| `consent_date` | date | when the person agreed to be contacted |
| `preferred_language` | code | sr, hu or en |

`contacts.csv` holds personal data of the customers' staff. Use it only for the account work it was collected for.

## activities.csv

| column | type | meaning |
|---|---|---|
| `activity_id` | text | unique |
| `customer_id` | text | |
| `contact_id` | text | empty when the activity was with the account, not a person |
| `activity_date` | date | |
| `type` | text | visit, call, offer or complaint |
| `channel` | text | field, phone, email or web; delivered from release 2026.11, 4 November 2026 |
| `subject` | text | |
| `deal_value` | decimal | the value of an offer, in RSD; empty for the other types |
| `owner` | text | code of the Acme employee who logged it |
