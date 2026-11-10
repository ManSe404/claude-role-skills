# What a postmortem must hold

## A sourced timeline

Every entry names its source: a log line (`acme-orders.log:10`), a page (`incident-triage 2026-10-03,
facts`), a commit (`c376ea1`), a deploy record, or a person's statement marked as such ("the lead says the
rollback ran at 10:02; no log line"). An entry with no source is a gap, written as a gap. Times are in one
zone, named once at the top.

The entries that must be there, when the facts give them: the last change before the first error, the first
error, detection (who or what noticed), the first status update, each mitigation step, the moment it worked
again, resolution, and every point where the picture changed (a second signature, a wrong hypothesis
dropped).

## Phases and what they say

| Measure | Read against | What a bad number means |
|---|---|---|
| minutes to detect | errors before detection | nobody or nothing watched; an alert on the signature is the action |
| minutes to mitigate | the moves available at the time | the move was unknown, unsafe or needed someone absent; a runbook or a flag is the action |
| minutes to resolve | the size of the fix | the fix needed knowledge that was not written down |
| errors after mitigation | zero expected | the move did not stop it, or a second cause |

## The why chain

Each link is a question, an answer, the evidence and a tag. The evidence is a log line, a commit, a test, a
line of code or a page; "it is likely" is not evidence. The chain stops at the first link that would be a
[guess], and the page says what evidence would extend it (a metric nobody kept, a conversation nobody wrote
down). Five whys is not a target; three sourced links beat five invented ones.

A link that names a person ("the engineer did not run the tests") is rewritten to the system ("the pipeline
does not run the tests of that package", with where). The question is what let it happen, not who.

## Contributing factors

What let the cause reach production and stay there, each with evidence:

- a test removed or never written (the diff, the test file)
- no alert on the signature (the alert rules, or the time to detect)
- a deploy with no check after it (the deploy record, the first error minutes after)
- a format, a dependency or a contract nobody documented (the documents, or their absence)
- a runbook or a flag that did not exist (the time to mitigate)
- a second system that depended on the first in a way nobody knew (the timeline of the second failure)

## Action items

An item is real when it has a factor it answers, a role that owns it and a check that shows it is done:

| Action | Check |
|---|---|
| a regression test | the test exists in the repository and fails on the old code |
| an alert on the error signature | the alert rule exists and fires on a replay of the log |
| a deploy check | the pipeline runs it and a deploy without it is refused |
| a runbook or a flag | the document or the flag exists and was tried once |
| a document | the document exists and names the format, the contract or the dependency |

An item with no check, no role or no factor is not listed; "be more careful" is not an action.

## What went well and poorly

From the facts, not from feeling: detection in N minutes against M errors before it; a rollback that worked
in N minutes; an alert that did not fire; a status update that went out on time; a runbook that was missing.
Each line with its number or its source.

## The document

```
# Postmortem: <title>

Date: <first error> to <resolved>    Severity: SEV<n>    Status: draft | reviewed
Roles: lead, comms, fix

## Summary
<three sentences: what broke, for whom, how long, what fixed it>

## Impact
- <who could not do what, for how long, with counts>

## Timeline (<time zone>)
| Time | Event | Source |
|---|---|---|

## Root cause
<one sentence, with evidence>

## Contributing factors
- <factor, evidence>

## What went well
- <fact>

## What went poorly
- <fact>

## Action items
| Action | Factor | Role | Check | Done when |
|---|---|---|---|---|

## Open questions
- <what the evidence could not answer>
```
