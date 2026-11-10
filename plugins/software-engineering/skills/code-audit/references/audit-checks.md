# What to look for in code as it stands

The scan's rule is in the second column. A hit is a place to read, not a finding; most of what
matters has no rule and is found by walking the failure paths.

| Problem | Rule | Confirm by | Fix | Test that catches it |
|---|---|---|---|---|
| Delete before write across a call that can fail | `delete-then-write` | is there an outside call or a commit between the delete and the write? Inside one database transaction it is fine | write first, then delete what this run did not write; or one transaction | make the step after the delete fail; the old data must still be there |
| Error swallowed | `swallowed-exception`, `suppress-all` | what does the caller get: an empty result that looks like success? | catch only the errors you expect; let the rest reach the caller or a report | feed the failing input; expect an error or a reported failure, not an empty result |
| Key read that is never written | `orphan-key` | grep the key: is it written under another name, or only by an outside system? | one constant or one typed model for both sides | write, then read back, and compare every field |
| Call with no timeout | `no-timeout` | does a default timeout apply (client config, library default)? | an explicit timeout from config | a fake server that never answers; the call must give up in time |
| Retry with no limit | `retry-loop` | does every error path count an attempt, and is the count compared to a limit? | one counter for every failure, a limit, then the dead-letter path | an error type the loop does not expect; it must stop after the limit |
| Id that changes between runs | `builtin-hash` | is it stored or compared across processes? `hash()` of text differs per process | a stable hash (sha256 of the stable fields) | the same input in two processes must give the same id |
| Stream or protocol that can end without its last message | none | which errors does the loop catch, and what escapes it? | catch at the edge, always send the final event | a malformed line from the upstream; the stream must end with the error event |
| Check that disappears in production | `assert-in-code` | is it a runtime check rather than a test? `python -O` removes asserts | a real `if` with an error | run the check with `-O` |
| Shared default that leaks between calls | `mutable-default` | is the default ever changed? | `None` and create inside | two calls must not see each other's data |
| Silenced type error | `type-ignore` | what is the real type, and can the call fail? | fix the type or the interface | usually none; the type checker is the test |
| Catch-all in another language | `catch-all` | as for a swallowed error | as above | as above |

## What the scan cannot see

- A promise in the docs that no code keeps: idempotency, ordering, exactly one final event, "never
  loses". Find the code for each promise, or report that there is none.
- State left half-changed when a step fails: an object edited in place and then saved, a plan amended
  before it is checked, a status set before the work is done.
- Two copies of one rule or format: the same string keys, collection names or validation in two
  places, so they drift apart without a failing test.
- A failure that becomes a silent wrong answer: a missing table returning an empty list, a default
  value hiding a missing field, an optional dependency missing and treated as "no data".
- Concurrency: two runs on the same item, a shared mutable object, a check-then-act without a lock.
- Tests that pass for the wrong reason: they check a fake, or they never reach the failure path.

## Severity

- **High:** data is lost, corrupted or duplicated, or a user gets a wrong result with no sign of it.
- **Medium:** a failure is loud but leaves a mess to clean up, or a guarantee holds only by luck.
- **Low:** a trap for the next change; nothing is wrong today.

Leave alone what is odd but correct, and say why: an unusual pattern that a test pins down costs nothing.
