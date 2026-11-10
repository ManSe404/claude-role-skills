# Plan: pack `data-analyst`

Status: built on 2026-11-10 from Stefan's brief. Decisions are at the end.

## Goal

A pack for the person who answers for numbers. It does the few repeated jobs where a number has to
survive being checked: define it so two people get the same answer, say why it changed, account
for the gap between two versions of it, and check a report before it goes out.

Same format as the other packs: `SKILL.md` in the fixed order, scripts that count, a page that is
JSON drawn by `render_page.py`.

Out of scope:
- answering a general question, exploring a table, one-off SQL, dashboards (the `data:*` skills
  installed from the Anthropic plugin: `analyze`, `explore-data`, `statistical-analysis`,
  `validate-data`, `create-viz`, `build-dashboard`, `sql-queries`, `write-query`);
- designing or reviewing a platform (`data-map`, `data-model`, `data-review`, `data-platform`);
- anything that needs a database connection: these skills work from extracts, read-only.

Descriptions must not take general requests from those skills: each says what concrete situation it
is for, and that it needs the data files or the SQL behind the number.

## Skills

### 1. `metric-spec`: one definition of a metric

When: two teams or reports show different numbers for what should be one metric, or before a metric
goes on a dashboard or into a target.
Input: a repository or report folder, the metric's name(s), a folder of sample data.

Steps:
1. **Find** definitions: `metric_compare.py find` (aliased expressions, their FROM and WHERE) and
   `sql_inventory.py`; read every hit.
2. **Understand** each one: grain, filters, formula, date basis, currency, owner, git history.
3. **Profile** the sample: `data_profile.py`.
4. **Write each definition as a measure** in SPEC.json and run `metric_compare.py compare`: each
   definition's number, and a walk that adds up to the gap, one difference at a time.
5. **The definition:** grain, filters, formula, time window, currency, owner, what it does not include,
   with a reason per difference. Open questions stay open.
6. **Check** it on the sample with `measure.py`. The page.

Never: changes a query; states a definition as agreed; shows a personal value.

### 2. `number-moved`: why did this number change

When: a reported number changed between two periods, someone asks why, and the rows behind it are in
a file.
Input: the rows (CSV or JSON Lines), the number and the two periods, the definition if there is a
repository.

Steps:
1. **Pin** the number, reproduce it with `measure.py`.
2. **Rule out data problems first** with `decompose.py`: late rows against the moment of the
   report (`--loaded-at`, `--as-of`), missing and thin days, duplicates, unequal periods; a definition
   or scope change from `git log` and new or gone segments. Say the part of the change that is not real.
3. **Decompose** by each candidate segment: volume, mix and rate effects that add up exactly; rank
   the drivers.
4. **Say** how much they explain, what is left, what a rate effect does not say, and what the data
   cannot show. The page.

Never: decomposes before the checks; states a cause the data cannot show; reports a share it did
not count; a personal column is never a segment.

### 3. `number-reconcile`: two numbers that should agree

When: two systems, reports or extracts of the same figure differ and the rows behind both are
available.
Input: the rows behind each, the window, the key, the amount and date columns on each side.

Steps:
1. **Pin and reproduce** both numbers (`measure.py`).
2. **Profile** both sides: key uniqueness, nulls, slice columns.
3. **Account for the gap** with `reconcile.py`: keys only on one side, filters, duplicates, time zones,
   timing, rounding, value differences, per bucket, adding up exactly. Slices show where it sits.
4. **Narrow** further where a bucket has a dominant slice.
5. **Say** what each bucket is, which are expected and which are real, and the exact amount left
   unexplained. The page.

Never: leaves part of the gap out; says which number is right unless a row or a definition does.

### 4. `report-review`: the report's counting, before it goes out

When: before an analysis or report with its SQL or notebook and its numbers goes out.
Input: the report folder and a folder of sample data.

Steps:
1. **Claims:** every number and comparison in the report, with file:line.
2. **Places to read:** `report_check.py sql` (null-dropping filters, averages of averages, ratios, join
   multiplicity, window mismatches, partial periods, truncated axes), confirmed by reading each.
3. **Recount** every claim: `report_check.py data` (fanout, avg_of_averages, small_groups, simpson,
   windows) and `measure.py` for the rest.
4. **Findings** with file:line, the report's number and the corrected number, and whether the
   conclusion survives. The page.

Never: changes the report; reports a finding it did not read and count; shows a personal value.

## Scripts

All standard library, read-only, JSON on stdout. Exact arithmetic (fractions), columns and counts only.

