# What makes a structure hard to change

The script's output field is in the second column. A number is a place to read, not a finding.

| Problem | Field | Confirm by | Fix |
|---|---|---|---|
| Cycle between modules | `cycles` | which `using` or import closes it, and why | move the shared idea down, invert one direction, or merge the two |
| Layer break | `layer_breaks` | does an inner layer really call an outer one? | an interface in the inner layer, implemented outside |
| Dumping ground | `modules`: high fan-in, unrelated contents | read it: do its parts belong together? | split by purpose and move each part to its user |
| Hidden coupling | `git.hidden_coupling` | why do these always change together? | one owner of the rule, or a shared contract |
| Hot spot | `git.hot_spots` | is it big because it does too much? | split along what changes together; test first |
| One person only | `git.owners`, `one_person` | is the knowledge written down anywhere? | pair on the next change, write what only they know |
| Shared table | `containers: tables_shared` | who owns the rows and the schema? | one owner; others call it or get events |
| Synchronous loop | `containers: loops` | can a request wait on itself? | break one direction with a queue, or merge them |

## Instability

Instability is fan-out / (fan-in + fan-out). Near 0 means many depend on it and it depends on little:
it should be stable and abstract. Near 1 means it depends on others and few depend on it: it is free
to change. A much-used module with high instability is the dangerous case.

## What a script cannot see

- Boundaries drawn around technical layers instead of business areas.
- A "shared" library that holds business rules, so every service changes with it.
- A retry with no limit, a call with no timeout, a failure that blocks the whole request.
- A deployment that needs another one first.
- Tests that only pass with everything running.

## Severity

- **High:** it blocks the next planned change, or a failure spreads between parts.
- **Medium:** each change costs more because of it, or it will grow worse.
- **Low:** untidy, and no change is held back today.

Leave alone what is ugly but stable: code nobody needs to change costs nothing.
