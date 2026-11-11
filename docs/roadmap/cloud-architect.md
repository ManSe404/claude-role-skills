# Plan: pack `cloud-architect`

Status: Stefan said go on 2026-11-10. Azure and AWS are built; the choices made without him are at the
end. The pack is steps 3a and 3b of [architect-packs.md](architect-packs.md); Google Cloud is later.

## Goal

A pack for the person responsible for where a system runs. It draws the cloud infrastructure that
exists, from code in a repository with no cloud login or from a read-only export, reviews it against
the provider's Well-Architected pillars, and compares a brief across options and clouds with real
prices. It works the same way on any provider it knows; a provider is a pair of files.

Out of scope:
- deploying and writing production infrastructure code: Microsoft's `azure-skills` and the AWS plugins do that;
- the structure of the software that runs there: `software-architect`;
- the data platform's models and pipelines: `data-architect`;
- AI solutions: `ai-architect`.

Vendors cover one cloud each and they deploy. Ours differs in two ways: one brief compared across
clouds with real prices, and a drawing and a review that start from a repository with no login.

## Skills

### 1. `cloud-map`: the infrastructure that exists

From Terraform, Bicep, ARM templates or CloudFormation in a repository, or from a read-only export after
the user's yes. A page with a `nested` block following the provider's levels (subscription, resource group,
VNet, subnet; or account, region, VPC, subnet), clickable; the
request flows; a `reach` view from the internet to what it can get to, stopping at firewalls or private
boundaries; and what is in code but not deployed and deployed but not in code, when both are given.

Never: logs in, deploys, reads a state file or a variables file with real values, or shows a secret's value.

### 2. `cloud-design`: what it should run on

From a brief, ruled out from the simplest up, as in `arch-style` and `data-platform`: compute class, data,
networking, region and availability. Up to two variants or two clouds. Monthly cost from the provider's
price list, summarised per cloud, every price with its date and source. An ADR draft.

Never: proposes Kubernetes where a managed platform or serverless containers pass.

### 3. `cloud-review`: what is wrong with it

Problems in the code or an export, each tied to file:line or a resource, checked against the provider's
Well-Architected pillars, marked on the drawing, with what to fix first. The script's hits are places to
read; a hit that was not read is not a finding.

## Scripts

Standard library, read-only, JSON on stdout, no network unless asked for, and then with a timeout.

| script | skills | what it does |
|---|---|---|
| `cloud_inventory.py` (shared) | cloud-map, cloud-review | A small HCL, Bicep, ARM and CloudFormation (JSON and YAML, with a small indentation reader) reader into one shape: id, provider, type, category, name, file, line, nesting, location, the attributes that matter, references. Reports what it could not resolve instead of guessing. `--compare` for drift against a saved export. `--checks` for review hits per family, each with its pillar. Computes public exposure. Replaces values that look like secrets with a marker. |
| `cloud_prices.py` (shared) | cloud-design | Prices a bill of materials. `--prices FILE` reads a saved, dated table and can be repeated for each cloud; `--online` calls the provider's public price list with a timeout: a query API for Azure, whole offer files streamed to a temporary file under a size ceiling for AWS. Each price comes with its date and source; a total per cloud and variant. |
| `cloud_rules.py` | cloud-design | The hard rules of the five ladders. Neutral options, simplest first, named thresholds printed in the output, never chooses, lists the facts it does not know. |

No script calls `az`, `aws` or any cloud API other than the public price lists. A live read is the skill's text
asking for a yes, then running the read-only command from the provider file and saving JSON that the
script reads.

## Providers

`shared/cloud/<provider>.md` for what Claude reads (service mapping, nesting, what public exposure means
per service, the pillars, the read-only export, how to fill a bill of materials) and
`shared/cloud/<provider>.json` for what the scripts read (resource types, categories, placement,
exposure rules, check rules, export shapes, price list shape). The core of every script and the text of
every skill stay provider-neutral: a test checks that. `azure.*` has five pillars, `aws.*` six.

