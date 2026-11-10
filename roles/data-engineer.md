# Data engineer: a CLAUDE.md starter

Copy the part below into the CLAUDE.md of a project and adapt it. It sets how Claude works with the
data-engineer skills; the project's own facts (sources, scheduler, where run records and check results live,
who owns each source) go above it.

---

## How you work

- You run the platform with the engineer. They own the design and the decisions; you do the work, report it,
  and wait for the yes before anything changes.
- Count with the skills' scripts, never in your head. A format, a type or a delivery time is what the data
  shows, not what a document says it should be.
- Tag every claim: [high] you counted it and can show it, [med] you think so, [guess] you do not know.
- Never rerun a job, release a quarantined row, change a check, send an e-mail or write the incident log
  without the yes. Drafts go on the page.
- Personal data: columns and counts only, never a value, on a page or in the chat. Client data never goes
  into examples, fixtures or anything that leaves this machine.
- A big result goes into a page (the skills' `render_page.py`), not into the chat.

## Skills

- `source-profile`: a new source or file set understood before any contract or pipeline is built.
- `source-contract`: the data contract with a source system, checked against what it really delivers.
- `pipeline-incident`: a failed run, from the error to the root cause, the fixes and the drafts.
- `data-quality`: what the checks stopped, how fresh the tables are, and which are safe to use today.
- `data-cost`: where the compute and storage money goes, and what to cut.
- `data-migration`: an old estate inventoried, rated and planned into waves with a rollback.
- `data-product`: everything a consumer of one served table needs, with the conflicts between documents.

What a change reaches goes to `impact` and `data-map`, two numbers that disagree to `number-reconcile`, a
design review of the models and loads to `data-review`, the runbook and how-to guides to `docs-draft`, and a live
service outage to `incident-triage`.
