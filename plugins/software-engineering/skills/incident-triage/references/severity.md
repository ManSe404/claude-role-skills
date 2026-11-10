# Severity, mitigation and the status update

## Criteria

Each criterion is set by a fact from the timeline, the logs or the report, with where the fact comes from.
A criterion with no fact is unknown: it is listed, and it lowers nothing. The level is the highest any
criterion sets.

| Criterion | Sets SEV1 | Sets SEV2 | Sets SEV3 | Sets SEV4 |
|---|---|---|---|---|
| Who is affected | every user, or the whole service | many users, or one main feature | some users, or a minor feature | one person, or nobody yet |
| Data | lost or wrong and not recoverable | wrong but recoverable, or delayed past a deadline | delayed, within the deadline | untouched |
| Workaround | none | manual and costly | exists and is cheap | not needed |
| Spreading | growing with time or load | stable | shrinking | over |
| Money or obligation | revenue, a contract or a regulator | a report or a partner | internal | none |

Response time is the organisation's rule, not this page's; the page gives the level and the facts, the
organisation gives the clock. A level set by one unknown criterion is written "SEV2, assuming the workaround
holds" and the assumption goes on the page.

## Mitigation moves

Each option on the page names the move, the evidence that it would help, what it costs and what it does not
fix. None is executed here.

| Move | When the evidence supports it | Cost | What it does not fix |
|---|---|---|---|
| Roll back to the version before the first error | the first error follows a deploy or version change and the error's frame is in code that deploy touched | the features of that deploy go with it; data written in the new format may need care | an input that would also break the old version |
| Turn the feature or the path off | a flag, a route or a job can be disabled and the rest of the service does not need it | that function is unavailable until fixed | the records already affected |
| Quarantine the input | the error names one file, message or record that fails every time | the rest proceeds; the quarantined item waits | nothing about the code; the item comes back |
| Scale, drain or restart | the signature is a resource (connections, memory, a queue) and the rate grows with load | time and money; a restart hides the evidence | the leak or the growth |
| Replay or re-run | the run failed before it wrote anything, and the input is still there | nothing, if the first run wrote nothing; duplicates if it did | the cause |
| Do nothing yet | the failure is contained, the impact is SEV4 and the fix is near | the risk that it spreads | anything |

The move with the best evidence comes first. "Nothing was saved from the failing file" is a fact the
timeline gives (a run that errors before its first write); it decides whether a replay is safe.

## Status update

```
Incident: <title in the words of the report>
Severity: SEV<n> (<the criterion that set it>)    Status: investigating | identified | monitoring | resolved
Since: <first error, local time>                  Next update: <time>

What we know
- <fact, with its source: log, alert, report>
- <fact>

Impact
- <who cannot do what since when, with the count>

What was done
- <step, when, by which role>

Next
- <step, by which role, by when>
```

Facts only: what the logs show, what was done, what is next. No cause until `bug-hunt` has evidence; "the
first error follows the 18:05 deploy" is a fact, "the deploy broke it" is not yet. No names: roles.

## Roles

- **Lead:** decides, keeps the timeline, calls the level.
- **Comms:** sends the status update on the cadence the level sets, and only that.
- **Fix:** runs `bug-hunt`, proposes the fix, never deploys without the lead's yes.

One person may hold all three on a small team; the page still lists them so a hand-over has a shape.
