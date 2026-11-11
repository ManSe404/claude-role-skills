# Container view

The parts of the repository, how a pack reaches Claude Code and how the shared files reach each skill. Every box is a
folder or file in the repository, except Claude Code and the pages folder.

```mermaid
flowchart LR
  user["Person using Claude Code"]
  cc["Claude Code"]
  pages[("Pages folder<br/>CLAUDE_PAGES_DIR, default ~/claude-pages")]

  subgraph repo["claude-role-skills repository"]
    market[".claude-plugin/marketplace.json<br/>one entry per pack"]
    subgraph pack["plugins/PACK/"]
      manifest[".claude-plugin/plugin.json<br/>name, version, dependencies"]
      skill["skills/SKILL/<br/>SKILL.md, scripts/, references/, assets/fonts/"]
      evals["evals/CASE/<br/>case.yaml, prompt.md, fixture.sh, graders/"]
    end
    shared["shared/<br/>render_page.py, guard.py, page-format.md, fonts/,<br/>cloud/, the shared scripts"]
    sync["tools/sync_shared.py"]
    fixtures["fixtures/acme-*/<br/>build_fixture.py"]
    tests["tests/<br/>pytest"]
    tools["tools/selection_check.py<br/>tools/eval_table.py"]
    roles["roles/<br/>CLAUDE.md starters"]
  end

  user --> cc
  cc -- "/plugin marketplace add, /plugin install" --> market
  market --> manifest
  manifest --> skill
  cc -- "picks by description and when_to_use,<br/>then loads the body and the hooks" --> skill
  skill -- "page JSON, HTML and note" --> pages
  shared --> sync
  sync -- "copies a file into every skill<br/>whose SKILL.md names it" --> skill
  fixtures -- "fixture.sh builds the project<br/>an eval case runs on" --> evals
  tests -- "scripts, renderer, guard,<br/>fixtures, skill files" --> shared
  tests --> fixtures
  tools -- "loads every pack,<br/>one model call per prompt" --> cc
  user -. "copies into a project" .-> roles
```
