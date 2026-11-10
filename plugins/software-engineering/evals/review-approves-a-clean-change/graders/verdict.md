---
type: llm
---

The commit changes vat_total to stop rounding per line and order_total to round once, updates the docstring, and adds the test test_rounds_once_per_order (3 x 3.33 = 11.99). Nothing in it is wrong: the callers (report.py, cli.py) use order_total and the tests cover the change.
PASS if the reply's verdict is approve (low notes are fine) and it names at least one thing that looks good with its file, such as the added test or the docstring that now matches the code.
FAIL if the verdict is request changes or needs discussion, if it reports a high finding, or if it invents a bug that is not in the diff (for example that rounding once changes the discount).
