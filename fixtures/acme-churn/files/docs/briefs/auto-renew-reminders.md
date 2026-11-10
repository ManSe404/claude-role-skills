# Brief: reminders for annual plans about to lapse

Customer care asked for "a model that predicts which annual-plan customers will not renew", so
someone can send them a reminder email 30 days before the term ends.

An annual plan renews by itself unless the customer has switched off automatic renewal. Last year,
of 910 annual-plan customers with automatic renewal switched off at 30 days before the term end, 856
did not renew; of those with it still on, 3 in 1,000 did not renew. Care want to mail the first group,
and can do so from the customer database with no new system.

What an error costs: an email to someone who would have renewed anyway costs 0.05 EUR. Missing one
costs about 8 EUR: a 10 percent chance the reminder changes their mind on an 80 EUR plan. Around
9,000 annual-plan renewals come up each year; about 900 of them have automatic renewal switched off at that
point. Our smallest model project is estimated at 60,000 EUR a year to build and keep running. Care's own bar
is to find at least 90 percent of those who will not renew.
