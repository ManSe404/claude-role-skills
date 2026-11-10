---
name: cloud-review
description: Use before a release, an audit or a take-over of cloud infrastructure, from Terraform, Bicep, ARM templates or CloudFormation in a repository or a saved read-only export, to review it against the provider's Well-Architected pillars, with problems tied to file:line or a resource, marked on a drawing, with what to fix first.
argument-hint: "[repository] [saved export] [brief or requirements]"
---

# Cloud review

The job: find what is wrong with cloud infrastructure, prove each problem from the code or the export, and say what
to fix first. It changes nothing. For the software's structure use `arch-review`; for a data platform, `data-review`;
for an AI solution, `ai-review`.

Input: a repository, a saved export, or both, and any requirements or brief. Default: the current repository.

## Steps

1. Read [references/review.md](references/review.md): each family of problems, how to confirm it and how to fix it.
   Read `references/cloud/<provider>.md` for each provider: the pillars and what public means there.
2. Inventory with hits: `python3 "${CLAUDE_SKILL_DIR}/scripts/cloud_inventory.py" REPO --checks` to your scratchpad,
   adding `--compare EXPORT.json` when there is an export.
3. Confirm every hit by reading it. A hit is a place to look: one that is fine is dropped with a reason in your notes;
   one that needs the requirements to judge is judged against them, not against a rule of thumb. Say which hits you
   read and which you confirmed.
4. Walk what a script cannot see: the requirements or brief against what the code does (a zone demanded, a region
   promised), what `unresolved` hides, secrets handled badly in ways that do not look like secrets, drift when an
   export exists, and two or three failure scenarios ("one zone is lost during a sale").
5. Findings: severity by what the problem can cost, the provider's pillar, file:line or the resource, the evidence, the
   fix, and what makes the fix safe. Not all findings are high: say what is low and why.
6. Draw the drawing: a `nested` block as in `cloud-map`, with each problem's box or link flagged (`flag`: warn or bad)
   and the finding named in its details.
7. Order: what is open to the internet right now first, then what loses data or a zone, then what makes it hard to run,
   then the rest. Say what you would leave alone and why.
8. Write the page JSON, with `facts`, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format, including `findings`, `nested`
and `facts`, and [references/example.json](references/example.json) for a filled page.

Sections in this order: Findings (a `findings` block, high first, each with file:line or a resource, evidence and
fix), Where they sit (a `nested` block with the problem spots flagged), By pillar (table: pillar, findings, highest
severity, the one to fix first), Code and deployment (table, when there is an export; omit otherwise), Order of the
fixes (list), What to leave alone (list), What this review did not cover (list), Open questions. Stats on top: findings
by severity, hits confirmed of hits read, pillars affected, public resources. The verdict says in two sentences whether
this estate can go to production and what it most needs.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both files in
`${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/cloud-review-<YYYY-MM-DD>.*`. Write the page in the language of the
request; Serbian pages in Latin script.

## Reads

- the repository, any saved export and the requirements, read-only; never state files or variable files with real values

## Writes

- the page and its JSON, outside the repository

## Never

- Never changes a file and never deploys. A live read happens only after a yes, as in `cloud-map`.
- Never reports a finding it did not read: a hit alone is a place to look.
- Never shows a secret: the script replaces values that look like secrets with a marker. A secret finding names the
  setting and where it is, never its value. Never opens a `.env`, state or variable file.
