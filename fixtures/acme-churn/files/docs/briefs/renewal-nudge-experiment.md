# Brief: the renewal-nudge experiment

An in-app reminder 14 days before a subscription renews, sent to subscribers randomly assigned to
`treatment`; `control` got nothing. Split 50/50 by subscriber at the moment they became eligible.

Files, both with one row per subscriber:

- `data/experiment_broken.csv`: the first attempt, in August. The assignment service was changed
  partway through.
- `data/experiment_clean.csv`: the September run, after that was fixed. Plan: at least 2,900
  subscribers per arm, 14 days of assignment.

Metrics, all measured per subscriber at the renewal date:

- primary: `renewed`, higher is better;
- also measured, any of which could justify shipping: `upgraded`, `app_open_7d`, `arpu_eur`;
- guardrails, lower is better: `support_contact` may rise by at most 2.0 percentage points,
  `refund_requested` by at most 0.75 percentage points.

The smallest rise in renewal worth shipping is 2.0 percentage points. The team looked at the
dashboard every working day of the two-week run: 10 looks.
