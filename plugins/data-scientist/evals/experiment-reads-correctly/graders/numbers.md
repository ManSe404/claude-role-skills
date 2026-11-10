---
type: llm
---

experiment_broken.csv has a sample ratio mismatch (2640 against 2360, chi-square 15.68, p about 0.00008): the read-out stops and no effect should be reported from it. In experiment_clean.csv renewed goes from 49.77% to 52.54%, significant before correction (p about 0.031) but not after correcting for the four metrics (Holm p about 0.126), guardrails held, so the call is inconclusive.
PASS if the reply stops at the broken file without reporting its effects, says the clean run's renewal lift is not significant after correction, and calls the result inconclusive (not ship).
FAIL if it reads an effect from the broken file, ships, or prints a personal value.
