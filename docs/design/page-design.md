# Page design

Every skill ends in a page drawn by `shared/render_page.py`, so this is the design of every skill's output. How the
page is produced is in [architecture/overview.md](../architecture/overview.md); the JSON format a skill writes is
[shared/page-format.md](../../shared/page-format.md).

## The look

A hive: a dark amber ground with a faint honeycomb and a warm glow at the top, honey as the one accent, panels with
a honey edge. Counters, tags and the boxes of every diagram are hexagons, the cells of the comb; a flowchart draws
its start and end as capsules. Bricolage Grotesque for text and JetBrains Mono for labels, both inlined with Latin
Extended for Serbian, under the SIL Open Font License ([THIRD-PARTY-NOTICES.md](../../THIRD-PARTY-NOTICES.md)). In
graphs, honey marks what leads to a change and sky blue what it reaches; the chart colours pass the dataviz checks
against the panel. The page is dark only.

The CSS and the shapes live in `shared/render_page.py` (the CSS, and `_hex_plate` for the hexagons), so every skill's
page changes with it.

## What the reader can do

- **Graphs are clickable.** A node shows what leads to it and what it reaches, and a link such as
  `page.html#node=importer` opens the page traced.
- **Long tables** get a filter box, **code blocks** a copy button.
- **Architecture:** the `architecture` block adds a panel per component, flows that play step by step, variants and a
  trust view, with links such as `#flow=order&step=3`.
- **Decisions:** the `decision` block shows options against factors with the reason each one fell.
- **Data models:** the `model` block draws tables with their keys and opens each one's columns; a `reach` view shows
  how far personal data travels.
- **Nested boxes:** the `nested` block draws boxes inside boxes with zoom between levels.
- **Processes:** the `flowchart` block draws a process with branches: start, steps, decisions with their answers, end.
- **One place for all pages:** `render_page.py --index FOLDER` writes an index of every page under a folder.
- **A note for a vault, a wiki or a pull request:** `--md` writes the same JSON as a Markdown note, each drawing
  replaced by its table. The text-only skills, listed in `shared/page-format.md`, write the note by default.

The page reads the same without its script: the script only adds the interactions above.

## Checking a change

Render an `example.json` from a skill's `references/` and look at it; headless Chrome `--screenshot` does. The
`architecture` page of `ai-architecture` is the one with the most to try: click a component, press Play on a flow,
switch between the routed workflow and agentic RAG, turn on the trust view.

## Open

- `shared/page-format.md` ("What the reader can do") says a traced node turns what leads to it blue and what it
  reaches orange; the renderer's CSS draws upstream edges in honey (`--accent`) and downstream ones in sky blue
  (`--down`), as described above.
