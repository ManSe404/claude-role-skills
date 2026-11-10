# Azure

Everything Azure-specific a cloud skill needs to read. The scripts read `azure.json` (resource types,
exposure rules, review checks); this file is for Claude. Facts marked [high] were checked against
learn.microsoft.com on 2026-11-10; check a limit or a price again when a decision depends on it.

## Infrastructure code

`cloud_inventory.py` reads Terraform (`azurerm_*`), Bicep and ARM JSON. Terraform names, Bicep and ARM types
map to one normal form: the ARM type, such as `Microsoft.Sql/servers`.

## Nesting

Subscription, resource group, VNet, subnet, resource. The inventory fills each resource's `nesting` with those
four levels; a level the code does not state is `null`.

How to draw it in a `nested` block: one box for the subscription, a box per resource group inside it, the VNet
inside its resource group, each subnet inside the VNet. A resource that sits in a subnet goes in that subnet's
box even when its own resource group is another one: say its group in the card. Everything else goes in its
resource group's box. A resource with a `parent` (a database on a server, a container app in its environment)
goes in its parent's box. A resource with no resource group goes in a box called "Not placed by the code".

Show the parts of a server or namespace that matter (database, queue, firewall rule) as boxes inside it; leave out
what adds nothing (diagnostic settings, Subnet-NSG associations) and say so in a note.

Levels: Subscription (only the resource groups open), Resource groups (each group open), Network (groups, VNet and
subnets open), and everything open.

## The ladders, as Azure services

The neutral options from `cloud_rules.py`, as real services.

| Ladder | Option | Azure service |
|---|---|---|
| compute | managed_app_platform | App Service (Linux plan) |
| compute | serverless_containers | Container Apps (Consumption, or Dedicated workload profiles) |
| compute | functions | Azure Functions (Flex Consumption) |
| compute | kubernetes | AKS |
| compute | virtual_machines | Virtual Machines, VM Scale Sets |
| data | managed_relational | Azure SQL Database (single database), or Azure Database for PostgreSQL flexible server |
| data | managed_relational_scaled | The same, with read replicas |
| data | managed_document | Azure Cosmos DB |
| data | self_managed | A database on Virtual Machines |
| network | public_restricted | Public endpoints with firewall rules and access restrictions |
| network | private_data | VNet integration for compute, private endpoints for SQL, Storage and Key Vault; only the web tier faces the internet |
| network | fully_private | Internal compute behind Application Gateway with WAF or Front Door Premium with Private Link |
| network | hub_and_spoke | A hub VNet with Azure Firewall, peered spokes |
| region | one_region | One region inside the residency area |
| region | two_regions | A paired region, with failover (SQL failover groups, GZRS storage) |
| availability | one_zone | The default: nothing zone redundant |
| availability | zone_redundant | Zone-redundant SQL, App Service plan or Container Apps environment, ZRS storage, zone-redundant gateway |
| availability | multi_region | Two regions with a tested failover |

Limits that change a design [high]:

- App Service: zone redundancy needs a Premium v2, v3 or v4 plan and at least 2 instances.
- Container Apps: zone redundancy needs a custom VNet (subnet at least /27 for workload profiles, /23 for
  consumption-only) and is set when the environment is created: it cannot be changed later. Set `min_replicas`
  to at least 2.
- SQL Database: zone redundancy is available for General Purpose, Business Critical and Hyperscale (vCore) and
  Premium (DTU), not for Basic or Standard DTU.
- Service Bus: private endpoints are in the Premium tier only. A design that needs a private queue pays for
  Premium, or uses Storage queues over a private endpoint.

## What public exposure means

`cloud_inventory.py` decides with the rules in `azure.json`. In words:

| Service | Public when | What closes it |
|---|---|---|
| App Service app | always, unless closed | `public_network_access` off, a private endpoint [med: closes the default public access], or access restrictions (only some addresses) |
| Container App | ingress is external | internal ingress, or an internal environment |
| SQL server, PostgreSQL | a firewall rule covers everything | public access off; firewall rules for specific addresses mean restricted |
| Storage account | network rules allow it; anonymous reads if blob public access is on or a container is public | public access off, network rules deny by default, no anonymous access |
| Key Vault | network rules allow it | public access off, network rules deny by default |
| Service Bus, Cosmos DB, Redis, Container Registry, API Management | public endpoint unless closed | public access off (Service Bus: Premium with a private endpoint). Authentication still applies. |
| AKS | the API server is public unless the cluster is private | a private cluster |
| Public IP | always | no public IP, or an NSG in front of what it points to |
| NSG rule | an inbound Allow from `*`, `Internet` or `0.0.0.0/0` | a specific source; on its own it opens nothing unless something listens |

Firewalls and private boundaries stop the `reach` walk: a firewall (Azure Firewall), a gateway with a WAF, a private
endpoint, and anything whose exposure is `private`.

## The five pillars

The Azure Well-Architected Framework has five pillars. Every review check in `azure.json` names one.

