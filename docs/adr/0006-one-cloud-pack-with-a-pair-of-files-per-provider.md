# 0006. One cloud pack, with a pair of files per provider

Date: 2026-11-09, in the plan of the architect series.

## Status

Accepted

## Context

The vendor skills (`microsoft/azure-skills`, `awslabs/agent-plugins`) cover one cloud each and deploy; the community
multi-cloud skills give text tables with no real prices and no drawings. The gap was one brief compared across clouds
with real prices, drawn and reviewed the same way, starting from infrastructure code with no cloud login. Comparing needs
both clouds in the same skill. Source: "3. cloud-architect" in
[roadmap/architect-packs.md](../roadmap/architect-packs.md#3-cloud-architect) and
[roadmap/cloud-architect.md](../roadmap/cloud-architect.md).

## Decision

One `cloud-architect` pack. Everything provider-specific is one pair of files, `shared/cloud/PROVIDER.md` and
`shared/cloud/PROVIDER.json`; nothing provider-specific goes in a `SKILL.md` or in the core of a script. The skills do
not deploy and do not write production infrastructure code.

## Consequences

- A test checks that the cloud skills and the core cloud scripts name no provider.
- Adding a provider is one pair of files and needs no change to `tools/sync_shared.py`; Azure and AWS exist, Google
  Cloud does not (its price API needs a key).
