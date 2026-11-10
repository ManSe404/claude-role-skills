---
name: cloud-map
description: Draws cloud infrastructure from Terraform, Bicep, ARM, CloudFormation or a saved export as nested boxes, with request flows, what the internet reaches and drift between code and account.
when_to_use: Use when you inherit cloud infrastructure or must explain it, from infrastructure code or a read-only export, with no cloud login.
argument-hint: "[repository] [saved export]"
hooks:
  PreToolUse:
    - matcher: "Skill|Read|Write|Edit|MultiEdit|NotebookEdit|Bash|WebFetch|WebSearch"
      hooks:
        - type: command
          command: 'for d in "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PROJECT_DIR/.claude" "$HOME/.claude"; do [ -f "$d/skills/cloud-map/scripts/guard.py" ] && exec python3 "$d/skills/cloud-map/scripts/guard.py" pre cloud-map; done; true'
---

# Cloud map

The job: one page that shows the cloud infrastructure that exists: what is there, where it sits, how a request
crosses it, what the internet can reach, and where the code and the deployment differ. It changes nothing. For the
software inside the boxes use `arch-c4`; for a data platform use `data-map`.

Input: a repository, a saved export, or both. Default: the current repository.

## Steps

1. Inventory: `python3 "${CLAUDE_SKILL_DIR}/scripts/cloud_inventory.py" REPO` to your scratchpad, adding
   `--compare EXPORT.json` when there is an export, or `--from-export EXPORT.json` when there is no code. Read
   `references/cloud/<provider>.md` for each provider in `providers`.
2. A live read only when asked for, and only after a yes: say which account you would read and what the command
   collects, ask, and wait. Then run the read-only export command from the provider file yourself, save the JSON in
   your scratchpad, and go back to step 1. Never log in, change anything, or run anything but that export.
3. Read the code at every resource you draw. A box or link you did not read is tagged [guess]. `unresolved` lists what
   the script could not follow (repeated resources, dynamic names, remote modules, unknown types): open those places
   and say what stays unknown.
4. Draw a `nested` block with the provider file's nesting and drawing rule. Keep to about 40 boxes: group what adds
   nothing. Each box carries its kind in text and, in its card, name, type, file:line and what the attributes say.
5. Flows: two to four requests that matter most, traced from the entry to the data, each step tied to the attribute
   or setting that says so. The script's references are places to look, not proven requests.
6. Reach: use `exposure` for a `reach` from the internet box: `from` the internet, `stops` the firewalls and private
   boundaries, `targets` the data stores and compute. Say what each public resource is open to and why.
7. Drift, when an export was given: only in code, only in the export, and what could not be compared.
8. Write the page JSON, with `facts`, render it, and say where to open it, with a link that opens the drawing
   (`page.html#variant=<level>`).

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format, including `nested`, `reach` and
`facts`, and [references/example.json](references/example.json) for a filled page.

Sections in this order: The estate (a `nested` block with the provider's levels, flows and `reach`), What is there
(table: name, type, category, placed in, file), What the internet can reach (table: resource, how, what stops it),
Code and deployment (tables: only in code, only in the export, not compared; omit when there is no export), What could
not be read (table: kind, resource, file, what stays unknown), Open questions. Stats on top: resources, public
resources, stopped at a boundary, unresolved, drift. The verdict says in two sentences what this estate is and what the
internet can reach that it should not.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both files in
`${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<project>/cloud-map-<YYYY-MM-DD>.*`. Write the page in the language of the
request; Serbian pages in Latin script.

## Reads

- the repository and any saved export, read-only; never state files or variable files with real values

## Writes

- the page and its JSON, outside the repository

## Never

- Never logs in, deploys or changes anything; a live read happens only after a yes, and only the read-only export.
- Never draws a box or link as checked unless it was read; otherwise it is [guess].
- Never shows a secret: the script replaces values that look like secrets with a marker; settings are named, not quoted.
