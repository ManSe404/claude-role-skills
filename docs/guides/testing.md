# Testing

Three kinds of checks, from free to paid: the unit tests, the evals, and the selection check. How they fit into the
design is in [architecture/overview.md](../architecture/overview.md#how-it-is-checked).

## Unit tests

```bash
uv run pytest
```

They cover the scripts, the renderer, the guard, the fixtures, the selection check's judging and the skill files.
They build the fixtures into temporary folders and call no model. `tests/test_page_script.py` drives the page
script in headless Chrome or Chromium and is skipped when neither is installed. CI runs them on every push to `main`
and every pull request.

The scripts are tested against the fixtures (see [reference/codebase.md](../reference/codebase.md#fixtures)): each is a
made-up project with planted problems, and its `test_fixture_*.py` checks that the build holds them.

## Evals

Each pack's `evals/` holds cases for `claude plugin eval`. A case is `case.yaml`, `prompt.md`, `fixture.sh` (builds
the fixture the case runs on) and `graders/`. The evals start real Claude sessions and cost money, about 80 cents a
case; `--max-cost-usd` caps a run. Run them only when asked.

```bash
claude plugin eval plugins/software-engineering --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins/ai-architect --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins/data-architect --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins/data-engineer --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins/data-analyst --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins/data-scientist --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins/software-architect --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins/cloud-architect --scaffold --allow-tools Bash Write --runs 1 --ablation none
claude plugin eval plugins --eval-dir solutions-architect/evals --scaffold --allow-tools Bash Write --runs 1 --ablation none
```

Without `--ablation none` each case also runs without the plugin, for comparison, which about doubles the cost. The
`solutions-architect` command differs because its cases must load the four specialist packs, and the eval tool only
loads plugins from inside the folder it is pointed at.

Writing a case, from [CLAUDE.md](../../CLAUDE.md): in the eval sandbox shell commands cannot write files, so
`page-made` checks the page's JSON, not its HTML. A grader never reads `target: trace`, because the trace holds the
text of SKILL.md and a pattern found there proves nothing; use `tool_used` on `Bash` with `input_match`. An `llm`
grader sees only the final reply, not the code or the page.

### Summing up the results

`claude plugin eval` writes its results to `plugins/PACK/evals/results/`, which git ignores. `tools/eval_table.py`
sums them into one Markdown page, pack by pack and case by case: outcome graders (what was produced) separately from
"the skill fired", with the cost.

```bash
python3 tools/eval_table.py -o docs/evals.md
```

## Selection check

The evals load one pack at a time, so they cannot show whether Claude picks the right skill among all of them. The
selection check does: it loads every pack from this repository and makes one model call per prompt in
`tools/selection_cases.json`, about 15 cents each.

```bash
uv run python tools/selection_check.py
```

`--all-tools` offers Claude's ordinary tools as well as Skill; `--budget USD` caps the spend (25 by default);
`--only TEXT` runs the cases whose id contains the text; `--out DIR` sets where the results go; `--runs N` and `-j N` set
the runs per case and how many run at once. Pass `--out` with a folder outside the repository: the default is
`selection-results` in the current folder, which `.gitignore` does not list.

## Open

- The script's docstring says nothing in the repository changes, but its default `--out` is a relative folder, so a
  run from the repository root without `--out` writes `selection-results/` into the working tree.
- There is no documented command for the `workflows` evals. Their cases load other packs through `plugins:` in
  `case.yaml`, as the `solutions-architect` cases do, so the same form
  (`claude plugin eval plugins --eval-dir workflows/evals ...`) is likely needed; it has not been checked.
- `tools/eval_table.py` writes its page to `docs/evals.md`, which holds eval results inside the repository. Where those
  results should live is an open decision; see [docs/README.md](../README.md#open-decisions).
