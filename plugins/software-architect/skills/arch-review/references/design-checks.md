# What makes a design fail or hard to change

The inventory's field is in the second column. A line in it is a place to read, not a finding; the
finding is what the documents say there, read whole.

| Problem | Field | Confirm by | Fix |
|---|---|---|---|
| A chain of waiting calls longer than its goal | `links` (sync), `latencies`, `quality_goals` | add the stated times along the chain where each caller waits, at the goal's percentile | make one step not wait (a queue, a cached quote), or agree a new goal |
| Data written by two parts | `data_writes` with `shared_write` | does each really write it, or does one only read? | one owner; the others send it a command or follow its events |
| A promise with no mechanism | `promises` | which part keeps it, and how: a key, a transaction, a dedupe, an outbox? | name the mechanism in the design, or drop the promise |
| A quality goal without a number | `quality_goals` with `has_number: false` | is the number stated anywhere else? | a number, a percentile and the load it must hold at |
| An outside dependency with no failure plan | `links` to outside systems | does any document say timeout, retry, fallback or what the user sees? | a timeout and a fallback per dependency, and what the user sees |
| Documents that disagree | `links` between the same parts in different styles; `adrs` status | which is current: the accepted ADR or the later proposal? | one decision, recorded, and the other superseded |
| A boundary by technical layer | `parts` and `links`: one part that every other part calls for its data | does every business change need that part's team? | data owned by business area, each service with its own |
| An open decision that blocks others | `open`, ADRs still Proposed | which parts of the design rely on the answer? | decide it first, or design so that either answer works |
| One part everything waits on | `links` fan-in | can the rest work while it is down? | a second instance, or a way to degrade |

## What the inventory cannot see

- A need in the brief that no part of the design serves.
- Load the design never sizes: peak figures, growth, data volume.
- Security: where untrusted input enters, who may call what, where secrets live.
- Operations: how it is deployed, observed, rolled back, and moved to from today's system.
- Cost.

## Severity

- **High:** expensive to change once built (who owns data, a waiting dependency, a promise customers
  rely on), or the design cannot meet a goal it states.
- **Medium:** it will cost more later, or a decision other teams wait for is missing.
- **Low:** unclear wording or a missing diagram; nothing is blocked.

Leave alone what is unusual but argued: a decision with its reasons written down costs nothing to keep.
