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

## Several pages, one header

When a run writes more than one page (several repositories, several skills on one repo), link them so the
reader can switch: write a site file and render the set. Every page gets the same header on top, with its own
link marked.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" --site SITE.json
```

```json
{
  "title": "Acme platform",
  "pages": [
    {"label": "Overview", "page": "codebase-map-2026-11-06.json"},
    {"label": "API", "group": "Orders", "page": "../acme-orders/codebase-map-2026-11-06.json"},
    {"label": "UI", "group": "Orders", "page": "../acme-orders-ui/codebase-map-2026-11-06.json"}
  ]
}
```

- `page` is a page JSON, relative to the site file. Each HTML is written beside its JSON and the script works
  out the links, so you never write an `href`.
- The first page is the home of the set. Keep `label` short. `group` is optional: neighbouring pages with the
  same group share one caption.
- If any page is invalid or missing, nothing is written and each problem is printed.
- Keep `SITE.json` beside the first page. To change one page later, run `--site` again: a page rendered on its
  own loses the header.
- Agents working in parallel each write only their own page JSON. Whoever started them writes the site file last.

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
answer before the detail. Keep stats to the 3–6 numbers that matter. `facts` is optional, see below.

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
| `architecture` | `zones`, `components`, `links`, `flows`, `variants`, `reach`, see below |
| `model` | `areas`, `tables`, `relations`, see below |
| `nested` | `boxes`, `levels`, `links`, `flows`, `reach`, see below |
| `chart` | `kind`: bar, line, waterfall, heatmap; `categories` and `series`, or `items`, or `rows`, `columns` and `values`, see below |

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

A click on a node traces it: what leads to it turns blue, what it reaches orange, the rest
fades; Esc clears. A link ending in `#node=<id or label>` opens the page traced, so give stable,
readable node ids (`importer`, `order_total`) and name them when you point the user at a page.
Tables with 8 or more rows get a filter box, and code blocks a copy button.

## Reach

An `architecture` block may add `reach`, a second computed view: what starts at some components
and how far it gets. For a data platform, links point the way the data goes.

```json
"reach": {"label": "Personal data", "from": ["crm"], "stops": ["mask"], "targets": ["bi", "export"]}
```

The page walks the links forward only, from `from`. A `stops` component receives it and passes
nothing on (masking, a firewall). Every target reached is listed with the shortest path, and a
button draws it. `#reach=1` opens that view.

## Model

```json
{
  "type": "model",
  "title": "Sales",
  "areas": [{"id": "sales", "label": "Sales"}],
  "tables": [{"id": "fct_sales", "label": "fct_sales", "kind": "fact", "area": "sales",
              "grain": "one row per order line", "note": "one line", "flag": "warn", "history": "new row on change",
              "columns": [{"name": "order_id", "type": "bigint", "key": "pk", "note": "one line"},
                          {"name": "email", "personal": true, "mask": "hashed in gold", "history": "overwrite"}]}],
  "relations": [{"from": "fct_sales", "to": "dim_customer", "on": "customer_key", "cardinality": "n:1", "label": "bought by"}]
}
```

- `kind`: fact, dimension, bridge, hub, link, satellite, staging, table. `key`: pk, fk, bk (business key).
- `on` is a column both tables have, or `left=right`, several separated by commas. `cardinality`:
  1:1, 1:n, n:1 (the default), n:n. The many side is drawn on the left, an n:n in red.
- A box shows the name, kind, primary key and "+ N more columns". Keep to about 30 tables a block.

A click opens the table's card (grain, history, every column, what it joins to) and lights its
neighbours; Esc clears. Area buttons filter. `#table=<id>` and `#area=<id>` open that state. Without
the script, and in print, every card is listed under the diagram.

## Nested

Boxes inside boxes: C4 levels, or a cloud subscription down to a subnet.

```json
{
  "type": "nested",
  "title": "Acme Logistics",
  "levels": [{"id": "context", "label": "Context", "open": [], "note": "one line"},
             {"id": "containers", "label": "Containers", "open": ["system"]},
             {"id": "inside-api", "label": "Inside the API", "open": ["system", "api"]}],
  "boxes": [{"id": "system", "label": "Logistics", "kind": "service", "note": "one line"},
            {"id": "api", "label": "API", "parent": "system", "kind": "service", "tech": ".NET 8",
             "details": [["Fails how", "503"]], "flag": "warn"}],
  "links": [{"from": "web", "to": "api", "label": "JSON/HTTPS", "flag": "bad"}],
  "flows": [{"id": "book", "title": "Book a parcel", "variants": ["containers"],
             "steps": [{"from": "web", "to": "api", "text": "…"}]}]
}
```

