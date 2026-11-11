# Packs and skills

Generated from `.claude-plugin/marketplace.json`, each pack's `.claude-plugin/plugin.json` and the frontmatter
and `scripts/` folder of each `SKILL.md`. Do not edit it by hand: change the manifest or the skill, then
regenerate it (see [How to regenerate](#how-to-regenerate)). What each skill writes, in words, is in
[product/features/](../product/features/).

10 packs, 50 skills.

| Pack | Version | Skills | Installs with it |
|---|---|--:|---|
| [software-engineering](#software-engineering) | 0.4.4 | 10 | nothing |
| [ai-architect](#ai-architect) | 0.2.5 | 4 | nothing |
| [data-architect](#data-architect) | 0.2.5 | 4 | nothing |
| [data-engineer](#data-engineer) | 0.1.3 | 7 | nothing |
| [software-architect](#software-architect) | 0.3.5 | 4 | nothing |
| [cloud-architect](#cloud-architect) | 0.2.6 | 3 | nothing |
| [solutions-architect](#solutions-architect) | 0.2.5 | 2 | `ai-architect`, `data-architect`, `software-architect`, `cloud-architect` |
| [data-analyst](#data-analyst) | 0.2.5 | 4 | nothing |
| [data-scientist](#data-scientist) | 0.2.5 | 5 | nothing |
| [workflows](#workflows) | 0.1.1 | 7 | `software-engineering`, `ai-architect`, `data-architect`, `data-engineer`, `software-architect`, `cloud-architect`, `solutions-architect`, `data-analyst`, `data-scientist` |

Every skill carries copies of `shared/guard.py` and `shared/render_page.py` in its `scripts/`. The table lists a skill's own scripts and its other copies from `shared/`. The guard column says how the skill's `hooks:` block calls `guard.py`: `pre` asks before changes and before going online; `pre + personal` also keeps personal data out (see [architecture/crosscutting.md](../architecture/crosscutting.md)).

## software-engineering

Ten skills for software engineers: codebase-map, impact, bug-hunt, test-gap, dependency-audit, code-audit, change-review, docs-draft, incident-triage and postmortem. Each counts with its own scripts and ends in one self-contained web page.

| Skill | What it does | When to use it | Own scripts | Other shared copies | Guard |
|---|---|---|---|---|---|
| [bug-hunt](../../plugins/software-engineering/skills/bug-hunt/SKILL.md)<br>`/software-engineering:bug-hunt [error text, log file, failing test or issue]` | Traces a failure from its symptom to the root cause with evidence and a failing test that reproduces it, finds the same weakness elsewhere and proposes fixes, fixing only after the yes. | Use when an error, a stack trace, a failing test or a bug report needs its root cause. | `suspects.py` | none | pre |
| [change-review](../../plugins/software-engineering/skills/change-review/SKILL.md)<br>`/software-engineering:change-review [range such as main..feature, a patch file or a PR] [what worries you]` | Reviews a diff or pull request hunk by hunk for security, performance, correctness and maintainability, holds it against what it claims, and ends in a verdict with every finding tied to a line and the test that would catch it. | Use before a change is merged, when given a branch, a range, a patch or a PR. Not for code as it stands (code-audit), one failure (bug-hunt) or a planned change (impact). | `diff_facts.py` | `audit_scan.py` | pre |
| [code-audit](../../plugins/software-engineering/skills/code-audit/SKILL.md)<br>`/software-engineering:code-audit [repo, folder or module] [what worries you]` | Reviews code as it stands for bugs, failure handling, promises in its docs that no code keeps and structure that makes it hard to change, each with file:line and the test that would catch it. | Use before you build on, take over or release a repository or module. Not for a diff or pull request (a change review), one known failure (bug-hunt) or an unbuilt design (arch-review). | none | `audit_scan.py`, `code_graph.py` | pre |
| [codebase-map](../../plugins/software-engineering/skills/codebase-map/SKILL.md)<br>`/software-engineering:codebase-map [repo or folder]` | Maps an unknown repository on one page from what the code does, with entry points, modules, flows traced hop by hop, outside systems, how to run it and open questions. | Use when you open a repository you do not know yet, or must explain one to someone. | `imports.py`, `inventory.py` | none | pre |
| [dependency-audit](../../plugins/software-engineering/skills/dependency-audit/SKILL.md)<br>`/software-engineering:dependency-audit [repo or manifest]` | Audits the dependencies of a project for vulnerabilities and whether the code reaches them, outdated, unused or abandoned packages and licence clashes, and plans upgrades in safe waves. | Use when you inherit a project, before a release, or when a vulnerability alert arrives. | `deps.py` | none | pre |
| [docs-draft](../../plugins/software-engineering/skills/docs-draft/SKILL.md)<br>`/software-engineering:docs-draft [repository or folder] [kind of document] [who reads it]` | Drafts a README, runbook, API reference, onboarding guide, architecture document or a whole docs/ set in one layout, every name from the code and the rest tagged, and lists where existing documents drifted. | Use when a technical document must be written or brought back in line with the code. Not for mapping an unknown repository (codebase-map) or reviewing a design (arch-review). | `docs_facts.py` | none | pre |
| [impact](../../plugins/software-engineering/skills/impact/SKILL.md)<br>`/software-engineering:impact [name and intended change, or the diff]` | Finds everything a change reaches, including callers, dynamic uses, public surfaces, stored data and outside consumers, and the safe order to make it. | Use before you change, rename or remove a function, class, module, endpoint, setting or column, or on the current diff. | `refs.py` | none | pre |
| [incident-triage](../../plugins/software-engineering/skills/incident-triage/SKILL.md)<br>`/software-engineering:incident-triage [alert or report text] [log file or folder] [repository]` | Turns an alert or outage report and the logs into one timeline with the first error, what changed before it, a severity with its facts, mitigation options with evidence and a status update draft. | Use when an alert fires or production misbehaves and the team needs the picture now. Not for a failing test with its trace (bug-hunt) or after the incident (postmortem). | none | `data_profile.py`, `incident_timeline.py` | pre + personal |
| [postmortem](../../plugins/software-engineering/skills/postmortem/SKILL.md)<br>`/software-engineering:postmortem [incident-triage and bug-hunt page JSON] [logs] [repository] [detected, mitigated and resolved times]` | Writes the blameless postmortem of a resolved incident from the triage and bug-hunt pages, the logs and git, with a sourced timeline, cause and factors, a why chain that stops at the first guess, and action items with checks. | Use when an incident is resolved and the team needs the write-up. Not while it burns (incident-triage) and not to find the cause (bug-hunt). | none | `data_profile.py`, `incident_timeline.py` | pre + personal |
| [test-gap](../../plugins/software-engineering/skills/test-gap/SKILL.md)<br>`/software-engineering:test-gap [repo, folder or coverage report]` | Ranks code by risk, change rate and missing coverage, names the missing test cases with their expected results written first, and finds tests that assert nothing. | Use when deciding which tests to write first, before a refactor or after an incident. | `gaps.py` | none | pre |

## ai-architect

Four skills for AI solutions architects: ai-pattern, ai-stack, ai-architecture and ai-review. They decide what an AI solution should be, pick and price its stack, draw it as an interactive page and review one that exists. Each counts with its own scripts and ends in one self-contained web page.

| Skill | What it does | When to use it | Own scripts | Other shared copies | Guard |
|---|---|---|---|---|---|
| [ai-architecture](../../plugins/ai-architect/skills/ai-architecture/SKILL.md)<br>`/ai-architect:ai-architecture [ai-pattern or ai-stack page JSON, a description, or a repo]` | Draws an AI or LLM solution as one interactive page, with components in zones, request flows step by step, variants and the trust boundaries untrusted text crosses. | Use when an AI or LLM solution must be shown or explained to a client or a team, from its design or its repository. | none | `ai_inventory.py` | pre |
| [ai-pattern](../../plugins/ai-architect/skills/ai-pattern/SKILL.md)<br>`/ai-architect:ai-pattern [brief file or text] [documents folder]` | Decides what an AI or LLM solution should be, from no LLM to RAG, a workflow or agents, by ruling options out against the brief, with acceptance criteria and an ADR draft. | Use before building an AI or LLM solution, when a brief or use case arrives and the approach is still open. | `corpus_stats.py`, `decide.py` | none | pre |
| [ai-review](../../plugins/ai-architect/skills/ai-review/SKILL.md)<br>`/ai-architect:ai-review [repo] [brief]` | Reviews the code of an AI or LLM solution for the common failures, such as untrusted text reaching actions, agent loops without limits, no evals, no timeouts and unknown cost, with file:line fixes. | Use before a release, a takeover or a handover of an AI or LLM solution. For general bugs in code use code-audit. | none | `ai_inventory.py` | pre |
| [ai-stack](../../plugins/ai-architect/skills/ai-stack/SKILL.md)<br>`/ai-architect:ai-stack [ai-pattern page JSON or a description] [constraints]` | Picks the models, embeddings, store, orchestration, hosting, tracing, evals and guardrails for an AI solution, in up to two variants, with monthly cost and latency from a dated price table. | Use when the pattern of an AI or LLM solution is chosen and the tools must be picked, such as which vector database or which model. | `cost_model.py` | none | pre |

## data-architect

Four skills for data architects: data-platform, data-model, data-map and data-review. They decide what a data platform should be and size it, design the model with its grain and keys, map what exists from the code, and review it. Each counts with its own scripts and ends in one self-contained web page.

| Skill | What it does | When to use it | Own scripts | Other shared copies | Guard |
|---|---|---|---|---|---|
| [data-map](../../plugins/data-architect/skills/data-map/SKILL.md)<br>`/data-architect:data-map [repository of the data platform]` | Maps a data platform from its SQL, dbt, notebooks and pipelines, with sources, layers, consumers, table lineage, owners, unused tables and where personal data travels. | Use when you inherit a data platform or must explain one. | none | `sql_inventory.py` | pre |
| [data-model](../../plugins/data-architect/skills/data-model/SKILL.md)<br>`/data-architect:data-model [DDL, dbt project or samples folder] [the questions it must answer]` | Models a subject area of a data platform, choosing the modelling style, the grain of every fact, the keys and the history, ending in a clickable model and DDL drafts. | Use when a subject area must be modelled from source schemas, DDL, dbt or sample files. | `model_check.py` | `data_profile.py`, `sql_inventory.py` | pre + personal |
| [data-platform](../../plugins/data-architect/skills/data-platform/SKILL.md)<br>`/data-architect:data-platform [brief file or text] [samples folder]` | Decides what a data platform should be, from reports on the source to a warehouse, lakehouse or streaming path, by ruling options out against the brief, with sizing, layers and an ADR draft. | Use before building or rebuilding a data platform, when a brief or a list of sources arrives, or when choosing between products such as Snowflake and Fabric. | `platform_rules.py` | `data_profile.py` | pre + personal |
| [data-review](../../plugins/data-architect/skills/data-review/SKILL.md)<br>`/data-architect:data-review [repository of the data platform] [samples folder]` | Reviews the models and loads of a data platform for the common failures, such as mixed grain, joins that multiply rows, loads that cannot be rerun and personal data served unmasked, with file:line fixes. | Use before a release, a takeover or a handover of a data platform. | none | `data_profile.py`, `sql_inventory.py` | pre + personal |

## data-engineer

Seven skills for data engineers who run a platform: source-profile, source-contract, pipeline-incident, data-quality, data-cost, data-migration and data-product. Each counts with its own scripts and ends in one self-contained web page.

| Skill | What it does | When to use it | Own scripts | Other shared copies | Guard |
|---|---|---|---|---|---|
| [data-cost](../../plugins/data-engineer/skills/data-cost/SKILL.md)<br>`/data-engineer:data-cost [repo] [usage export, storage table, query log if elsewhere]` | Breaks a data platform's compute and storage spend down per cluster, job, pipeline and table, and finds spending with no use behind it, such as unread tables, needless full reloads, schedules faster than the reads and idle clusters. | Use when the platform bill grows or before a budget review. Choosing or pricing a cloud platform goes to cloud-design, the platform's design to data-review. | `cost_breakdown.py` | none | pre |
| [data-migration](../../plugins/data-engineer/skills/data-migration/SKILL.md)<br>`/data-engineer:data-migration [job inventory or crontab] [scripts folder] [as-of time]` | Inventories an old estate of scheduled jobs from its inventory and scripts, rates each job keep, rebuild or retire, and plans the move in waves with acceptance numbers, a parallel run and a rollback. | Use before moving cron jobs, an old warehouse or a legacy ETL estate onto a new platform. Choosing the new platform goes to data-platform, restructuring a software system to arch-evolve. | `estate_inventory.py` | none | pre |
| [data-product](../../plugins/data-engineer/skills/data-product/SKILL.md)<br>`/data-engineer:data-product [schema.table] [repo] [folder of sample data]` | Writes the consumer guide of one served table from its SQL, sample, query log, checks and documents, with its real grain, metric definitions, freshness and personal columns, naming every conflict between documents. | Use when a served table gets new consumers or its document is in doubt. One metric whose numbers differ between teams goes to metric-spec, lineage of the whole platform to data-map. | `product_facts.py` | `data_profile.py` | pre + personal |
| [data-quality](../../plugins/data-engineer/skills/data-quality/SKILL.md)<br>`/data-engineer:data-quality [repository] [period] [tables that matter most]` | Summarises a platform's checks over a period, with what passed, warned and failed, the quarantine, freshness against each table's service level, checks that prove nothing, and a verdict per table. | Use when asked which tables are safe to use today, what the checks stopped or how far to trust them. A design review of models and loads goes to data-review, a report's counting to report-review. | `quality_summary.py` | `data_profile.py` | pre + personal |
| [pipeline-incident](../../plugins/data-engineer/skills/pipeline-incident/SKILL.md)<br>`/data-engineer:pipeline-incident [repository] [run id, or job and day] [what the users see]` | Traces a failed data pipeline run from its records to the root cause, a workaround, two fixes, the same weakness elsewhere, e-mail drafts and the incident-log entry. | Use when a scheduled data load or transformation failed and its run records are at hand. Not for a live application or service outage (incident-triage), its write-up (postmortem) or a failing test (bug-hunt). | `run_trace.py` | `data_profile.py` | pre + personal |
| [source-contract](../../plugins/data-engineer/skills/source-contract/SKILL.md)<br>`/data-engineer:source-contract [contract file, or the source's delivery folders] [delivery log] [metadata document]` | Drafts or checks the data contract with a source system against what it really delivers, naming the conflicts with the files, the metadata document and the delivery log. | Use when a contract with a source system is to be written, agreed or checked against its deliveries. An unknown source is profiled first (source-profile); one metric's definition goes to metric-spec. | `contract_check.py` | `data_profile.py` | pre + personal |
| [source-profile](../../plugins/data-engineer/skills/source-profile/SKILL.md)<br>`/data-engineer:source-profile [delivery folder] [earlier deliveries] [vendor's document]` | Profiles a new source before any contract or pipeline exists, from file format and schema drift to null tokens, placeholders, duplicates, orphans, personal data and gaps against the vendor's document. | Use when a new source, feed or file set arrives and must be understood first. Not for a quick look at a table (the data plugin), a data contract (source-contract) or a platform design (data-review). | `source_format.py` | `data_profile.py` | pre + personal |

## software-architect

Four skills for software architects: arch-style, arch-c4, arch-review and arch-evolve. They decide what shape a system should have, draw it in C4 from a brief or from the code, review a design before it is built, and plan the way to a target in safe steps. Each counts with its own scripts and ends in one self-contained web page.

| Skill | What it does | When to use it | Own scripts | Other shared copies | Guard |
|---|---|---|---|---|---|
| [arch-c4](../../plugins/software-architect/skills/arch-c4/SKILL.md)<br>`/software-architect:arch-c4 [repository, or a brief or arch-style page]` | Draws a software system in C4 on one clickable page, with context, containers and components, requests traced hop by hop and every box tied to the code or marked as a guess. | Use when a software system must be drawn and explained, from a brief or from its repository. | `c4_check.py` | `code_graph.py`, `containers.py` | pre |
| [arch-evolve](../../plugins/software-architect/skills/arch-evolve/SKILL.md)<br>`/software-architect:arch-evolve [repository] [target, or an arch-style page]` | Plans the move from a system's current structure to a target in steps that each leave it working, with how each step is verified and undone. | Use when splitting a monolith, extracting a service, untangling modules or replacing a part without stopping delivery. | none | `code_graph.py`, `containers.py` | pre |
| [arch-review](../../plugins/software-architect/skills/arch-review/SKILL.md)<br>`/software-architect:arch-review [design documents or folder] [the goals that matter most]` | Reviews a software design from its documents and ADRs for what will make it fail or hard to change, such as waiting chains that miss latency goals, shared data, promises with no mechanism and open decisions. | Use before a design document, proposal or set of ADRs is approved or built. Not for code that exists (use code-audit). | `design_inventory.py` | none | pre |
| [arch-style](../../plugins/software-architect/skills/arch-style/SKILL.md)<br>`/software-architect:arch-style [brief file or text]` | Decides what shape a software system should have, from one deployable to microservices, by ruling options out against the team and the brief, with fitness rules and an ADR draft. | Use before building or restructuring a system, when a brief arrives or someone proposes microservices. | `style_rules.py` | none | pre |

## cloud-architect

Three skills for cloud architects: cloud-map, cloud-design and cloud-review. They draw the cloud infrastructure that exists from code in a repository with no login or from a read-only export, compare a brief across options with real prices, and review it against the provider's Well-Architected pillars. Each counts with its own scripts and ends in one self-contained web page. Azure first.

| Skill | What it does | When to use it | Own scripts | Other shared copies | Guard |
|---|---|---|---|---|---|
| [cloud-design](../../plugins/cloud-architect/skills/cloud-design/SKILL.md)<br>`/cloud-architect:cloud-design [brief file or text] [saved price table]` | Decides what a system should run on in the cloud and compares up to two variants or two clouds, costed from each provider's price list, with an ADR draft. | Use before building or moving a system to the cloud, when a brief arrives or a platform such as AKS or App Service is being picked. | `cloud_rules.py` | `cloud_prices.py` | pre |
| [cloud-map](../../plugins/cloud-architect/skills/cloud-map/SKILL.md)<br>`/cloud-architect:cloud-map [repository] [saved export]` | Draws cloud infrastructure from Terraform, Bicep, ARM, CloudFormation or a saved export as nested boxes, with request flows, what the internet reaches and drift between code and account. | Use when you inherit cloud infrastructure or must explain it, from infrastructure code or a read-only export, with no cloud login. | none | `cloud_inventory.py` | pre |
| [cloud-review](../../plugins/cloud-architect/skills/cloud-review/SKILL.md)<br>`/cloud-architect:cloud-review [repository] [saved export] [brief or requirements]` | Reviews cloud infrastructure code or a saved export against the provider's Well-Architected pillars, with problems tied to file:line or a resource and what to fix first. | Use before a release, an audit or a takeover of cloud infrastructure. | none | `cloud_inventory.py` | pre |

## solutions-architect

Two skills that sit on top of the specialist architect packs and own the whole solution: solution-brief frames a client brief once and sends the right specialists with shared facts, and solution-blueprint joins their pages into one solution and names what contradicts. Installing this pack installs the four specialist packs.

| Skill | What it does | When to use it | Own scripts | Other shared copies | Guard |
|---|---|---|---|---|---|
| [solution-blueprint](../../plugins/solutions-architect/skills/solution-blueprint/SKILL.md)<br>`/solutions-architect:solution-blueprint [pages folder or page JSON files]` | Joins the specialist pages of one project into one solution, names every conflict between them with the side it recommends, and says what to do first. | Use when the AI, data, software and cloud pages for one project exist. Not for deciding one area (use ai-pattern, data-platform, arch-style or cloud-design). | `join_facts.py` | none | pre |
| [solution-brief](../../plugins/solutions-architect/skills/solution-brief/SKILL.md)<br>`/solutions-architect:solution-brief [brief file or text]` | Frames a client brief that spans several areas once and says which specialist skills to run, in which order, with the shared facts each must use. | Use when a brief arrives that may span AI, data, software and cloud, before any one area is decided. Not for a question inside one area. | none | none | pre |

## data-analyst

Four skills for data analysts: metric-spec, number-moved, number-reconcile and report-review. They write the one definition of a metric, explain why a number changed in effects that add up exactly, account for the whole gap between two numbers, and check a report's counting before it goes out. Each counts with its own scripts and ends in one self-contained web page.

| Skill | What it does | When to use it | Own scripts | Other shared copies | Guard |
|---|---|---|---|---|---|
| [metric-spec](../../plugins/data-analyst/skills/metric-spec/SKILL.md)<br>`/data-analyst:metric-spec [repository or report folder] [metric name] [folder of sample data]` | Writes the one definition of a business metric that everyone will use, from the SQL, dbt models or reports that compute it and a sample of its data. | Use when two teams or reports show different numbers for the same metric, or before a metric goes on a dashboard or into a target. | `metric_compare.py` | `data_profile.py`, `measure.py`, `sql_inventory.py` | pre + personal |
| [number-moved](../../plugins/data-analyst/skills/number-moved/SKILL.md)<br>`/data-analyst:number-moved [data file] [the number and the two periods] [definition, repo or SQL behind it]` | Explains why a business number changed between two periods, checking for late or missing data first, then splitting the change into effects that add up exactly. | Use when someone asks why a reported number moved and the rows behind it are in a CSV or JSON Lines file. Not for a trend question with no data file. | `decompose.py` | `data_profile.py`, `measure.py` | pre + personal |
| [number-reconcile](../../plugins/data-analyst/skills/number-reconcile/SKILL.md)<br>`/data-analyst:number-reconcile [file or query behind number A] [file or query behind number B] [the window] [the key that joins them]` | Finds exactly where two numbers that should agree part ways and accounts for the whole difference, or says how much remains unexplained. | Use when two systems, reports or extracts give different figures for the same thing and the rows behind both are available. | `reconcile.py` | `data_profile.py`, `measure.py` | pre + personal |
| [report-review](../../plugins/data-analyst/skills/report-review/SKILL.md)<br>`/data-analyst:report-review [report folder] [folder of sample data]` | Checks the counting behind an analysis against its data, such as double counting, wrong denominators, dropped rows, partial periods and misleading charts. | Use before a report or analysis with its SQL or notebook goes out. Not for general feedback with no code or data behind it. | `report_check.py` | `data_profile.py`, `measure.py`, `sql_inventory.py` | pre + personal |

## data-scientist

Five skills for data scientists: ds-frame, ds-explore, ds-dataset, ds-evaluate and ds-experiment. They decide before modelling whether a rule, a score or a real model should be built, explore what in a table relates to the target, audit a training set for leakage, compare models from files of predictions so noise is called noise, and read A/B tests so a broken split or a win that does not survive correction cannot pass. Each computes with its own scripts and ends in one self-contained web page.

| Skill | What it does | When to use it | Own scripts | Other shared copies | Guard |
|---|---|---|---|---|---|
| [ds-dataset](../../plugins/data-scientist/skills/ds-dataset/SKILL.md)<br>`/data-scientist:ds-dataset [train file] [test file] [label column] [repository of the modelling code]` | Audits a training set for target and time leakage, entities on both sides of a split, duplicates across splits, drift and personal columns. | Use before trusting a predictive model, when the train and test files and the label are at hand. Not for profiling an ordinary table. | `dataset_audit.py` | `data_profile.py`, `measure.py`, `model_stats.py` | pre + personal |
| [ds-evaluate](../../plugins/data-scientist/skills/ds-evaluate/SKILL.md)<br>`/data-scientist:ds-evaluate [predictions file(s)] [baseline column] [costs of a false positive and a false negative]` | Says which trained model is really better than the baseline and which differences are noise, with intervals, calibration, a cost-based threshold and the worst slices. | Use when comparing predictive models from a file of predictions with the label. Not for evaluating an LLM or retrieval. | `model_eval.py` | `data_profile.py`, `measure.py`, `model_stats.py` | pre + personal |
| [ds-experiment](../../plugins/data-scientist/skills/ds-experiment/SKILL.md)<br>`/data-scientist:ds-experiment [plan numbers, or experiment file] [variant, unit and metric columns] [expected split, guardrails with margins]` | Sizes an A/B test or reads its result, checking the sample ratio first, correcting for several metrics and ending in ship, do not ship or inconclusive. | Use when a randomised experiment is being planned or has finished. Not for a before-and-after comparison. | `ab_test.py` | `data_profile.py`, `measure.py`, `model_stats.py` | pre + personal |
| [ds-explore](../../plugins/data-scientist/skills/ds-explore/SKILL.md)<br>`/data-scientist:ds-explore [data file] [column to predict] [time column and how long until the outcome is known]` | Explores what relates to a yes/no target in one table before any model, including its rate over time, unknown codes, feature strength with intervals and columns to check for leakage. | Use before building a predictive model when nobody has looked at the data yet. Not for a table with no target, or an existing train and test split (use ds-dataset). | `explore_target.py` | `data_profile.py`, `measure.py`, `model_stats.py` | pre + personal |
| [ds-frame](../../plugins/data-scientist/skills/ds-frame/SKILL.md)<br>`/data-scientist:ds-frame [brief file or text] [folder of history data]` | Decides whether a rule, a simple score or a real model is the right thing to build, names the baseline to beat and writes acceptance criteria. | Use before building a predictive model, when someone asks for one and the decision, target, label or error costs are still open. Not for an LLM solution (use ai-pattern). | `frame_rules.py` | `data_profile.py`, `measure.py` | pre + personal |

## workflows

Seven process workflows that chain the skills of the other packs, each step reading the previous step's page: take-over, ship-change, incident-run, data-incident, new-solution, platform-month and model-build. Each ends in one page that says what was found and whether the chain is done. Installing this pack installs every other pack.

| Skill | What it does | When to use it | Own scripts | Other shared copies | Guard |
|---|---|---|---|---|---|
| [data-incident](../../plugins/workflows/skills/data-incident/SKILL.md)<br>`/workflows:data-incident [run records or pipeline]` | Runs a failed data load from the run records to a safe rerun in one chain, pipeline-incident, source-contract when the source changed, and data-quality after the rerun, and ends in one page that says which tables are safe. | Use when a scheduled load or transformation failed and the team wants cause, contract and a checked rerun in one go. The trace alone goes to pipeline-incident. | none | `chain_status.py` | pre |
| [incident-run](../../plugins/workflows/skills/incident-run/SKILL.md)<br>`/workflows:incident-run [alert, logs or service]` | Runs an incident from the alert to the write-up in one chain, incident-triage, bug-hunt, change-review of the fix and postmortem, and ends in one page that says whether the incident is closed. | Use when an alert fires or production misbehaves and the team wants triage, cause, fix and write-up in one go. Triage alone goes to incident-triage. | none | `chain_status.py` | pre |
| [model-build](../../plugins/workflows/skills/model-build/SKILL.md)<br>`/workflows:model-build [decision, data files]` | Takes a prediction request to a decision in one chain, ds-frame, ds-explore, ds-dataset, ds-evaluate and ds-experiment, each step reading the previous page, and ends in one page that says ship, do not ship or inconclusive. | Use when someone asks for a prediction or a model and the team wants framing, data checks, evaluation and the experiment read in one go. One of those alone goes to its own skill. | none | `chain_status.py` | pre |
| [new-solution](../../plugins/workflows/skills/new-solution/SKILL.md)<br>`/workflows:new-solution [brief]` | Takes a client brief to a reviewed solution in one chain, solution-brief, the specialists it names, solution-blueprint and the reviews, and ends in one page that says whether the solution holds together. | Use when a brief arrives that spans AI, data, software or cloud and must end in one reviewed solution. One area alone goes to that area's skills. | none | `chain_status.py` | pre |
| [platform-month](../../plugins/workflows/skills/platform-month/SKILL.md)<br>`/workflows:platform-month [platform repo and month]` | Runs the monthly review of a data platform in one chain, data-quality, data-cost and data-product for the tables that gained consumers, and ends in one page that says what to stop, what to fix and who decides. | Use when a month closes on a data platform and the team wants quality, cost and the served tables checked in one go. One of those alone goes to its own skill. | none | `chain_status.py` | pre |
| [ship-change](../../plugins/workflows/skills/ship-change/SKILL.md)<br>`/workflows:ship-change [branch or diff]` | Takes a change from branch to mergeable in one chain, impact, change-review, bug-hunt when a test fails, and docs-draft for the changelog, and ends in one page that says whether it can merge. | Use when a branch is ready and must be checked, fixed and documented before it merges. A review alone goes to change-review. | none | `chain_status.py` | pre |
| [take-over](../../plugins/workflows/skills/take-over/SKILL.md)<br>`/workflows:take-over [repo]` | Owns a repository you did not write in one chain, codebase-map, code-audit, dependency-audit, test-gap and docs-draft, each step reading the previous page, and ends in one page that says what was found and whether the chain is done. | Use when a repository arrives that the team must own, before changing it. One of those jobs alone goes to its own skill. | none | `chain_status.py` | pre |

## How to regenerate

From the repository root, after a skill or a manifest changes:

```bash
awk '/^```$/{f=0} f; /^```python$/{f=1}' docs/reference/skills.md | python3 -
```

It runs the script below, which rewrites this file, the script included.

```python
"""Write docs/reference/skills.md from the marketplace, the pack manifests and the SKILL.md frontmatter.

Run from the repository root. Standard library only. The script is kept at the end of the file it writes.
"""

import json
import re
from pathlib import Path

ROOT = Path.cwd()
OUT = ROOT / "docs" / "reference" / "skills.md"
FENCE = "`" * 3
MARKET = ROOT / ".claude-plugin" / "marketplace.json"
if not MARKET.is_file():
    raise SystemExit("run this from the repository root")


def own_source() -> str:
    """This script's text: the python block at the end of the file it writes, or this file when run directly."""
    if OUT.is_file():
        lines, inside = [], False
        for line in OUT.read_text("utf-8").splitlines():
            if line == FENCE:
                inside = False
            if inside:
                lines.append(line)
            if line == FENCE + "python":
                inside = True
        if lines:
            return "\n".join(lines) + "\n"
    return Path(__file__).read_text("utf-8")


def frontmatter(path: Path) -> dict[str, str]:
    """The top-level scalar keys of a SKILL.md frontmatter, and the guard commands as `hooks`."""
    lines = path.read_text("utf-8").splitlines()
    end = lines.index("---", 1)
    keys: dict[str, str] = {"hooks": ""}
    for line in lines[1:end]:
        match = re.match(r"^([a-z_-]+):\s*(.*)$", line)
        if match and match.group(2):
            keys[match.group(1)] = match.group(2).strip().strip("\"'")
        if "guard.py" in line:
            keys["hooks"] += line
    return keys


def cell(text: str) -> str:
    return text.replace("|", "\\|").strip()


shared = {p.name for p in (ROOT / "shared").glob("*.py")}
market = json.loads(MARKET.read_text("utf-8"))
packs = []
for entry in market["plugins"]:
    folder = ROOT / entry["source"]
    manifest = json.loads((folder / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    skills = []
    for skill_md in sorted(folder.glob("skills/*/SKILL.md")):
        meta = frontmatter(skill_md)
        scripts = sorted(p.name for p in (skill_md.parent / "scripts").glob("*.py"))
        skills.append(
            {
                "name": meta.get("name", skill_md.parent.name),
                "path": skill_md.relative_to(ROOT).as_posix(),
                "description": meta.get("description", ""),
                "when": meta.get("when_to_use", ""),
                "argument": meta.get("argument-hint", ""),
                "own": [s for s in scripts if s not in shared],
                "copies": [s for s in scripts if s in shared],
                "personal": " personal" in meta["hooks"],
            }
        )
    packs.append({"entry": entry, "manifest": manifest, "skills": skills})

everywhere = set.intersection(*(set(s["copies"]) for p in packs for s in p["skills"]))
total = sum(len(p["skills"]) for p in packs)
out = [
    "# Packs and skills",
    "",
    "Generated from `.claude-plugin/marketplace.json`, each pack's `.claude-plugin/plugin.json` and the frontmatter",
    "and `scripts/` folder of each `SKILL.md`. Do not edit it by hand: change the manifest or the skill, then",
    "regenerate it (see [How to regenerate](#how-to-regenerate)). What each skill writes, in words, is in",
    "[product/features/](../product/features/).",
    "",
    f"{len(packs)} packs, {total} skills.",
    "",
    "| Pack | Version | Skills | Installs with it |",
    "|---|---|--:|---|",
]
for pack in packs:
    name = pack["entry"]["name"]
    deps = ", ".join(f"`{d}`" for d in pack["manifest"].get("dependencies", [])) or "nothing"
    out.append(f"| [{name}](#{name}) | {pack['manifest']['version']} | {len(pack['skills'])} | {deps} |")
out += [
    "",
    "Every skill carries copies of "
    + " and ".join(f"`shared/{s}`" for s in sorted(everywhere))
    + " in its `scripts/`. The table lists a skill's own scripts and its other copies from `shared/`. "
    "The guard column says how the skill's `hooks:` block calls `guard.py`: `pre` asks before changes and before "
    "going online; `pre + personal` also keeps personal data out (see "
    "[architecture/crosscutting.md](../architecture/crosscutting.md)).",
]
for pack in packs:
    name = pack["entry"]["name"]
    out += ["", f"## {name}", "", pack["manifest"]["description"], ""]
    out += [
        "| Skill | What it does | When to use it | Own scripts | Other shared copies | Guard |",
        "|---|---|---|---|---|---|",
    ]
    for s in pack["skills"]:
        call = f"`/{name}:{s['name']}" + (f" {s['argument']}`" if s["argument"] else "`")
        own = ", ".join(f"`{x}`" for x in s["own"]) or "none"
        copies = ", ".join(f"`{x}`" for x in s["copies"] if x not in everywhere) or "none"
        guard = "pre + personal" if s["personal"] else "pre"
        out.append(
            f"| [{s['name']}](../../{s['path']})<br>{cell(call)} | {cell(s['description'])} | {cell(s['when'])} "
            f"| {own} | {copies} | {guard} |"
        )
out += [
    "",
    "## How to regenerate",
    "",
    "From the repository root, after a skill or a manifest changes:",
    "",
    FENCE + "bash",
    "awk '/^" + FENCE + "$/{f=0} f; /^" + FENCE + "python$/{f=1}' docs/reference/skills.md | python3 -",
    FENCE,
    "",
    "It runs the script below, which rewrites this file, the script included.",
    "",
    FENCE + "python",
    own_source().rstrip("\n"),
    FENCE,
    "",
]
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(out), encoding="utf-8")
print(f"wrote {OUT.relative_to(ROOT)}: {len(packs)} packs, {total} skills")
```
