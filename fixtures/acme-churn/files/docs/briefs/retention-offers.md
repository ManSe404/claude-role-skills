# Brief: who gets a retention offer

The retention team wants to spend the retention budget on the subscribers most likely to leave.

Each month a list goes to the team; each subscriber on it gets a 25 EUR credit. We have about 40,000
active subscribers and decide on all of them each month, so 480,000 decisions a year. Roughly 16 to 17
in 100 cancel within 60 days of a snapshot. We can only learn the outcome after those 60 days; the
team reviews the list every month, and a label that takes 60 days is acceptable, up to 90.

What an error costs: an offer to someone who would have stayed costs 25 EUR. Someone who cancels without an
offer costs about 90 EUR on average: the 300 EUR margin of a saved subscriber, with retention
offers saving about 30 percent of those who get one.

A rule of thumb the team tried: anyone with four or fewer logins in the last 30 days. On our extract it is
right about 4 times in 10, but it finds only about 1 in 5 of those who cancel. The team's bar for the list:
at least one in three of those who will cancel, with no more than 6 in 10 of the offers wasted.

The signals available are the 11 columns in `model/features.py`. We have 18 months of labelled snapshots, about
3,400 labelled rows and 580 churners in our extract. The offer list is built in the data warehouse, but a Python
job can call a model at list time. Nobody outside the team needs to recompute a score by hand.

Building, serving, monitoring and retraining a model is estimated at 60,000 EUR a year in staff time.
