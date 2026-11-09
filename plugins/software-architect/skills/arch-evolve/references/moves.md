# Safe moves

Each move leaves the system working. Prefer the smallest one that makes the next step possible.

| Move | When | Verify | Undo |
|---|---|---|---|
| Characterise first | the code to move has no tests | tests pass before and after | delete the tests |
| Break a cycle | two modules use each other | no cycle in `code_graph.py` | revert the commit |
| Invert a dependency | an inner layer uses an outer one | no layer break | revert the commit |
| Split a dumping ground | one module holds unrelated things | its fan-in drops; imports move | revert the commit |
| One owner for a rule | the same rule is written twice | the pair stops changing together | keep both behind a switch until proven |
| Enforce a boundary | modules exist only by convention | a CI check fails on a violation | turn the check off |
| One writer per table | two deployables write one table | only the owner writes | restore the old path |
| Parallel run | replacing logic that must be right | old and new agree on real traffic | keep using the old result |
| Strangler | moving a capability out | traffic moves route by route | route it back |
| Expand, then contract | changing a schema or a contract | old and new work during the change | stop before the contract step |
| Queue instead of a call | a synchronous loop or a slow dependency | the caller no longer waits | call directly again |

## Choosing

1. Do what makes the next step safe: tests before moves, boundaries before splits.
2. Do what delivers something by itself. A plan that pays only at the end usually stops halfway.
3. Split out the part with the strongest reason to be separate, not the easiest one.
4. Move data last, and in expand-then-contract steps.
5. Stop when the main pain is gone. A half-finished migration that nobody finishes is the worst state.
