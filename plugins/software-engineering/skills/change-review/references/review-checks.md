# What to check in every hunk

Four dimensions, in this order, because what reaches a user or the data outranks what reaches the next
developer. A hunk usually touches one or two; note which, and note "none" when none applies, so the page
shows the hunk was read.

## Security: can a value from outside do more than it should?

| Problem | Confirm by | Fix | Test that catches it |
|---|---|---|---|
| SQL, a shell command, a path, a URL or a template built from a value (`sql-concat`, `shell-input`, `path-from-input`, `url-from-input`) | trace the value to where it enters: a request, a file, an argument, a message | parameters, argument lists, a resolved path under a root, an allow list of hosts | a value with `'`, `;`, `../` or a private host must be refused or passed through as data |
| A check that is missing or can be skipped: who may call this, who owns this object | read the caller chain: is the check before every path to the action? | one check at the entry, the object's owner compared with the caller | a request for another user's object must get 403 or 404, never the object |
| A secret in the diff (`secret-literal`), in a log line or in an error message | is it a real credential, a fixture or a placeholder? | settings or a secret store; rotate what was committed | a log capture that contains no key |
| Data built into objects or code (`unsafe-load`, `eval`, `pickle`, `yaml.load`) | does the data come from outside the process? | `json`, `safe_load`, a schema | a payload with a constructor tag or code must be refused |
| Input accepted without bounds: size, count, depth, type | what happens with an empty value, a huge one, the wrong type? | validate at the edge, with limits | the empty, the huge and the wrong-typed input, each with its expected refusal |

## Performance: does it still work when the numbers grow?

| Problem | Confirm by | Fix | Test that catches it |
|---|---|---|---|
| A call inside a loop (`call-in-loop`): one query, request or write per element | how large can the loop get, from where the elements come? | one query with `IN`, a bulk write, a prefetch, a cache for the loop | the call count stays constant when the input grows |
| A whole table or file read (`unbounded-read`) in a request path | is the caller a request handler, and can the source grow? | `WHERE` plus `LIMIT` and paging; stream a file | a source ten times larger must not make the request ten times slower |
| Quadratic work on a hot path: a nested loop over the same list, `in list` inside a loop, repeated sorting | which paths call this, and how often? | a set or a dict, sort once | a timing at 10 and at 10,000 elements with a bound |
| A resource not released (`unclosed-resource`): a file, a connection, a thread, a temporary file | which path leaves without closing, usually the error path | `with` or `try/finally` | after a raised error, the handle count is back where it was |
| Memory held for the whole run: a list built where an iterator would do, a cache that never evicts | where the data goes after it is built | a generator, a bounded cache | memory flat over a long input |

## Correctness: does it do what it says in every state?

| Problem | Confirm by | Fix | Test that catches it |
|---|---|---|---|
| Edge cases: empty input, `None`, zero, negative, the last element, Unicode, a comma where a dot is expected | read what the old code accepted that the new one does not | handle the case or refuse it loudly | the case itself, with its expected result |
| An error swallowed or widened: `except Exception`, a return of `None` or `[]` on failure, a catch that re-raises without the cause | what does the caller get, and does it look like success? | catch what you expect, let the rest reach the caller, `raise ... from exc` | the failing input; the caller must see an error, not an empty result |
| A race: check-then-act, a shared mutable object, two writers of one record | can two requests reach this at once? | a lock, a transaction, an atomic operation | two concurrent calls, one must lose or wait |
| Off by one, a boundary moved, an inclusive range made exclusive | compare the old and the new boundary against every caller | one definition of the boundary | the boundary value and its neighbours |
| A type that changed: a string that was a Decimal, a date that was a datetime, an optional that was required | follow the value to where it is stored, compared or summed | one type across the flow | a value that only the old type accepted |
| A behaviour removed that someone relies on: a format accepted, a field written, an event sent | search the callers, the docs and the tests that were deleted | keep it or deprecate it with a window | the test that was removed, kept |

## Maintainability: will the next change be safe?

| Problem | Confirm by | Fix | Test that catches it |
|---|---|---|---|
| A second copy of a rule or a format: the same parsing, the same keys, the same validation in two places | search for the first copy | one function, one constant | a change to one copy breaks a test of the other |
| Logic with no test: a changed source file with no changed test, a branch no test reaches | the facts list `source_without_test_change`; read the nearest test | the test, written out on the page | the test itself |
| A name that lies: a function whose name says one thing and whose body does another after the change | read the body against the name and the docstring | rename, or split | none; review is the test |
| A silenced check: `# type: ignore`, `# noqa`, a disabled lint rule, a skipped test | what it hides | fix the cause | the check turned back on |
| A migration without a rollback, a dependency pinned to a version with a known problem, a CI step removed | the facts list them under `risk_files`; read each | the rollback, the safe version, the step restored | none; a checklist item |

## Claims against the diff

A claim is a sentence of the PR description, the ticket or a commit message that says what the change does
or guarantees. For each: which hunk keeps it. "Fixes the import" with no hunk in the importer is not kept.
"Simplifies parsing" that removes a case and its test is a behaviour removed, not a simplification.

## Severity

- **High:** once merged, a user gets a wrong result, data is lost or exposed, or a request can be made to do
  something its caller may not.
- **Medium:** a failure is loud but costs a cleanup, or a guarantee holds only by luck, or a test was removed.
- **Low:** a trap for the next change; nothing is wrong today.

## Verdict

- **approve:** no high finding, no test removed without a reason, every claim kept or explained.
- **request changes:** any high finding, a test removed without a reason, or a claim the diff contradicts.
- **needs discussion:** a claim and the diff disagree and the reviewer cannot tell from the code which is right,
  or the change needs a decision the diff does not record (a format dropped, a dependency changed).

Say what looks good, with file:line, in two to five lines: the test that was added, the boundary made explicit,
the duplication removed. A review that lists only faults is not read, and praise that is not tied to a line is
not believed.
