# Plan: pack `software-architect`

Status: Stefan said go on 2026-11-09. The choices made without him are at the end.

## Goal

A pack for the person responsible for a system's structure. It decides what shape a system should
have, draws it in C4 from a brief or from the code, measures what is wrong with an existing
structure, and plans how to get from today's shape to the target in safe steps.

Out of scope:
- single-change questions (`impact`), bugs (`bug-hunt`), tests (`test-gap`): the `software-engineering` pack;
- generic ADR text and system-design frameworks: `engineering:architecture`, `engineering:system-design`;
- where it runs and what it costs: `cloud-architect`.

Community C4, arc42 and ADR skills exist as text or LikeC4 templates. Ours differs by measuring: the
structure and its problems come from the code and the git history, and end in a clickable page.

## Skills

### 1. `arch-style`: what shape it should be

A ladder ruled out against the brief, simplest first: one deployable, a modular monolith, serverless
functions, a few services, services with an event backbone, microservices. Steps as in `ai-pattern`
and `data-platform`: frame, ask what flips it, `style_rules.py`, weigh what is open (can this team run
it, consistency, change independence, operations, cost), name the binding constraint, what would
change it, acceptance criteria as measurable fitness rules, ADR draft.

Never: proposes services where a modular monolith passes; microservices without several teams and
people to run them.

### 2. `arch-c4`: the system, drawn

From a brief or from the code: context, containers, components as nested boxes with a level switch.
`containers.py` finds what runs (Dockerfiles, compose, project files, entry points, internal URLs,
settings by name), `code_graph.py` finds the components. Flows traced hop by hop; `c4_check.py` checks
the drawing.

Never: draws a box or link from code as checked unless it was read; quotes a setting's value.

### 3. `arch-review`: what is wrong with the structure

**Changed 2026-11-10:** `arch-review` now reviews design documents only, before a system is built, with its own
`design_inventory.py`; the measurement of existing code described below moved into the software-engineering skill
`code-audit`. See [code-audit.md](code-audit.md). The rest of this section is the original plan.

`code_graph.py --git`: cycles, layer breaks, fan-in and fan-out, instability, files that always change
together, hot spots (change rate × size), modules only one person touches. `containers.py`: services
sharing a store, synchronous loops. Then what a script cannot see, checked against quality-attribute
scenarios. Findings with file:line, flagged on the drawing.

### 4. `arch-evolve`: from today to the target

The current shape measured, the target from `arch-style` or the user, then steps that each leave the
system working: what changes, what stays, how it is verified, how it is undone. Today, each stage and
the target as variants of an `architecture` block. An ADR per decision. Never a big-bang rewrite
without saying why nothing smaller works.

## Scripts

Standard library, read-only, JSON on stdout.

| script | skills | what it does |
|---|---|---|
| `code_graph.py` (shared) | arch-c4, arch-review, arch-evolve | Module graph for C#, Python, TypeScript/JavaScript, Java and Go. Fan-in, fan-out, instability, cycles, layer breaks (`--layers`). `--git`: change coupling, hot spots, authors. Other languages are counted as not covered. |
| `containers.py` (shared) | arch-c4, arch-review, arch-evolve | What runs: Dockerfiles, compose services and `depends_on`, images recognised as stores or brokers, .NET web projects, package and pyproject entry points. Internal URLs between services, tables written by more than one deployable. Settings by name, never values. |
| `style_rules.py` | arch-style | The hard rules of the ladder. Never chooses. |
| `c4_check.py` | arch-c4 | A person or outside system inside the system, a container without technology, a link without a label, a box nothing touches, a level that opens nothing. |

## Renderer

**`nested` block,** reused by `cloud-architect`: boxes inside boxes.

```json
{"type": "nested", "title": "Acme Logistics",
 "levels": [{"id": "context", "label": "Context", "open": []},
            {"id": "containers", "label": "Containers", "open": ["system"]},
            {"id": "api", "label": "Inside the API", "open": ["system", "api"]}],
 "boxes": [{"id": "system", "label": "Logistics", "kind": "service", "tech": "", "note": "", "details": [], "flag": "warn"},
           {"id": "api", "label": "API", "parent": "system", "kind": "service", "tech": ".NET"}],
 "links": [{"from": "web", "to": "api", "label": "JSON/HTTPS"}],
 "flows": [{"id": "book", "title": "Book", "variants": ["containers"], "steps": [{"from": "web", "to": "api", "text": "…"}]}]}
```

A level says which boxes are open. A link between closed boxes' children is lifted to what is visible
at that level. It is drawn by the same page script as `architecture`: a level is a variant, so cards,
flows, deep links and `reach` work without new script. Layout is computed in Python, recursively, with
the existing layering helpers.

## Fixture: `fixtures/acme-logistics/` (all fictional)

A .NET API, a TypeScript web app and a Python worker, with a git history, two briefs (one where the
right answer is a modular monolith or plain monolith, one that needs a few services with events and
rules out microservices) and eight planted structural problems: a cycle, a layer break, a dumping
ground, the same rule written twice and always changed together, a shared table, a hot spot, a
synchronous loop between services, a module only one person touches.

## Evals

style-does-not-overbuild, style-names-the-constraint, c4-from-code, review-finds-planted (at least 6
of 8, no file changed), evolve-safe-steps. Each with a `skill-fired` grader. Run only when Stefan asks.

## Order

M1 fixture. M2 renderer. M3 scripts and tests. M4 skills and examples from headless runs (about $10).
M5 evals written. M6 README, marketplace, role starter, CLAUDE.md. Green at the end.

## Choices made without Stefan

1. Names: `software-architect`; `arch-style`, `arch-c4`, `arch-review`, `arch-evolve`.
2. Thresholds in `style_rules.py`: at least 3 teams and 3 platform engineers for microservices; a part
   must take 10 times the load of the rest to count as scaling on its own.
3. Languages: C#, Python, TypeScript/JavaScript, Java, Go, because those cover Stefan's work; the
   others are reported as not covered rather than guessed.
