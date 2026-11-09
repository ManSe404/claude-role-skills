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
| `decision` | `factors`: [string], `options`: [{`label`, `status`: chosen, viable, eliminated; `eliminated_by`; `why`; `cells`: [{`rating`: pass, weak, fail; `text`}]}] |
| `architecture` | `zones`, `components`, `links`, `flows`, `variants`, see below |

A cell is a string, a number or null. Findings are shown high first. A declined finding needs
its `reason`: it stays on the page, it is never dropped.

Graph groups: `entry` (where it starts), `module`, `boundary` (public surface: endpoint, CLI,
published API, message), `data` (database, file, queue), `external` (outside the repo), `test`,
`changed` (the change itself), `affected` (needs a change), `safe`, `unknown` (not checked).
The graph is drawn left to right; edges that close a cycle are dashed. Keep it under ~40 nodes:
group modules rather than draw every function. The page also lists the edges as a table.

## Decision

Options in rows, from the simplest up, factors in columns, one cell per factor. At most one option is
`chosen`; an `eliminated` option keeps `eliminated_by` (the factor or rule that ruled it out) and
`why`. The chosen row stands out and eliminated rows fade, but their reason stays readable.

## Architecture

```json
{
  "type": "architecture",
  "title": "Support assistant",
  "zones": [{"id": "app", "label": "Application"}],
  "components": [{"id": "api", "label": "Assistant API", "zone": "app", "kind": "service",
                  "tech": "FastAPI", "note": "one line", "details": [["Fails how", "503, contact form"]],
                  "side_effect": false, "flag": "warn", "variants": ["workflow"]}],
  "links": [{"from": "customer", "to": "chat", "label": "question", "trust": "untrusted"}],
  "flows": [{"id": "order", "title": "Order status", "steps": [{"from": "chat", "to": "api", "text": "…"}]}],
  "variants": [{"id": "workflow", "label": "Routed workflow", "note": "one line"}]
}
```

- Zones are columns, left to right in the order given: typically user and channel, application,
  AI layer, knowledge, systems and people, operations. Components stack inside their zone.
- `kind`: user, channel, service, model, retrieval, store, tool, system (outside), human, guard,
  ops. `side_effect: true` marks what changes the world (sends, writes, pays). `flag`: warn or bad
  marks a problem spot, for a review.
- Links point the way the request goes (caller to callee). `trust: "untrusted"` marks a link that
  carries text nobody vetted: the user's message, a fetched page, a document, a tool's output.
- The page works out where untrusted text can travel. It follows each link the way the request
  goes, and back from a service, model, retrieval, store, tool, outside system or guard to its
  caller, because the caller reads what comes back. It stops at a person (`human`, `user`). Every
  side effect it reaches is listed once, with the ways in and the shortest path. A side effect
  behind a human step is not reached.
- `variants`: the first is the default. A component, link or flow with `variants` exists only in
  those, and a link or a flow step may only join components that exist in its variants.
- Keep labels short: a box shows about 18 characters, a link label 14. Full text goes in `note`,
  `details` and the flows.

The reader clicks a component for its card (zone, kind, tech, details, what it sends to and
receives from), plays or steps a flow (‹ ›, the arrow keys), switches the variant and turns on the
trust view. Links open a state: `#component=api`, `#flow=order&step=3`, `#variant=agentic`,
`#trust=1`, combined with `&`. Without the script, and in print, every card, flow and variant
note is listed under the diagram.

## What the reader can do

A click on a node traces it: what leads to it turns purple, what it reaches orange, the rest
fades; Esc clears. A link ending in `#node=<id or label>` opens the page traced, so give stable,
readable node ids (`importer`, `order_total`) and name them when you point the user at a page.
Tables with 8 or more rows get a filter box, and code blocks a copy button.
