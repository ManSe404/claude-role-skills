# AWS

Everything AWS-specific a cloud skill needs to read. The scripts read `aws.json` (resource types, exposure rules,
review checks); this file is for Claude. Facts marked [high] were checked against docs.aws.amazon.com on 2026-11-10;
[med] are from memory or from the shape of the price list; check a limit or a price again when a decision depends on it.

## Infrastructure code

`cloud_inventory.py` reads Terraform (`aws_*`) and CloudFormation (JSON and YAML, with the short tags `!Ref`, `!GetAtt`,
`!Sub` and the rest). Both map to one normal form, the CloudFormation type, such as `AWS::RDS::DBInstance`. A few types
that exist only as a Terraform resource (`aws_s3_bucket_public_access_block`) get a name of the same shape so a check can
find them; CloudFormation sets those on the bucket itself.

What cannot be resolved is listed under `unresolved`, never guessed: `Fn::If` (`conditional-value`), a `Condition` on a
resource (`conditional`), `Fn::ImportValue` (`import-value`), `Transform`/`Fn::Transform` (`macro`), nested stacks
(`nested-stack`), `Fn::ForEach` (`loop`), a `Count` property (`count`), and Terraform `count`/`for_each`. Parameters
with a `Default` are used; a parameter with no default, or `NoEcho`, or a name that looks like a secret, stays unknown.

## Nesting

Account, region, VPC, subnet, resource. The inventory fills each resource's `nesting` with those four levels; a level
the code does not state is `null`. Account and region come from the Terraform `provider "aws"` block
(`allowed_account_ids`, `region`); a CloudFormation template states neither, because they belong to the deployment.

How to draw it in a `nested` block: one box for the account, a box for the region inside it (when known), the VPC
inside the region, each subnet inside the VPC. Group subnets by their zone when two zones mirror each other: public and
private in each of two zones is one picture. A resource that sits in several subnets (an ALB, an ECS service,
`also_in` in the inventory) goes in a box around those subnets, or in each with a note: pick what reads best and say
which. Regional services with no place in a network (S3, SQS, SNS, Secrets Manager, CloudWatch, IAM) go in the region's
box, outside the VPC, in a box called "Regional services". A resource with no account or region in its code goes in a
box called "Not placed by the code".

Show what matters inside a resource (target groups under a load balancer, the database in its subnet group); leave out
what adds nothing (route table associations, gateway attachments, bucket versioning resources) and say so in a note.

Levels: Account (only the region and VPCs open), Network (VPCs and subnets open), and everything open.

## The ladders, as AWS services

The neutral options from `cloud_rules.py`, as real services.

| Ladder | Option | AWS service |
|---|---|---|
| compute | managed_app_platform | App Runner, or Elastic Beanstalk [med: pick by who runs it] |
| compute | serverless_containers | ECS on Fargate |
| compute | functions | Lambda |
| compute | kubernetes | EKS |
| compute | virtual_machines | EC2, with an Auto Scaling group |
| data | managed_relational | RDS for PostgreSQL or MySQL, or Aurora |
| data | managed_relational_scaled | The same, with read replicas |
| data | managed_document | DynamoDB |
| data | self_managed | A database on EC2 |
| network | public_restricted | Public endpoints with security groups or an IP allow list |
| network | private_data | Compute in private subnets, RDS not publicly accessible, S3 and DynamoDB through gateway endpoints, others through interface endpoints; only the load balancer faces the internet |
| network | fully_private | Internal compute behind an ALB with WAF, or CloudFront with VPC origins |
| network | hub_and_spoke | Transit Gateway with a network firewall |
| region | one_region | One region inside the residency area |
| region | two_regions | A second region, with cross-region read replicas and S3 replication |
| availability | one_zone | The default: nothing spread across zones |
| availability | zone_redundant | Multi-AZ RDS, ECS tasks in subnets of at least two zones, an ALB in two zones, a NAT gateway per zone |
| availability | multi_region | Two regions with a tested failover |

Limits that change a design:

- An Application Load Balancer needs subnets in at least two availability zones [high].
- RDS Multi-AZ runs a standby in a second zone and is billed at about twice the Single-AZ rate, storage included [high:
  the price list shows it].
- A NAT gateway is zonal. One NAT gateway for two zones means the loss of its zone cuts outbound access for the other
  [med]. For zone redundancy price one per zone.
- A Fargate task in a private subnet pulls its image through a NAT gateway or through an interface endpoint for ECR
  [high]. Which is cheaper depends on data volume: price both when it matters.
- A task only runs in the subnets it is given; two zones need at least two subnets and `desired_count` of at least 2
  [med].
- An SQS, Secrets Manager, ECR or CloudWatch Logs call from a private subnet goes through a NAT gateway or an interface
  endpoint (billed per zone per hour); S3 and DynamoDB can use a free gateway endpoint [med].