Both files are copied into each skill by `tools/sync_shared.py` (a skill must work on its own).

## Renderer

Nothing new: the `nested` block with `reach` was built for this. Boxes carry their kind in text; no
official icons, because Microsoft allows them only in diagrams and documentation and they cannot fall
under the repo's MIT licence.

## Fixture: `fixtures/acme-cloud/` (all fictional)

Acme Tickets, a small estate: Terraform for the main app, one local module, a Bicep module for reports
across subscription-level resource groups, an ARM template, a VNet with subnets, App Service, Container
Apps, Azure SQL, Storage, Key Vault and a Service Bus queue. Two briefs: the box office (the right answer is
a managed app platform with one database) and the festival platform (private networking, zone redundancy
and containers, not Kubernetes). `extras/` holds a saved fake export and a saved dated price table of
real list prices. Eight planted problems, plus one resource only in code and one only in the export.

`fixtures/acme-cloud-aws/` (all fictional, except the saved list prices): Stagefront, a ticket seller on AWS that Acme
Tickets bought. Terraform for the main application (VPC, ALB, ECS on Fargate, RDS, S3, Secrets Manager, SQS through a
local module) and CloudFormation (YAML and JSON) for reports, an admin host and alerts. Eight planted problems and
drift: one ElastiCache group only in the export, one bucket only in code. One brief, the festival platform, that either
cloud must serve, so the two-cloud comparison has one input. `extras/` holds a saved tagging export, real AWS list
prices for eu-central-1 from 2026-11-10, and a copy of the Azure price table.

## Evals

map-from-code, map-drift, design-does-not-overbuild, design-names-the-constraint, review-finds-planted
(at least 6 of 8, no file changed), and for step 3b aws-map-from-code, aws-review-finds-planted and
design-compares-clouds. Each with a `skill-fired` grader. Run only when Stefan asks.

## Order

M1 plan and fixture. M2 renderer, if a real gap shows. M3 scripts and tests. M4 skills, provider files
and tooling. M5 evals written. M6 manifests, role starter, README, CLAUDE.md. Then the example pages
from headless runs (about $7.50) and checks by hand. Green at the end.

## Choices made without Stefan

1. A `.tfvars`, `.tfstate`, `.bicepparam` and `.parameters.json` file is listed as not read, even though the
   values would resolve more names: those are where real values and secrets live.
2. A category of its own, `scope`, for resource groups, which are neither compute nor network.
3. Rules for `cloud_rules.py`: at most 5 services stay on a managed app platform; at least 2 platform engineers
   and at least 15 services (or a stated need for the Kubernetes API) for Kubernetes. These are judgements,
   printed in the output so a page can show them.
4. The fixture's saved price table holds real Retail Prices API rows from 2026-11-10, because a made-up price
   would make the page's numbers meaningless; everything else in the fixture is fictional.
5. For AWS, a price item's `sku` is a few attributes of the offer row joined with " / ", because the offer files have no
   human name for a row; `aws.json` lists which attributes per offer, and `aws.md` gives the exact strings a bill uses.
6. `--online` for AWS streams each offer file to a temporary file and stops at 64 MB, because the EC2 file is 435 MB for
   one region; the design page's NAT gateway rows therefore come from the saved table, which was extracted once with the
   ceiling raised. A request above the ceiling comes back as `too_large` with how to give a table.
7. AWS Terraform and CloudFormation share one normal form, the CloudFormation type; a few Terraform-only resources
   (`aws_s3_bucket_public_access_block` and the like) get a name of the same shape so checks can follow them.
8. Exposure for regional APIs (SQS, Secrets Manager, KMS, ECR, DynamoDB) is `restricted` rather than `public`: they have
   no address in a network and every call is signed, which is a different thing from a database with a public address.
9. The Azure price table is copied into the AWS fixture so a design run has both tables in one fixture; a test keeps the
   two copies identical.