- `parent` puts a box inside another. `kind` is an architecture `kind`; a box with open children is
  drawn as a frame around them.
- Each level lists the boxes that are `open`; a box shows when every box around it is open. Leave
  `levels` out to draw everything open in one view.
- Write links between the most specific boxes. At a level where an end is hidden inside a closed
  box, the link moves out to that box, and links that end up joining the same two boxes become one.
- A flow's `variants` are the levels it plays at; every step must be visible at those levels.
- It behaves like `architecture`: click a box for its card, step a flow, switch the level, and
  `reach` works the same. `#variant=<level>`, `#component=<id>` and `#flow=<id>&step=1` open a state.

## Chart

Data drawn as inline SVG, computed by the renderer: no library, nothing fetched, the same JSON always gives the same
drawing. Each mark has a tooltip (`<title>`), and the chart's data follows it as a plain table, for readers without the
drawing and for print. Every number and label is escaped.

```json
{"type": "chart", "kind": "bar", "title": "Change by driver", "unit": "EUR", "x_label": "Driver",
 "categories": ["Mix: premium", "Mix: value", "Volume"],
 "series": [{"name": "Effect", "values": [-7488, -3696, 960]}]}
```

- `kind: "bar"`: horizontal bars, the value at the tip. `categories` and `series`, up to 6 series as grouped bars.
  A value may be null or negative. Good for a ranked list; a single series needs no legend.
- `kind: "line"`: `categories` in time order, the same `series` shape, with an end label and a point every
  period. The axis starts at zero; `"zero": false` lets it start elsewhere and then the chart says so.
- `kind: "waterfall"`: `items` as `{"label", "value", "total": true}`. A `total` is a level; the other steps are
  changes. A total must equal the running sum of the steps before it, to the cent, or the page is not drawn. Use it for a
  change split into effects: the first period, each effect, the second period. Leave the totals out to chart
  only the effects, when they are small against the levels.
- `kind: "heatmap"`: `rows`, `columns` and `values` (one list per row, null for no data), for cohorts. Numbers show in
  the cells; `"show_values": false` hides them. `"scale": [0, 100]` fixes the range. One hue, darker for less.
- Optional on any kind: `unit` ("EUR", "%"), `x_label`, `y_label`, `caption` (text, with the usual inline
  marks), `places` (decimals shown; default none for whole numbers, two otherwise).
- Give a chart a `title`. Two series with different units do not belong on one chart: use two charts.

## Facts

`facts` sits at the top level of the page JSON and is not drawn. Other skills read it from the JSON
beside the page, so a later skill can join several pages. Fill it on every page that decides or maps
something, with what the page already says; leave out a list that has nothing to report.

```json
"facts": {
  "version": 1,
  "scope": "the data platform of Acme Foods",
  "regions": [{"name": "EU", "why": "residency"}],
  "data": [{"name": "customer contact", "class": "personal", "where": ["silver.customers"], "rule": "EU only"}],
  "components": [{"id": "lake", "label": "Lakehouse", "tech": "not chosen", "kind": "store"}],
  "costs": [{"item": "model calls", "monthly": 420.0, "currency": "EUR", "as_of": "2026-11-09", "source": "price list"}],
  "decisions": [{"title": "Platform", "chosen": "Lakehouse", "because": "files and images"}],
  "assumptions": ["one line each"],
  "open": ["one line each"]
}
```

A cost needs its date and source. `version` is 1.

Optional, for joining pages across specialties; leave them out when they do not apply:

- `region` on a component: where that one component runs, when it differs from the page's `regions`.
- `cloud` and `variant` on a cost: which cloud or variant a line belongs to, so alternatives are not
  added together. A line with "total" in its `item` stands for that page's cloud or variant.
- `budget` on the facts: `{"monthly": 6000, "currency": "EUR", "source": "the brief"}`. One currency.
- `specialists` on the facts: the skills that must run, written by `solution-brief`.
