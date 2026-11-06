---
name: dependency-audit
description: Use when you inherit a project, before a release, or when a vulnerability alert arrives, to audit its dependencies - which are vulnerable and whether the vulnerable code is reached, which are outdated, unpinned, unused or abandoned, which licences clash - and plan the upgrades in safe waves, without installing anything.
argument-hint: "[repo or manifest]"
---

# Dependency audit

The job: every dependency of the project weighed by what it costs to keep it as it is, and the
order to upgrade. It never installs, upgrades or edits a manifest or a lock file.

Input: a repository or a folder in it.

## Steps

1. Inventory, offline: `python3 "${CLAUDE_SKILL_DIR}/scripts/deps.py" REPO`, output to your
   scratchpad. Manifests, lock files, direct and transitive dependencies, ranges without a lock,
   duplicates, and where each direct dependency is imported.
2. Online, only after the yes: tell the user that `--online` sends package names and versions,
   and nothing else, to api.osv.dev, pypi.org, registry.npmjs.org and api.nuget.org. After the
   yes, run it again with `--online`. Without the yes, the page covers the offline part and says
   that vulnerabilities and latest versions were not checked.
3. Vulnerabilities: for each one, is the vulnerable code reached? Read the advisory, find the
   affected function or feature, and search the repo for its use. Reached is [high] with
   file:line; not reached is [med], because a transitive use can hide it. A range without a lock
   is checked at the lowest version it allows: say that the installed version may differ.
4. Outdated: how far behind each direct dependency is (patch, minor, major), and its age.
   Abandoned: no release in two years, or deprecated by its maintainers.
5. Unused: direct dependencies the code never imports. Before calling one unused, check it is
   not a plugin, a command-line tool, a type package or a runtime extra. Then [med].
6. Licences: against the project's own licence and how it ships (library, service, closed
   product). Flag copyleft in closed products and unknown licences.
7. Upgrade plan in waves: first the fixes for reached vulnerabilities that stay in the same
   major version, then the remaining security fixes, then majors one at a time, each with its
   breaking changes from the changelog and the tests that must pass. Pin and lock where nothing
   locks.
8. Write the page JSON, render it, and say where to open it.

## Output

One page. Read [references/page-format.md](references/page-format.md) for the format and
[references/example.json](references/example.json) for a filled page before you write.

Sections in this order: Inventory (table: package, scope, declared, locked, latest, imported in),
Vulnerabilities (findings: one per vulnerability, with severity, reached or not, where, fixed in),
Outdated and abandoned (table), Unused (findings), Licences (table), Pinning and locking
(findings), Upgrade plan (steps per wave). Stats on top: direct and transitive dependencies,
vulnerabilities and how many are reached, majors behind, unpinned. The verdict names what to do
this week.

Render: `python3 "${CLAUDE_SKILL_DIR}/scripts/render_page.py" PAGE.json -o PAGE.html`, with both
files in `${CLAUDE_PAGES_DIR:-$HOME/claude-pages}/<repo>/dependency-audit-<YYYY-MM-DD>.*`.

## Reads

- the manifests, the lock files and the code of the repo
- after the yes: the public vulnerability database and package registries, for names and versions

## Writes

- the page and its JSON, outside the repo

## Never

- Never installs, upgrades or removes a package, and never edits a manifest or a lock file.
- Never sends anything but package names and versions, and nothing at all before the yes.
- Never calls a vulnerability harmless without reading where the vulnerable code would run.
