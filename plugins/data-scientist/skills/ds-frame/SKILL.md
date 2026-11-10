---
name: ds-frame
description: Use before building a predictive model, when someone asks for a model or a prediction and the decision it should change, the exact target, the label and what each error costs are still open, to decide whether a rule, a simple score or a real model is the right thing to build, name the baseline it must beat and write acceptance criteria. Not for an LLM or chatbot solution (use ai-pattern) and not for a general data question.
argument-hint: "[brief file or text] [folder of history data]"
---

# Frame a model

The job: before anyone trains anything, say what the prediction is for. Which decision changes, what
exactly is predicted and when, whether a label exists in time, what each error costs. Then a ladder
from the simplest thing up, with options ruled out against the brief, a baseline that must be beaten,
and acceptance criteria. It writes only the page. Often the right answer is a rule, and the page says so.

Input: a brief (a file or text) and optionally a folder of history (CSV or JSON Lines). Default: ask
for the brief.

## Steps

1. Read [references/ladder.md](references/ladder.md): the ladder, what each fact decides, how to set
   the baseline and how to write acceptance criteria.
2. Frame it, each line with where it came from in the brief:
   - **Decision:** what changes when the prediction changes. No decision means no model, a report.
   - **Target:** the exact outcome, for whom, over what horizon, computed how.
   - **Moment:** when the prediction is made and what is known at that moment.
   - **Label:** does the outcome exist in history, and how long after the prediction is it known.
   - **Costs:** what acting wrongly costs and what not acting wrongly costs, in money or a stated proxy.
   If the job is reading or writing free text, stop here: say this is `ai-pattern`, not this pack.
3. Ask what would flip the answer, in plain words, the two to four facts that matter most, and wait.
   If the user says go on, assume, and write every assumption next to the decision it drives.
4. If a history folder is given: `python3 "${CLAUDE_SKILL_DIR}/scripts/data_profile.py" FOLDER` for
   the shape, then `python3 "${CLAUDE_SKILL_DIR}/scripts/measure.py" FOLDER SPEC.json` for the base
   rate and for how well a rule from the brief would have done (the same measure with a filter), so
   the facts carry measured numbers instead of hopes.
5. Hard rules: write the facts as JSON in your scratchpad and run
   `python3 "${CLAUDE_SKILL_DIR}/scripts/frame_rules.py" FACTS.json` (`--facts` lists them). Keep every
   eliminated option with its rule. Never overrule a rule; if it is wrong, the fact is wrong: fix the fact.
6. Choose the lowest open rung. Climb above `lowest_open` only for a reason you can name from the
   brief, written on the page. A cost you assumed goes on the page as `[guess]`.
7. Name the baseline that must be beaten, from `baseline_to_beat` and `economics`, with this brief's
   numbers: the score, the rule or the trivial policy, and its value. A model that does not beat it
   is not shipped.
8. Write acceptance criteria: three to five, each with a threshold and how it is measured before
   launch (a metric with a floor, a cost per case, a calibration limit, a fairness or slice limit).
9. Write what would change the answer: three to five conditions, each with the rung it leads to.
10. Write the page JSON, with `facts`, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: The frame (a `kv` block: decision, target, moment, label, costs, each with its
source), The ladder (a `decision` block from the simplest up, factors as columns, an eliminated option
keeps its rule), What it would cost (a `chart` of kind `bar`: the cost per case of acting on nobody, acting
on everyone and, if measured, the rule; and the break-even probability, leave the chart out if the
costs are not known), The baseline, Acceptance criteria (table: criterion, threshold, measured how), What
would change the answer (list), Assumptions and open facts. Stats on top: the rung chosen, the base rate,
the break-even probability, the ceiling a perfect model could save per year. The verdict says what to
build, in one or two sentences, or says to use `ai-pattern`, or says that no model is needed at all.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both files
in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/ds-frame-<YYYY-MM-DD>.*`. Write the page in the
language of the request; Serbian pages in Latin script.

## Reads

- the brief; history data read-only, through `data_profile.py` and `measure.py`

## Writes

- the page and its JSON, outside the repo

## Never

- Never starts a model or trains anything: this skill only frames.
- Never overrules a rule of the script, and never states an assumed cost as a fact.
- Never recommends climbing the ladder without a named reason from the brief.
- Never prints rows containing personal columns, not even for diagnostics. An earlier run printed names
  into its session log while debugging, and a script cannot prevent that. Columns and counts only.