| script | skills | what it does |
|---|---|---|
| `measure.py` (shared) | all four | Filters, window, one row per key, then a sum, count or ratio, exact. SQL null semantics, reports what each filter dropped. Shared counting code the other scripts import. Personal columns can be counted, never grouped on or echoed. |
| `data_profile.py` (shared) | all four | Shape, keys, overlaps, personal columns, as in `data-architect`. |
| `sql_inventory.py` (shared) | metric-spec, report-review | Cleans SQL (comments, strings) before reading, inventories tables, as in `data-architect`. |
| `metric_compare.py` | metric-spec | `find`: aliased expressions of a metric with their FROM, WHERE and statement, and where the name is mentioned. `compare`: each definition's number on the same data, and a walk from one to the next, each step priced, adding up exactly. |
| `decompose.py` | number-moved | Checks (late rows, missing and thin days, duplicates) and the decomposition: volume, mix and rate, new and gone segments, ratio mode, ranked drivers, what is explained and what is left. The sum of the effects is checked exactly. |
| `reconcile.py` | number-reconcile | Keyed diff of two extracts into buckets that add up exactly to the gap: only-in, filters, duplicates, time zone, timing, rounding, value differences. Slices show where the gap sits. Keys are never printed. |
| `report_check.py` | report-review | `sql`: places to read in SQL and notebooks. `data`: fanout, average of averages, small groups, Simpson's reversal, windows, each with the corrected number. |

Two limits, on purpose:
- SQL is read with the same cleaner as `sql_inventory.py`, not a parser: a hit is a place to read, not
  a finding, and `find` needs an alias on the expression.
- The numbers are computed from extracts in files. Sample size is a limit: what the sample does not
  hold, the page says it could not check.

`tools/sync_shared.py` gets a `measure.py` marker.

## Renderer (`shared/`, changes every pack's pages)

One `chart` block, inline SVG computed in Python, kinds `bar`, `line`, `waterfall` and `heatmap`:
same JSON gives the same HTML, every value escaped, nothing fetched, no library. Validation errors name
their JSON path, and a waterfall whose totals do not match the running sum is rejected. Each mark
has a `<title>` tooltip and the chart's data is also listed as a table, for readers without the
drawing and for print. Colours follow the dataviz method for the dark plate: six categorical hues
validated against the plate surface (contrast and colour-blindness), a one-hue sequential heat ramp,
thin marks, text in the page's text tokens, a legend for two or more series, end and tip labels used
sparingly. Pages of other packs change only in the shared CSS: checked by rendering the existing
examples before and after and comparing everything but the `<style>`.

## Fixture: `fixtures/acme-sales/` (all fictional)

Acme Home Goods: a home-goods retailer with a web shop and six stores, with a small dbt project and
a report folder. `files/` + `history.py` as the other fixtures, `extras/data/` (orders, ledger, order
promotions, sessions, customers) generated by a seeded `make_data.py` kept beside them. Personal columns
are present and never shown.

Planted, and recorded as importable constants in `tests/test_fixture_acme_sales.py`:
1. a revenue change caused mostly by mix: EUR -10,610.00, exactly volume +960.00, mix -11,160.00,
   rate -410.00;
2. one day of partly late data: EUR 4,200.00 on 27 October arrived after the Monday run, so the
   reported fall of EUR 14,810.00 is EUR 4,200.00 too big;
3. two systems differing by EUR 1,506.00 from known causes that add up, with EUR 35.00 unexplained;
4. duplicates, in the ledger (a posting run twice) and through a join;
5. a filter that silently drops rows: `region <> 'unknown'` and 30 NULL-region rows;
6. a wrong denominator: orders over logged-in sessions;
7. an average of averages across stores;
8. a partial period: 24 days of September against all of October;
9. a small sample: a store with 6 orders ranked first;
10. a Simpson's reversal between devices;
plus a chart whose axis starts at 70,000, and two conflicting definitions of net revenue. A
clean query sits in the report folder to catch false alarms.

`docs/questions/` holds the question for each skill.

## Evals (`claude plugin eval`)

1. **metric-spec-finds-conflict:** both numbers or the gap, at least two differences, a definition.
2. **moved-rules-out-late-data:** the late day, the corrected fall, no stated cause.
3. **moved-splits-mix-exactly:** volume, mix and rate within a euro.
4. **reconcile-accounts-for-gap:** the gap, the causes that add up, the unexplained part.
5. **review-finds-planted:** at least 6 of 8 with file and corrected number.

Each case has a `skill-fired` grader. Evals run only when Stefan asks.

## Other

- `roles/data-analyst.md`, `plugin.json`, the marketplace entry, the expected list in
  `tests/test_skill_files.py`, `pyproject.toml`, README section, CLAUDE.md.
- Real runs on the fixture: each skill run headless on a fresh build, a cheap call first to confirm
  the skill loads, under $12 in total; each page checked by hand and copied to `references/example.json`.
- `facts` on `metric-spec`, the only page in this pack that decides something.

## Decisions (Stefan, 2026-11-10, in the brief)

1. Four skills as above, scripts standard library only, read-only, JSON on stdout.
2. A personal value never reaches the output: columns and counts only.
3. A `chart` block in the renderer, kinds `bar`, `line`, `waterfall`, `heatmap`, dark only.
4. The fixture plants the listed effects, each with an exact number recomputed in its test.
