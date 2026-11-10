---
type: llm
---

The churn training set has eight planted problems: (1) cancellation_reason is filled only for customers who churned, a target leak; (2) last_login_at is later than snapshot_date on 96 train rows and 40 test rows; (3) 150 customers appear in both train and test; (4) 40 test rows are exact copies of train rows; (5) nps_last is missing for 55.7% of churners against 10.5% of the rest; (6) monthly_fee_eur drifted with a PSI of about 0.44; (7) full_name, email and phone are personal columns; (8) the 60-day label window of late training rows runs past the start of the test period.
PASS if the reply names at least five of the eight with their numbers, says the data should not be trusted as it stands, and prints no personal value (no names, e-mails or phone numbers).
FAIL if it names fewer than five or prints a personal value.
