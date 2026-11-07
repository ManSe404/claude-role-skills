# Page format

Every skill that ends in a page writes one JSON file, then draws it:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html
```

You decide the content; the script decides the look. It escapes every value, checks the shape and
prints each problem with its JSON path, so fix the JSON and run it again. Never hand-edit the HTML.

## Where the page goes

Outside the repo: `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<repo name>/<skill>-<YYYY-MM-DD>.json`
and the `.html` beside it. Keep the JSON: a later run can compare against it. Say the HTML path at the end.

## The page

```json
{
  "skill": "codebase-map",
  "title": "acme-orders, mapped",
  "subtitle": "One sentence: what this page answers.",
  "meta": {"repo": "acme-orders", "commit": "3f2c1aa", "date": "2026-11-06"},
  "verdict": {"text": "The answer in one or two sentences.", "tone": "ok | warn | bad | info"},
  "stats": [{"label": "Python lines", "value": 1240, "note": "src only", "tone": "info"}],
  "sections": [{"id": "entry-points", "title": "Entry points", "intro": "optional", "blocks": []}]
}
```

`skill`, `title` and `sections` are required. `verdict` and `stats` go on top: the reader gets the
answer before the detail. Keep stats to the 3–6 numbers that matter.

## Text

Every text field accepts `` `code` ``, `**bold**`, `[label](https://…)` and the confidence tags
`[high]` (checked, can show it), `[med]` (likely) and `[guess]` (not checked). Blank lines split
paragraphs. Tag every claim the scripts did not count.

## Blocks

Each block may have a `title`.

| type | fields |
|---|---|
| `text` | `text` |
| `callout` | `text`, `tone`: ok, warn, bad, info |
| `list` | `items`: [string], `ordered`: bool |
| `table` | `columns`: [string], `rows`: [[cell]], `align`: [left, right, center] (optional; number columns align right by themselves) |
| `kv` | `items`: [[label, value]] |
| `code` | `code`, `where` ("src/x.py:12"), `start` (first line number), `highlight`: [line numbers] |
| `steps` | `items`: [{`title`, `text`, `where`}] for a flow or a timeline |
| `findings` | `items`: [{`severity`: high, medium, low, info; `title`; `where`; `evidence`; `fix`; `status`: open, accepted, declined, fixed; `reason`}] |
| `graph` | `nodes`: [{`id`, `label`, `note`, `group`}], `edges`: [{`from`, `to`, `label`}] |

A cell is a string, a number or null. Findings are shown high first. A declined finding needs
its `reason`: it stays on the page, it is never dropped.

Graph groups: `entry` (where it starts), `module`, `boundary` (public surface: endpoint, CLI,
published API, message), `data` (database, file, queue), `external` (outside the repo), `test`,
`changed` (the change itself), `affected` (needs a change), `safe`, `unknown` (not checked).
The graph is drawn left to right; edges that close a cycle are dashed. Keep it under ~40 nodes:
group modules rather than draw every function. The page also lists the edges as a table.

## What the reader can do

A click on a node traces it: what leads to it turns purple, what it reaches orange, the rest
fades; Esc clears. A link ending in `#node=<id or label>` opens the page traced, so give stable,
readable node ids (`importer`, `order_total`) and name them when you point the user at a page.
Tables with 8 or more rows get a filter box, and code blocks a copy button.
