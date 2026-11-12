# Kinds of document

Each kind answers its reader's questions in a fixed order. The first sentence is the one that reader needs
in the first thirty seconds. Every command is shown as it runs; every name comes from the facts; what the
code does not show is tagged [guess] or left to a person.

## README: a contributor or a user meets the project

1. What it is and who it is for, in two sentences, from the manifest description and the entry points.
2. Start in five minutes: install, the first command that shows it works, what to expect. From the entry
   points, the CI steps and the Makefile; a command that CI does not run is marked as not verified.
3. Run: every command and subcommand with its flags and their help text, as the code defines them.
4. Configuration: every setting by name, its default, where it is read (environment, file), never a value
   that looks like a secret.
5. Test and check: the commands CI runs, verbatim.
6. Layout: the top-level folders and what each holds, from the code, one line each.
7. Where to go next: the documents that exist, linked.
8. Contributing and licence: from the files that exist; otherwise left to a person.

## Runbook: the on-call engineer at 3 a.m.

1. When to use this runbook: the symptom, the alert or the request, in the words the reader will see.
2. What they need first: access, credentials by name only, the host or the environment, the command to
   confirm they are on the right system.
3. Check: the commands that show the state (a health route, a log path, a status command), each with what a
   good answer looks like.
4. Do: the steps, one command each, in order, with what each one changes and how long it takes. A step that
   changes data says so before the command.
5. Verify: the command and the expected answer that show it worked.
6. Undo: how each step is taken back, in reverse order; a step that cannot be undone is marked.
7. Escalate: who and how, left to a person unless a document names them.
8. Known causes: from the git history and the existing documents, each with its signature in the log.

## API reference: a developer calling the service

1. How to reach it: base URL by name, authentication by scheme, never a token.
2. Every route from the facts: method and path, what it does, the request fields with their types, a
   request and a response taken from the code or its tests, the error responses the code returns.
3. Limits: paging, rate limits, sizes, when the code has them; otherwise left to a person.
4. Versioning and changes: from the documents that exist; otherwise left to a person.

## Onboarding: the first week of a new engineer

1. What the system does and for whom, in three sentences.
2. Setup: the commands, in order, with what each shows when it works; the settings to fill in, by name.
3. The map: the parts and how they connect, from a `codebase-map` or `arch-c4` page when one exists, from
   the entry points and the import graph otherwise; each part with its folder.
4. Common tasks: three to five things a newcomer does in the first month (add a command, change a setting,
   run the tests, read the logs), each with the files involved.
5. Who to ask: left to a person; the document names the roles, not the people.
6. Reading list: the documents that exist, in the order to read them.

## Architecture document: a team or a reviewer deciding something

1. Context: the system in one paragraph, its users and the outside systems it depends on.
2. The design: containers and components from an `arch-c4` page or the code, with the technology of each.
3. Decisions: the ADRs that exist, one line each, linked; a decision with no ADR is listed as undocumented.
4. Data flow: the two to four requests that matter, hop by hop, from the code.
5. Qualities: the goals with a number where a document gives one; without a number, left to a person.
6. Open questions: what the code and the documents cannot answer.

## Docs set: the whole layout of a repository

1. Inventory what exists: every Markdown file, what kind it is, and where it belongs in
   [repo-layout.md](repo-layout.md); dated status and results are listed for the owner's notes, not moved in.
2. The index first: `docs/README.md` with the reading order and each document's status and last checked date.
3. Then only what applies to the repository's size, each part in the order its own kind gives:
   `product/vision.md` in a larger project, `architecture/overview.md` with `diagrams/`, `reference/codebase.md`,
   `guides/setup.md` and `guides/development.md`, `roadmap.md` while work continues, `adr/` when decisions exist.
4. In a larger project (a product, a service, a library others build on, client work), `product/vision.md` is
   the introduction and comes first in the reading order, with these sections in order:
   the problem or opportunity (what is wrong or missing today, for whom, and the case, number or source that
   shows it), how we solve it (the idea and what the user does differently after), why this way (the options
   that lost, linked to `adr/`), for whom, what it is not, how we know it works (the measure, never a dated
   value). A section the code and the documents cannot answer is left open for the owner, not filled in.
5. The README shrinks to what it is (in a larger project: the problem and the solution in one sentence each,
   with a link to `product/vision.md`), how to run it, and the link to `docs/README.md`.

## What every kind leaves to a person

Owners and contacts, policy and its reasons, service levels nobody wrote down, the history of a decision,
anything behind a login. The page lists each placeholder with who can fill it; the draft never fills it
with a plausible sentence.
