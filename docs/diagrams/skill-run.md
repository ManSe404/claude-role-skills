# A skill run

What happens from a request to the page, with the guard hook on every tool call during the skill's turn. The data
skills (guard called with `personal`) also pass Bash and Read output through the guard after the call.

```mermaid
sequenceDiagram
  actor U as Person
  participant CC as Claude Code
  participant G as scripts/guard.py (hook)
  participant S as the skill's scripts
  participant R as scripts/render_page.py
  participant P as Pages folder

  U->>CC: a request, or /PACK:SKILL
  CC->>CC: pick the skill by its description and when_to_use, load SKILL.md, register its hooks
  loop every tool call in the turn that invoked the skill
    CC->>G: PreToolUse (Skill, Read, Write, Edit, Bash, WebFetch, WebSearch, ...)
    G-->>CC: nothing, ask the person, or deny
    CC->>S: python3 scripts/NAME.py ...
    S-->>CC: JSON on stdout: the counts
    opt skills with the personal guard
      CC->>G: PostToolUse (Bash, Read)
      G-->>CC: the output with e-mail addresses, IBANs and JMBGs removed
    end
  end
  CC->>P: write SKILL-DATE.json
  CC->>R: PAGE.json -o PAGE.html, and --md -o PAGE.md for a note
  R->>P: the page and the note, one self-contained file each
  CC->>R: --index on the pages folder
  R->>P: index.html
  CC-->>U: the verdict and where to open the page
  U->>CC: next message: the guard steps aside, normal permissions apply
```
