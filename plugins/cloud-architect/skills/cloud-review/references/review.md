# Reviewing cloud infrastructure

What the script's `--checks` families mean, how to confirm a hit, and how to fix it. The provider file says what each
service means by public and lists the pillars. A hit is a place to read.

| Family | What it finds | Confirm it by | Fix |
|---|---|---|---|
| exposure | a database open to every address, storage readable without a sign-in, a public endpoint left at its default | reading the firewall rule or property, and whether anything needs it open | close it; a specific address or a private endpoint; if it must stay open, say why and what watches it |
| network | an inbound rule from anywhere | what the rule applies to, and whether anything listens on that port there | a specific source, or remove the rule |
| secrets | a value that looks like a secret in plain settings | reading the setting's name and where its value comes from | a reference to the provider's secret store; rotate the value, it has been in the repository's history |
| identity | no managed identity, a shared admin user, a policy that allows every action | whether a credential is used instead; which permissions the workload really needs | a role or managed identity with only what it needs |
| monitoring | no diagnostics, short retention | whether another resource or an external system collects these logs | a diagnostic setting; retention to match what an incident needs |
| resilience | one zone, one instance, locally redundant storage | what the brief or requirements demand; a single zone is a finding when something demands more | a higher SKU and zone redundancy, or accept it in writing |
| supply-chain | an unpinned image | whether a deployment process pins it elsewhere | a version or digest |
| encryption | TLS below 1.2, plain HTTP allowed, storage not encrypted | the setting, and whether clients still need the old one | TLS 1.2 or later, HTTPS only, encryption at rest |
| efficiency | old instance generations, no autoscaling, data kept with nothing to expire it | whether the load is steady and the size chosen on purpose | a current generation, a scaling rule, a lifecycle rule |
| cost | logs and images kept forever | what the retention needs to be for an incident | an expiry that matches what an incident needs |

## Severity

Judge by what the problem can cost, not by its family. A database open to the whole internet is high whatever the data.
A single zone is high only if something demands more; otherwise it is a note. Say why.

## What a script cannot see

- Whether an open port is actually in use, or a public endpoint is intended.
- The requirements. A brief saying "survive a zone" is what makes a single zone a finding.
- Secrets that do not look like secrets, and secrets outside this repository.
- Anything `unresolved` lists: repeated resources, dynamic names, remote modules.
- Live configuration: the code says what was intended, an export says what exists.
