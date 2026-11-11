# Software engineering

The daily work on code: map a repository you do not know, find what a change reaches, trace a failure to its cause, pick the tests to write first, audit dependencies and code, review a change, write documents from the code, and handle an incident from triage to the write-up. Install it as `software-engineering@claude-role-skills`; the skills are called as `/software-engineering:<skill>`.

| Skill | Use it when | It writes |
|---|---|---|
| [codebase-map](../../../plugins/software-engineering/skills/codebase-map/SKILL.md) | you open a repository you do not know | a map: purpose, entry points, module graph, flows traced hop by hop, boundaries, health, open questions |
| [impact](../../../plugins/software-engineering/skills/impact/SKILL.md) | before you change, rename or remove something | everything the change reaches, including dynamic calls, stored data and outside consumers, and the safe order of steps |
| [bug-hunt](../../../plugins/software-engineering/skills/bug-hunt/SKILL.md) | an error, a failing test or a bug report needs its root cause | the cause with evidence, the commit that brought it, a failing regression test, the same weakness elsewhere, fix options |
| [test-gap](../../../plugins/software-engineering/skills/test-gap/SKILL.md) | you need to know which tests to write first | code ranked by risk, change rate and missing coverage; missing cases with their expected results; weak and deleted tests |
| [dependency-audit](../../../plugins/software-engineering/skills/dependency-audit/SKILL.md) | you inherit a project, before a release, or after an alert | vulnerabilities and whether the code reaches them, outdated, unused and abandoned packages, licences, upgrade waves |
| [code-audit](../../../plugins/software-engineering/skills/code-audit/SKILL.md) | the code as it stands must be checked for bugs, before you build on it or release it | bugs read in the code, each with the scenario that triggers it and the test that would catch it; promises in the docs that no code keeps; what happens when a step fails halfway; cycles, layer breaks and hidden coupling; SQL, shell commands, paths and URLs built from input, secrets in code, unsafe loads, calls in loops, whole-table reads, resources never closed |
| [change-review](../../../plugins/software-engineering/skills/change-review/SKILL.md) | a branch, a range, a patch or a PR must be reviewed before it merges | every hunk read against security, performance, correctness and maintainability; what the change claims against what it does; tests removed or missing, written out; what looks good; a verdict of approve, request changes or needs discussion |
| [docs-draft](../../../plugins/software-engineering/skills/docs-draft/SKILL.md) | a README, runbook, API reference, onboarding guide, architecture document or a whole `docs/` set must be written or brought back in line with the code | the draft, placed in one repository layout, with every command, flag, route, setting and scheduled job from the code and the rest tagged; where the existing documents drifted (a renamed job, a target, a setting, a time that disagrees with the schedule); what only a person can fill in; written into the repository after the yes |
| [incident-triage](../../../plugins/software-engineering/skills/incident-triage/SKILL.md) | an alert fires or production misbehaves and the team needs the picture now | one timeline from the logs and git, the first error and what changed before it, a severity with the facts that set it, mitigation options with evidence, a status update draft, the next call |
| [postmortem](../../../plugins/software-engineering/skills/postmortem/SKILL.md) | an incident is resolved and the team needs the write-up | a timeline with a source for every entry, the cause from the bug-hunt page, contributing factors, a why chain that stops at the first guess, action items each with its check, the document in Markdown; roles, not names |

`code-audit` reviews code that exists and `change-review` a change to it; a design that is not built yet goes to
`arch-review`. `incident-triage` runs while it burns, `bug-hunt` finds the cause, `postmortem` writes it up after.
`change-review`, `incident-triage` and `postmortem` post nothing: the comments and the status update are on the page,
and the user sends them.

## More

- Each skill's scripts, shared copies and guard: [reference/skills.md](../../reference/skills.md#software-engineering).
- [roadmap/engineering-pack-v2.md](../../roadmap/engineering-pack-v2.md): the second round of the pack: change-review, docs-draft, incident-triage, postmortem and the open phases.
- [roadmap/code-audit.md](../../roadmap/code-audit.md): why code-audit exists and which review takes which request.