## What public exposure means

`cloud_inventory.py` decides with the rules in `aws.json`. In words:

| Service | Public when | What closes it |
|---|---|---|
| Application or Network Load Balancer | `internal` is false or absent (Terraform), `Scheme` is `internet-facing` or absent (CloudFormation) | `internal = true`, `Scheme: internal` |
| RDS, Aurora | `publicly_accessible` true, and a security group admits the address. Left unset the default depends on the subnet group: private with one other than `default` [high] | `publicly_accessible = false` |
| S3 bucket | a bucket policy or an ACL allows `*`. New buckets block public access by default, but nothing in the code keeps that so [high]; a bucket with no block in the code is `restricted` until something reads it | all four public access block settings on |
| ECS service | tasks get a public IP (`assign_public_ip`) and a security group admits the address | no public IP; on its own that stops nothing that a load balancer forwards |
| EC2 instance | a public IP is asked for and a security group admits the address | no public IP (the subnet's auto-assign setting is the rest of the answer) |
| API Gateway, Lambda function URL | always, unless a REST API is private; `NONE` authorization means anonymous | a private API; an authorizer or `AWS_IAM` |
| EKS | the API server is public unless `endpoint_public_access` is false | a private endpoint |
| OpenSearch | a domain with no VPC | a VPC |
| SQS, SNS, Secrets Manager, KMS, ECR, DynamoDB | never "public" on a network sense: reached through a regional API with a signed request; a resource policy naming `*` is the exception | none needed; a resource policy that names principals |
| Security group ingress | an inbound rule from `0.0.0.0/0` or `::/0`; on its own it opens nothing unless something listens | a specific source |

Firewalls and private boundaries stop the `reach` walk: a Network Firewall, an ALB with a WAF association, a VPC endpoint,
and anything whose exposure is `private`, except an ECS service or an EC2 instance, which still receives what a load
balancer forwards. Reach follows target groups and listeners backwards, because a listener names its load balancer and
a service names its target group.

## The six pillars

The AWS Well-Architected Framework has six pillars [high]. Every review check in `aws.json` names one.

| Pillar | Asks | Hits usually from |
|---|---|---|
| Security | Is the data and access protected? | public exposure, secrets in environment variables, `Action: "*"`, plain HTTP |
| Reliability | Does it survive a fault, and how fast does it recover? | Single-AZ, one task, no dead-letter queue, no versioning, no deletion protection |
| Operational Excellence | Can the team see and change it safely? | no load balancer logs, no flow logs, unpinned images, drift from code |
| Performance Efficiency | Does it scale to its load? | previous-generation instances, no autoscaling |
| Cost Optimization | Is anything paid for and not needed? | logs kept forever, images never expired |
| Sustainability | Does it use only what it needs? | objects with no lifecycle, x86 where Arm works |

A check's pillar is a starting point. The review may move a finding to a different pillar if that is what it costs.

## A read-only export

Only after the user's yes. Say which account and region would be read and that it lists resources and their tags, not
their settings or secrets. Then run one of these yourself and save the JSON. Do not run anything that changes something.
Do not log in for the user: if `aws sts get-caller-identity` fails, say so and stop.

```bash
aws sts get-caller-identity --output json
aws resourcegroupstaggingapi get-resources --region REGION --output json > EXPORT.json
```

The tagging API returns only resources that are tagged or were tagged before [high]: an untagged resource shows up as
"only in code" and is not necessarily missing; say so on the page. It is per region: pass the same region the code uses.
Or, where AWS Config records the account:

```bash
aws configservice select-resource-config --expression "SELECT resourceId, resourceName, resourceType, awsRegion, accountId" --region REGION --output json > EXPORT.json
```

`--compare` and `--from-export` read both shapes. An ARN gives the type and the name; a name that only lives in a tag
(VPC, subnet, security group) comes from the `Name` tag. Security group rules, bucket policies, IAM and similar are not
compared: `aws.json` lists them. IAM is global, so it does not belong in a per-region export.

Never run `aws cloudformation get-template` or read a stack's parameters: those can carry values the template hid.

## Price list

`cloud_prices.py --online` reads AWS's public offer files, no login:
`https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<Offer>/current/<region>/index.json`, listed at
`https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json`. It streams each file to a temporary file with a
size ceiling (64 MB) and a total time limit: the files for small services are a few MB, AmazonRDS is about 25 MB, and
AmazonEC2 is 435 MB for one region, so EC2 items come back as `too_large` unless the ceiling is raised
(`--max-file-mb`). A file too large or too slow is reported per item, with how to use a saved table. A saved table's
rows have the same shape as what `--online` returns.

Offer code = `service` below. Find the code in the index if it is not listed here (SQS is `AWSQueueService`, not
`AmazonSQS`). Region is the region code, such as `eu-central-1`. `meter` is the usage type without the region prefix
(`EUC1-`). Prices are in USD. A free tier is a separate row (usage type starting `Global-`); leave it out, and say so.

| What | service | product | sku | meter | unit | quantity |
|---|---|---|---|---|---|---|
| ECS Fargate, x86 vCPU | AmazonECS | Compute | (none) | Fargate-vCPU-Hours:perCPU | hours | vCPU × 730 |
| ECS Fargate, x86 memory | AmazonECS | Compute | (none) | Fargate-GB-Hours | hours | GB × 730 |
| ECS Fargate, Arm vCPU | AmazonECS | Compute | ARM | Fargate-ARM-vCPU-Hours:perCPU | hours | vCPU × 730 |
| ECS Fargate, Arm memory | AmazonECS | Compute | ARM | Fargate-ARM-GB-Hours | hours | GB × 730 |
| Application Load Balancer | AWSELB | Load Balancer-Application | ELB:Balancing | LoadBalancerUsage | Hrs | 730 |
| ALB capacity units | AWSELB | Load Balancer-Application | ELB:Balancing | LCUUsage | LCU-Hrs | LCUs × 730 [med: LCUs come from the load] |
| NAT gateway, hours | AmazonEC2 | NAT Gateway | NGW:NatGateway | NatGateway-Hours | Hrs | 730 × gateways |
| NAT gateway, data | AmazonEC2 | NAT Gateway | NGW:NatGateway | NatGateway-Bytes | GB | GB a month |
| RDS instance | AmazonRDS | Database Instance | `<class> / PostgreSQL / Single-AZ or Multi-AZ / No license required` | InstanceUsage:`<class short>` or Multi-AZUsage:`<class short>` | Hrs | 730 |
| RDS storage, gp3 | AmazonRDS | Database Storage | General Purpose-GP3 / PostgreSQL / Single-AZ or Multi-AZ | RDS:GP3-Storage or RDS:Multi-AZ-GP3-Storage | GB-Mo | GB |
| RDS backup above free | AmazonRDS | Storage Snapshot | Any / Single-AZ | RDS:ChargedBackupUsage | GB-Mo | GB beyond the database size |
| S3 Standard storage | AmazonS3 | Storage | General Purpose / Standard | TimedStorage-ByteHrs | GB-Mo | GB |
| S3 PUT/LIST | AmazonS3 | API Request | S3-API-Tier1 / PUT/COPY/POST or LIST requests | Requests-Tier1 | Requests | requests a month |
| S3 GET | AmazonS3 | API Request | S3-API-Tier2 / GET and all other requests | Requests-Tier2 | Requests | requests a month |
| SQS standard | AWSQueueService | API Request | Standard / SQS-APIRequest-Tier1 | Requests-Tier1 | Requests | requests a month (one request for each 64 KB) |
| Secrets Manager secret | AWSSecretsManager | Secret | AWSSecretsManager-Secret | AWSSecretsManager-Secrets | Secrets | secrets [note: price is per secret per month] |
| KMS key | awskms | Encryption Key | (none) | eu-central-1-KMS-Keys | Keys | keys [the meter names its region] |
| Interface endpoint, hours | AmazonVPC | VpcEndpoint | PrivateLink / VPCE:VpcEndpoint | VpcEndpoint-Hours | Hrs | 730 × endpoints × zones |
| Interface endpoint, data | AmazonVPC | VpcEndpoint | PrivateLink / VPCE:VpcEndpoint | VpcEndpoint-Bytes | GB | GB a month |
| CloudWatch Logs ingestion | AmazonCloudWatch | Data Payload | Ingested Logs | DataProcessing-Bytes | GB | GB a month |
| CloudWatch Logs storage | AmazonCloudWatch | Storage Snapshot | Amazon CloudWatch Standard Storage pricing current | TimedStorage-ByteHrs | GB-Mo | GB kept |
| WAF web ACL | awswaf | Web Application Firewall | Web ACL | WebACL | month | 1 per ACL |
| WAF rule | awswaf | Web Application Firewall | Rule | Rule | month | rules |
| WAF requests | awswaf | Web Application Firewall | Request | Request | Request | requests a month |
| Data transfer out | AWSDataTransfer | Data Transfer | AWS Outbound / EU (Frankfurt) / External | DataTransfer-Out-Bytes | GB | GB a month; the free allowance is not in this row |
| Inter-zone data | AWSDataTransfer | Data Transfer | IntraRegion / EU (Frankfurt) / EU (Frankfurt) | DataTransfer-Regional-Bytes | GB | GB a month, both directions counted [med] |

The `<class short>` in a usage type abbreviates a size (db.m6i.2xlarge is `db.m6i.2xl`): when unsure, leave `meter`
out and give the full sku, then read what comes back as `ambiguous`. A price not listed here: find its row in the
saved table, or ask `--online` and read what comes back.