| Pillar | Asks | Hits usually from |
|---|---|---|
| Reliability | Does it survive a fault, and how fast does it recover? | single zone or one instance, no backup |
| Security | Is the data and access protected? | public exposure, secrets in settings, no managed identity, old TLS |
| Cost Optimization | Is anything paid for and not needed? | oversized SKUs, dev tiers in prod, unused resources |
| Operational Excellence | Can the team see and change it safely? | no diagnostics, unpinned images, drift from code |
| Performance Efficiency | Does it scale to its load? | one worker, no scale-out rule, wrong SKU for the load |

A check's pillar is a starting point. The review may move a finding to a different pillar if that is what it costs.

## A read-only export

Only after the user's yes. Say which subscription would be read and that it lists resources without their keys or
settings, then run one of these yourself and save the JSON. Do not run anything that changes something. Do not log in
for the user: if `az account show` fails, say so and stop.

```bash
az account show -o json
az resource list --subscription SUBSCRIPTION_ID -o json > EXPORT.json
```

Or with Azure Resource Graph (needs the `resource-graph` extension):

```bash
az graph query -q "resources | project id, name, type, resourceGroup, location, subscriptionId" --first 1000 -o json > EXPORT.json
```

`az resource list` does not list subnets, NSG rules, firewall rules, blob containers, queues, role assignments or
diagnostic settings, so those are not compared with the code. `azure.json` holds the list.

## Price list

`cloud_prices.py --online` asks the Azure Retail Prices API, `https://prices.azure.com/api/retail/prices`, which is
public and needs no login. It sends the fields of a bill-of-materials item as an OData filter. Set `service`,
`product`, `sku`, `meter`, `region` and `unit` so one price matches; set `unit` to the price's own unit and `quantity`
to how many of that unit a month. A month is 730 hours.

| What | service | product | sku | meter | unit | quantity |
|---|---|---|---|---|---|---|
| App Service plan, Linux, B1 | Azure App Service | Azure App Service Basic Plan - Linux | B1 | B1 | 1 Hour | 730 × instances |
| App Service plan, Linux, S1 | Azure App Service | Azure App Service Standard Plan - Linux | S1 | S1 App | 1 Hour | 730 × instances |
| App Service plan, Linux, P1v3 | Azure App Service | Azure App Service Premium v3 Plan - Linux | P1 v3 | P1 v3 App | 1 Hour | 730 × instances |
| Container Apps, active vCPU | Azure Container Apps | Azure Container Apps | Standard | Standard vCPU Active Usage | 1 Second | seconds × vCPU |
| Container Apps, active memory | Azure Container Apps | Azure Container Apps | Standard | Standard Memory Active Usage | 1 GiB Second | seconds × GiB |
| Container Apps, requests | Azure Container Apps | Azure Container Apps | Standard | Standard Requests | 1M | millions of requests |
| Container Apps environment | Azure Container Apps | Azure Container Apps | Environment | Environment Management Hour | 1 Hour | 730 [med: these Environment rows are new, effective 2026-11-01; check that they apply to the plan you choose] |
| SQL Database, vCore, General Purpose | SQL Database | SQL Database Single/Elastic Pool General Purpose - Compute Gen5 | 2 vCore | vCore | 1 Hour | 730 (the sku is the whole database, not per vCore) |
| SQL Database, zone redundancy add-on | SQL Database | SQL Database Single/Elastic Pool General Purpose - Compute Gen5 | 2 vCore Zone Redundancy | Zone Redundancy vCore | 1 Hour | 730, added to the vCore row [med] |
| SQL Database, DTU | SQL Database | SQL Database Single Standard | S0 | S0 DTUs | 1/Day | 30.4 |
| SQL storage | SQL Database | SQL Database Single/Elastic Pool General Purpose - Storage | General Purpose | General Purpose Data Stored | 1 GB/Month | GB |
| SQL storage, zone redundant | SQL Database | SQL Database Single/Elastic Pool General Purpose - Storage | General Purpose Zone Redundancy | General Purpose Zone Redundancy Data Stored | 1 GB/Month | GB, instead of the row above [med] |
| Blob storage, hot | Storage | General Block Blob v2 | Hot LRS or Hot ZRS | Hot LRS Data Stored or Hot ZRS Data Stored | 1 GB/Month | GB |
| Service Bus Standard | Service Bus | Service Bus | Standard | Standard Base Unit | 1/Month | 1 |
| Service Bus Premium | Service Bus | Service Bus | Premium | Premium Messaging Unit | 1/Hour | 730 |
| Private endpoint | Virtual Network | Virtual Network Private Link | Standard | Standard Private Endpoint | 1 Hour | 730 × endpoints; region Global |
| Application Gateway with WAF | Application Gateway | Application Gateway WAF v2 | Standard | Standard Fixed Cost and Standard Capacity Units | 1/Hour | 730; capacity units per the load |
| Log Analytics ingestion | Log Analytics | Log Analytics | Analytics Logs | Analytics Logs Data Ingestion | 1 GB | GB a month |
| Key Vault operations | Key Vault | Key Vault | Standard | Operations | 10K | number of 10K a month |
| Outbound data | Bandwidth | Bandwidth - Routing Preference: Internet | Standard | Standard Data Transfer Out | 1 GB | GB a month |

A SKU not listed here: find its row in the saved table, or ask `--online` and read what comes back as `ambiguous`.
