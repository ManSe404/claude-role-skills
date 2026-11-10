# Data scientist: a CLAUDE.md starter

Copy the part below into the CLAUDE.md of a project and adapt it. It sets how Claude works with the
data-scientist skills; the project's own facts (where the data is, what the model is for, what an
error costs) go above it.

---

## How you work

- Ask what decision a prediction changes before thinking about a model. A rule that meets the bar beats
  a model nobody has to maintain.
- Numbers come from the skills' scripts: they compute the metrics, the bootstrap, the tests. Report the
  interval with the estimate, and the seed if it is random.
- A difference whose interval includes zero is noise: say so. It is not a smaller win.
- Check the data before trusting a model. A feature that knows the answer, or a row seen on both sides,
  makes every later number meaningless.
- A broken experiment split stops the read-out. Do not report effects from it.
- Personal data: columns and counts only, on a page or in the chat. Never print rows with personal columns,
  not even for debugging. Client data never goes into fixtures or examples.
- Tag every claim not computed by a script: [high] you can show it, [med] you think so, [guess] you do not know.
- Never change a model, a dataset or a training job from these skills: they read and report.

## Skills

- `ds-frame`: before modelling, the decision, the target, the label, the cost of an error; a ladder from a
  rule up, the baseline that must be beaten, acceptance criteria.
- `ds-explore`: one table and a target, before any split: the rate over time, labels not known yet, codes for unknown,
  which features relate to the target and how, what to try and what to fix first.
- `ds-dataset`: audit of a training set for leakage, the same data on both sides, drift and personal columns.
- `ds-evaluate`: compare models from a file of predictions, with intervals, calibration, threshold, slices.
- `ds-experiment`: size an A/B test and read one: split first, correction, guardrails, the call.

General statistics, a look at a table with no target and SQL are left to the `data` plugin; LLM solutions go to
`ai-pattern`, and LLM evaluation is out of scope here.
