---
name: ds-evaluate
description: Says which trained model is really better than the baseline and which differences are noise, with intervals, calibration, a cost-based threshold and the worst slices.
when_to_use: Use when comparing predictive models from a file of predictions with the label. Not for evaluating an LLM or retrieval.
argument-hint: "[predictions file(s)] [baseline column] [costs of a false positive and a false negative]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/ds-evaluate/scripts/guard.py" ] && exec python3 "$d/skills/ds-evaluate/scripts/guard.py" pre ds-evaluate personal; done; true'
  PostToolUse:
    - matcher: "Bash|Read"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/ds-evaluate/scripts/guard.py" ] && exec python3 "$d/skills/ds-evaluate/scripts/guard.py" post ds-evaluate personal; done; true'
---

# Evaluate models

The job: say which model to use, or none, in a way that survives being checked. Each metric with a
confidence interval, the same paired comparison against the baseline for every model, a difference
inside the noise called exactly that. Then calibration, a threshold from the costs of each
error, and how the model does per slice, the worst first. It changes nothing.

Input: one or more files of predictions (CSV or JSON Lines) with an id, the label, one score column
per model and any slice columns; the baseline's column; the costs of a false positive and a false
negative if the model will be used at a threshold. Default: ask for the file and the baseline.

## Steps

1. Read [references/evaluation.md](references/evaluation.md): what each number means, reading a
   paired interval, calibration, thresholds, slices, and what the bootstrap does not cover.
2. Shape: `python3 "${CLAUDE_SKILL_DIR}/scripts/data_profile.py" FILE`, output to your scratchpad: the
   columns, whether the id is unique, the personal columns. Work out which columns are models.
3. Evaluate, output to your scratchpad:
   `python3 "${CLAUDE_SKILL_DIR}/scripts/model_eval.py" FILE --id ID --label LABEL --models A,B,C
   --baseline A [--cost-fp X --cost-fn Y] [--slice COL ...] [--primary METRIC]`
   (default 2000 resamples, seed 7). Read `read` first: rows dropped, repeated ids, whether every model
   scored the same rows. `read`, `comparisons` and `primary_reading` are the base of the page.
   `measure.py` and `model_stats.py` are behind it.
4. Compare with the baseline. For each model and metric read `reading`: "better", "worse" or "inside the
   noise". Never state a win whose interval holds zero: say it is inside the noise, and say what the
   interval rules out.
5. Calibration: for models with probabilities, read each `calibration` block, its `reading`, the gap per
   bin. A model that ranks well and is miscalibrated cannot use a threshold taken from probabilities: use the
   empirical threshold or recalibrate first.
6. Thresholds: read each model's `best`, against acting on nobody and everyone, and
   `out_of_sample_cost_per_1000` (chosen on one half, costed on the other). Quote the out-of-sample number.
7. Slices: read `slices.worst`; too-small slices are listed but not ranked. Name the worst slices and
   whether a model is clearly worse there, or worse than the baseline there.
8. Recommend: which model, or none, or more data, with what must happen before it goes to
   production. Write the page JSON, with `facts`, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page.

Sections in this order: The comparison (table: each model, each metric, value and interval; a table of the
paired differences against the baseline with the reading), Calibration (a `chart` of kind `line`, one per
model that matters: mean predicted and observed by bin; the table of the bins), Threshold (a `chart` of
kind `line`: cost per 1,000 against the threshold, or against the share acted on; the best threshold with
its confusion counts), Slices (a `chart` of kind `bar` of the worst shortfalls, and the table with intervals),
The recommendation, What was not checked (list). Keep a bar label under 30 characters, or the renderer
cuts it. Stats on top: rows, positive rate, the best model and its gain over the baseline with interval,
the models whose win is inside the noise. The verdict says
which model is really better, by how much, and what stops it being used as it is.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both files
in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/ds-evaluate-<YYYY-MM-DD>.*`. Write the page in the
language of the request; Serbian pages in Latin script.

## Reads

- the predictions files read-only, through `data_profile.py`, `measure.py`, `model_eval.py` and `model_stats.py`

## Writes

- the page and its JSON, outside the repo

## Never

- Never calls a difference inside the noise a win, and never quotes a metric without its interval.
- Never ranks a slice by a point estimate alone: a slice's interval goes with it, and a too-small slice is
  not ranked.
- Never shows an id or a row; only metrics, counts and slice names, and a personal column is never a slice.
- Never prints rows containing personal columns, not even for diagnostics. An earlier run printed names
  into its session log while debugging, and a script cannot prevent that. Columns and counts only.
