# A workflow chain

How a workflow skill runs its steps. Each step is an ordinary skill run (see [skill-run.md](skill-run.md)); the
hand-over between steps is the page JSON in the pages folder, never the prose.

```mermaid
sequenceDiagram
  actor U as Person
  participant W as Workflow skill
  participant C as scripts/chain_status.py
  participant K as Step skill
  participant P as Pages folder
  participant R as scripts/render_page.py

  U->>W: /workflows:NAME and its input
  W->>C: --folder PAGES/REPO --steps a,b,c --since today
  C->>P: newest page of each step, checked with render_page.py
  C-->>W: each step's page, date, verdict, findings and open items
  loop each step in order
    alt a valid page from today exists
      W->>P: reuse it
    else
      W->>K: run the step with the Skill tool
      K->>P: the step's page JSON and HTML
    end
    W->>P: read the step's page JSON (facts, findings, tables)
  end
  W->>C: run again: is the chain done by its rule?
  W->>R: the chain's page JSON, --md for the note, then the page
  R->>P: NAME-DATE.md and NAME-DATE.html
  W-->>U: what was found, what is still open, done or not
```
