# Reading an experiment

An A/B test is randomised, so a difference between the arms is caused by the change, if the
randomisation held. The order of the read-out follows from that.

## Before launch

`plan` gives the sample per arm for the smallest effect worth detecting (or the smallest effect a given
sample can detect): two-sided, normal approximation, with the alpha split across the metrics the
ship could rest on. Say what the test can and cannot find: below that size you cannot tell. Plan the
number of looks before starting.

## The split comes first

A sample ratio mismatch: the arms did not come out in the planned ratio, more than chance allows. The
check is a chi-square test against the expected share, at p below 0.001, the usual conservative threshold.
A broken split means units were lost unevenly or assigned wrongly, for instance a redirect that drops some
users of one arm, a bot filter, or a crash in one arm. The metric comparison then compares two
different populations, so its result means nothing, and the script prints no metric at all. The way out
is to find why and re-run the test, or re-read only a period where the split held.

The same goes for a unit in both arms (the assignment was not sticky) and for several rows per unit (the
file is not one row per randomised unit). Rows from the same unit are not independent, so the
standard errors would be wrong.

## Metrics and the family

Proportions get a Wilson interval per arm and a pooled two-proportion test for the difference. Means get
Welch's difference with a normal approximation, fine at A/B test sizes and flagged under 100 units per
arm. The interval on the difference is the unpooled one.

The correction is over a family: every metric a ship could rest on, primary included. If one metric of
several was going to be the winner either way, a chance win on any of them is a false ship. If there
really is one pre-registered primary metric and nothing else could justify shipping, list only that one
under `--metrics` and read the others with a separate run, marked exploratory. Holm's method
controls the chance of any false win and is never worse than Bonferroni; `corrected_low` and `corrected_high`
are the matching Bonferroni interval.

A metric significant before correction and not after is the case to say out loud: on one test, that
is what chance looks like.

## Guardrails

A guardrail is something the change must not harm: support contacts, refunds, latency. Testing for
"no significant harm" proves nothing with a small sample. So a guardrail has a margin, the largest harm you
accept, and the question is whether the whole interval of the harm lies below the margin. Held means yes;
breached means the whole interval is above it; unclear otherwise. Margins come from the brief, in the
metric's own units; a guessed margin is written on the page as one. Guardrails are not part of the
correction family: they must all hold, which is already a stricter test.

## Peeking

A running test read every day and stopped at the first significant day has a false-positive rate far above
alpha: 19% with 10 looks at 5%, 37% with 100 looks (the table is in the script). `--looks` reports that
rate for the count that actually happened. `--time` replays the primary metric per day, which shows whether the
reading was significant on some days only. Only a test read at its planned size supports a p-value at face
value; otherwise use a sequential design planned in advance.

## The call

- **ship**: the primary is better after correction, every guardrail held, the effect reaches the minimum.
- **do not ship**: a guardrail is breached, the primary is worse, or the whole corrected interval of the primary
  is below the minimum worthwhile effect, so even the best case is not worth it.
- **inconclusive**: anything else, including "significant before correction" and "not enough data to rule
  out a useful effect". A read-out the script stopped is inconclusive too. Report what would settle it, not a
  softened ship.

## What this cannot do

The interval covers randomness in who got which arm. It does not cover novelty effects, a change in
who entered the test, or one business cycle standing in for a year.
