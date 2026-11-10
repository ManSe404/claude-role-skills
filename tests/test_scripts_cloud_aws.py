"""The cloud-architect scripts on AWS: the acme-cloud-aws fixture and small cases of their own."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar
from urllib.error import HTTPError

import pytest
from conftest import ROOT, load, run_json
from test_fixture_acme_cloud_aws import (
    ADMIN,
    ALERTS,
    AZURE_PRICES,
    DATA,
    EXPORT,
    ONLY_IN_CODE,
    ONLY_IN_EXPORT,
    PLANTED_AT,
    PRICES,
    PUBLIC,
    REPORTS,
    RESOURCES,
    SECRET,
)

INVENTORY = ROOT / "shared" / "cloud_inventory.py"
PRICE = ROOT / "shared" / "cloud_prices.py"
AWS_FILE = ROOT / "shared" / "cloud" / "aws.json"

CHECK_FOR_PLANTED = {
    1: "database-publicly-accessible",
    2: "s3-no-public-access-block",
    3: "secret-in-settings",
    4: "sg-open-from-anywhere",
    5: "database-single-az",
    6: "no-load-balancer-logs",
    7: "iam-action-star",
    8: "unpinned-image",
}
PILLARS = {
    "Security",
    "Reliability",
    "Operational Excellence",
    "Performance Efficiency",
    "Cost Optimization",
    "Sustainability",
}


def inv(path: Path, *args: str) -> dict[str, Any]:
    result: dict[str, Any] = run_json(INVENTORY, str(path), *args)
    return result


def by_id(result: dict[str, Any]) -> dict[str, Any]:
    return {r["id"]: r for r in result["resources"]}


def hits_of(result: dict[str, Any], check: str) -> list[dict[str, Any]]:
    return [h for family in result["checks"].values() for h in family if h["check"] == check]


@pytest.fixture(scope="module")
def full(aws_repo: Path) -> dict[str, Any]:
    return inv(aws_repo, "--checks", "--compare", str(aws_repo / EXPORT))


def write(tmp: Path, name: str, text: str) -> None:
    path = tmp / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def stdout_of(tmp: Path, *args: str) -> str:
    return subprocess.run(
        [sys.executable, str(INVENTORY), str(tmp), *args], capture_output=True, text=True, check=True
    ).stdout


# ---------------------------------------------------------------------------- cloud_inventory on the fixture


def test_every_format_is_read_and_counted(full: dict[str, Any]) -> None:
    assert full["summary"]["resources"] == RESOURCES and full["providers"] == ["aws"]
    assert full["levels"]["aws"] == ["account", "region", "vpc", "subnet"]
    assert "infra/terraform/app.tf" in full["read"]["terraform"]
    assert sorted(full["read"]["cloudformation"]) == sorted([ADMIN, ALERTS, REPORTS])
    assert full["summary"]["helpers_skipped"] == 1  # the random_id
    assert full["summary"]["by_category"]["compute"] == 7


def test_a_resource_has_the_normalised_shape(full: dict[str, Any]) -> None:
    db = by_id(full)["aws_db_instance.main"]
    assert db["type"] == "AWS::RDS::DBInstance" and db["category"] == "database"
    assert db["name"] == "stagefront-tickets-prod" and db["location"] == "eu-central-1"
    assert db["file"] == DATA and db["attributes"]["publicly_accessible"] is True
    assert db["attributes"]["multi_az"] is False and db["attributes"]["size"] == "db.m6i.large"


@pytest.mark.parametrize(
    ("rid", "account", "region", "vpc", "subnet"),
    [
        ("aws_lb.web", "000000000000", "eu-central-1", "stagefront-prod-vpc", "stagefront-prod-public-a"),
        ("aws_ecs_service.portal", "000000000000", "eu-central-1", "stagefront-prod-vpc", "stagefront-prod-private-a"),
        ("aws_db_instance.main", "000000000000", "eu-central-1", "stagefront-prod-vpc", "stagefront-prod-db"),
        ("aws_subnet.private_b", "000000000000", "eu-central-1", "stagefront-prod-vpc", None),
        ("aws_vpc.main", "000000000000", "eu-central-1", None, None),
        (f"{REPORTS}:ReportsBucket", None, None, None, None),
    ],
)
def test_nesting_is_followed_to_the_top(
    full: dict[str, Any], rid: str, account: str | None, region: str | None, vpc: str | None, subnet: str | None
) -> None:
    nesting = by_id(full)[rid]["nesting"]
    assert (nesting["account"], nesting["region"], nesting["vpc"], nesting["subnet"]) == (account, region, vpc, subnet)


def test_a_resource_in_two_subnets_says_so(full: dict[str, Any]) -> None:
    assert by_id(full)["aws_ecs_service.portal"]["also_in"] == {"subnet": ["stagefront-prod-private-b"]}


def test_an_ecs_service_sits_under_its_cluster(full: dict[str, Any]) -> None:
    rows = by_id(full)
    assert rows["aws_ecs_service.portal"]["parent"] == "aws_ecs_cluster.main"


def test_modules_get_a_prefix_and_their_inputs(full: dict[str, Any]) -> None:
    queue = by_id(full)["module.orders_queue.aws_sqs_queue.main"]
    assert queue["name"] == "stagefront-prod-orders" and queue["module"] == "module.orders_queue"


def test_terraform_tags_give_a_name_when_the_resource_has_no_name_attribute(full: dict[str, Any]) -> None:
    assert by_id(full)["aws_vpc.main"]["name"] == "stagefront-prod-vpc"


def test_cloudformation_yaml_is_read_with_lines_and_references(full: dict[str, Any]) -> None:
    rows = by_id(full)
    bucket = rows[f"{REPORTS}:ReportsBucket"]
    assert bucket["name"] == "stagefront-reports-prod" and bucket["line"] == 16 and bucket["format"] == "cloudformation"
    policy = rows[f"{REPORTS}:ReportsBucketPolicy"]
    assert policy["parent"] == f"{REPORTS}:ReportsBucket"
    lam = rows[f"{REPORTS}:ReportBuilder"]
    assert lam["conditional"] is True
    assert lam["attributes"]["settings"]["QUEUE_URL"] == "<unknown: Ref ReportRequests>"
    assert lam["attributes"]["settings"]["LOG_LEVEL"].startswith("<unknown: Fn::If IsProd")
    assert {(r["to"], r["kind"]) for r in lam["references"]} >= {
        (f"{REPORTS}:ReportRequests", "uses"),
        (f"{REPORTS}:ReportsBucket", "uses"),
    }


def test_cloudformation_json_is_read_the_same_way(full: dict[str, Any]) -> None:
    rows = by_id(full)
    alarm = rows[f"{ALERTS}:DatabaseCpuAlarm"]
    assert alarm["name"] == "stagefront-db-cpu" and alarm["line"] > 1
    assert (f"{ALERTS}:AlertTopic", "uses") in {(r["to"], r["kind"]) for r in alarm["references"]}


def test_an_inline_security_group_rule_keeps_its_own_line(full: dict[str, Any]) -> None:
    rule = by_id(full)[f"{ADMIN}:AdminSecurityGroup/Properties.SecurityGroupIngress[0]"]
    assert rule["attributes"]["source"] == "0.0.0.0/0" and rule["attributes"]["port"] == 22
    assert rule["parent"] == f"{ADMIN}:AdminSecurityGroup"


def test_what_could_not_be_read_is_reported_not_guessed(full: dict[str, Any]) -> None:
    kinds = {(u["kind"], u["resource"]) for u in full["unresolved"]}
    assert ("nested-stack", f"{ALERTS}:SharedDashboards") in kinds
    assert ("conditional", f"{REPORTS}:ReportBuilder") in kinds
    assert ("conditional-value", f"{REPORTS}:ReportBuilder") in kinds
    assert ("dynamic-name", "aws_s3_bucket.tickets") in kinds
    assert by_id(full)["aws_s3_bucket.tickets"]["name_unknown"] == "random_id.suffix.hex"


def test_public_exposure_is_computed_with_a_reason(full: dict[str, Any]) -> None:
    exposure = full["exposure"]
    assert {r["id"] for r in exposure["public"]} == PUBLIC
    reasons = {r["id"]: r for r in exposure["public"]}
    assert (
        reasons["aws_db_instance.main"]["why"] == "publicly accessible, and a security group opens it to every address"
    )
    assert reasons[f"{REPORTS}:ReportsBucket"]["anonymous"] is True
    assert reasons[f"{ADMIN}:AdminHost"]["why"].startswith("a public IP")
    private = {r["id"] for r in exposure["private"]}
    assert {"aws_s3_bucket.tickets", "aws_s3_bucket.backups", "aws_ecs_service.portal"} <= private
    restricted = {r["id"] for r in exposure["restricted"]}
    assert "aws_secretsmanager_secret.db" in restricted


def test_reach_runs_from_the_load_balancer_through_the_service(full: dict[str, Any]) -> None:
    reach = {r["to"]: r for r in full["exposure"]["reach"]}
    path = reach["aws_ecs_service.portal"]["path"]
    assert path == [
        "internet",
        "aws_lb.web",
        "aws_lb_listener.https",
        "aws_lb_target_group.portal",
        "aws_ecs_service.portal",
    ]
    assert reach["aws_ecs_service.portal"]["behind_stop"] is False  # a private service is still fed by the balancer
    assert reach["aws_db_instance.main"]["path"] == ["internet", "aws_db_instance.main"]
    assert "aws_secretsmanager_secret.db" in reach
    assert {s["id"] for s in full["exposure"]["stops"]} >= {"aws_s3_bucket.tickets"}


def test_the_open_security_group_rules_are_reported(full: dict[str, Any]) -> None:
    rules = {r["id"]: r for r in full["exposure"]["permissive_rules"]}
    admin = rules[f"{ADMIN}:AdminSecurityGroup/Properties.SecurityGroupIngress[0]"]
    assert admin["port"] == 22 and admin["source"] == "0.0.0.0/0" and admin["line"] == 27
    assert f"{ADMIN}:AdminHost" in admin["attached_to"]
    db_rule = rules["aws_security_group_rule.db_load_test"]
    assert "aws_db_instance.main" in db_rule["attached_to"]


@pytest.mark.parametrize("number", sorted(PLANTED_AT), ids=[f"planted-{n}" for n in sorted(PLANTED_AT)])
def test_every_planted_problem_has_a_hit_at_its_line(full: dict[str, Any], number: int) -> None:
    file, _, line = PLANTED_AT[number].rpartition(":")
    assert (file, int(line)) in {(h["file"], h["line"]) for h in hits_of(full, CHECK_FOR_PLANTED[number])}


def test_clean_resources_have_no_such_hits(full: dict[str, Any]) -> None:
    flagged = {(h["check"], h["resource"]) for family in full["checks"].values() for h in family}
    assert ("s3-no-public-access-block", "aws_s3_bucket.tickets") not in flagged
    assert ("unpinned-image", "aws_ecs_task_definition.portal") not in flagged
    assert ("queue-no-dead-letter", "module.orders_queue.aws_sqs_queue.main") not in flagged
    assert not any(c == "sg-open-from-anywhere" and "alb" in r for c, r in flagged)  # 443 on the load balancer
    assert ("secret-in-settings", "aws_ecs_task_definition.worker") not in flagged


def test_every_check_names_one_of_the_six_pillars() -> None:
    table = json.loads(AWS_FILE.read_text(encoding="utf-8"))
    used = {check["pillar"] for check in table["checks"]}
    assert used == PILLARS
    families = {check["family"] for check in table["checks"]}
    review = (ROOT / "plugins/cloud-architect/skills/cloud-review/references/review.md").read_text(encoding="utf-8")
    for family in families:
        assert f"| {family} |" in review, family


def test_drift_finds_the_one_only_in_code_and_the_one_only_in_export(full: dict[str, Any]) -> None:
    compare = full["compare"]
    assert [r["id"] for r in compare["only_in_code"]] == [ONLY_IN_CODE[0]]
    assert [(r["type"], r["name"]) for r in compare["only_in_export"]] == [ONLY_IN_EXPORT]
    assert compare["not_comparable"] == [
        {
            "id": "aws_s3_bucket.tickets",
            "type": "AWS::S3::Bucket",
            "why": "the name is not known from the code: random_id.suffix.hex",
            "candidates": ["stagefront-tickets-a1b2c3"],
        }
    ]
    assert compare["differences"] == []
    assert len(compare["in_both"]) == 35


def test_no_secret_value_reaches_stdout_on_the_fixture(aws_repo: Path) -> None:
    for args in ([], ["--checks"], ["--compare", str(aws_repo / EXPORT)]):
        out = stdout_of(aws_repo, *args)
        assert SECRET not in out
        assert "<hidden: looks like a secret>" in out


# ---------------------------------------------------------------------------- the YAML reader and CloudFormation


TEMPLATE = """AWSTemplateFormatVersion: "2010-09-09"
Description: >-
  A small template, with a folded description.
# a comment at the top
Parameters:
  Env:
    Type: String
    Default: prod
  DbPassword:
    Type: String
    NoEcho: true
    Default: hunter2-noecho-do-not-print
  ApiKeyValue:
    Type: String
    Default: hunter2-named-do-not-print
Mappings:
  Sizes:
    prod:
      db: db.m6i.large
Conditions:
  IsProd: !Equals [!Ref Env, prod]
Resources:
  Vpc:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: "10.0.0.0/16"
      Tags: [{Key: Name, Value: !Sub "vpc-${Env}"}]
  Subnet:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId: !Ref Vpc
      CidrBlock: 10.0.0.0/24 # trailing comment
  "Db":
    Type: "AWS::RDS::DBInstance"
    DependsOn: Subnet
    Properties:
      DBInstanceIdentifier: !Join ["-", ["db", !Ref Env]]
      DBInstanceClass: !FindInMap [Sizes, !Ref Env, db]
      MasterUserPassword: !Ref DbPassword
      Engine: postgres
      PubliclyAccessible: 'true'
      AllocatedStorage: 100
      VPCSecurityGroups:
        - !GetAtt Sg.GroupId
      EnableCloudwatchLogsExports:
        - postgresql
  Sg:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: >
        Multi-line description
        in a block.
      VpcId:
        Ref: Vpc
      SecurityGroupIngress:
        - CidrIp: 0.0.0.0/0
          FromPort: 443
          ToPort: 443
          IpProtocol: tcp
        - { CidrIp: "::/0", FromPort: 5432, ToPort: 5432, IpProtocol: tcp }
  Task:
    Type: AWS::ECS::TaskDefinition
    Properties:
      Family: task
      ContainerDefinitions:
        - Name: app
          Image: !Sub "000000000000.dkr.ecr.${AWS::Region}.amazonaws.com/app:latest"
          Environment:
            - Name: API_SECRET
              Value: hunter2-env-do-not-print
            - Name: URL
              Value: !Sub
                - "https://${Host}/x"
                - { Host: example.com }
  Picked:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Select [0, ["first-bucket", "second-bucket"]]
      AccessControl: PublicRead
"""


def test_a_small_template_is_read_with_every_short_form(tmp_path: Path) -> None:
    write(tmp_path, "stack.yaml", TEMPLATE)
    result = inv(tmp_path, "--checks")
    rows = by_id(result)
    assert result["read"]["cloudformation"] == ["stack.yaml"]
    db = rows["stack.yaml:Db"]
    assert db["name"] == "db-prod" and db["attributes"]["size"] == "db.m6i.large"
    assert db["attributes"]["publicly_accessible"] == "true"  # a quoted 'true' stays a string, as in the template
    assert {r["to"] for r in rows["stack.yaml:Subnet"]["references"]} == {"stack.yaml:Vpc"}
    assert rows["stack.yaml:Vpc"]["name"] == "vpc-prod"
    assert rows["stack.yaml:Subnet"]["nesting"]["vpc"] == "vpc-prod"
    assert rows["stack.yaml:Picked"]["name"] == "first-bucket"
    assert rows["stack.yaml:Db"]["references"][0]["to"] == "stack.yaml:Sg"
    task = rows["stack.yaml:Task"]
    assert task["attributes"]["images"] == "<unknown: Sub AWS::Region>"
    assert task["attributes"]["settings"]["URL"] == "https://example.com/x"


def test_short_forms_and_secrets_never_leak(tmp_path: Path) -> None:
    write(tmp_path, "stack.yaml", TEMPLATE)
    out = stdout_of(tmp_path, "--checks")
    assert "hunter2" not in out
    result = json.loads(out)
    rows = by_id(result)
    assert rows["stack.yaml:Db"]["attributes"]["master_password"] == "<unknown: parameter DbPassword>"
    assert rows["stack.yaml:Task"]["attributes"]["settings"]["API_SECRET"] == "<hidden: looks like a secret>"
    assert len(hits_of(result, "secret-in-settings")) == 1


def test_an_inline_rule_written_as_a_flow_mapping_is_a_child(tmp_path: Path) -> None:
    write(tmp_path, "stack.yaml", TEMPLATE)
    result = inv(tmp_path)
    rows = by_id(result)
    children = [r for rid, r in rows.items() if rid.startswith("stack.yaml:Sg/")]
    sources = sorted(str(r["attributes"].get("source", r["attributes"].get("source_v6"))) for r in children)
    assert sources == ["0.0.0.0/0", "::/0"]


def test_a_json_template_with_long_form_functions_is_read(tmp_path: Path) -> None:
    doc = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Parameters": {"Name": {"Type": "String", "Default": "web"}},
        "Resources": {
            "Topic": {
                "Type": "AWS::SNS::Topic",
                "Properties": {"TopicName": {"Fn::Join": ["-", [{"Ref": "Name"}, "alerts"]]}},
            },
            "Db": {
                "Type": "AWS::RDS::DBInstance",
                "Properties": {"DBInstanceIdentifier": {"Fn::Sub": "${Name}-db"}, "PubliclyAccessible": True},
            },
        },
    }
    write(tmp_path, "t.template", json.dumps(doc, indent=2))
    rows = by_id(inv(tmp_path))
    assert rows["t.template:Topic"]["name"] == "web-alerts"
    assert rows["t.template:Db"]["name"] == "web-db"
    assert rows["t.template:Db"]["exposure"]["state"] == "restricted"


@pytest.mark.parametrize(
    ("resource", "kind"),
    [
        (
            "  Macro:\n    Type: AWS::Lambda::Function\n    Properties:\n"
            "      Fn::Transform:\n        Name: AWS::Include\n",
            "macro",
        ),
        (
            "  Imports:\n    Type: AWS::SNS::Topic\n    Properties:\n      TopicName:\n"
            "        Fn::ImportValue: shared-name\n",
            "import-value",
        ),
        ("  Picky:\n    Type: AWS::SNS::Topic\n    Condition: IsProd\n    Properties: {}\n", "conditional"),
        (
            "  Nested:\n    Type: AWS::CloudFormation::Stack\n    Properties:\n"
            "      TemplateURL: https://templates.example.com/x.yaml\n",
            "nested-stack",
        ),
        ("  Many:\n    Type: AWS::SNS::Topic\n    Count: 3\n    Properties: {}\n", "count"),
        (
            "  Fn::ForEach::Queues:\n    - Name\n    - [a, b]\n    - Queue${Name}:\n        Type: AWS::SQS::Queue\n",
            "loop",
        ),
        (
            "  Value:\n    Type: AWS::SNS::Topic\n    Properties:\n      TopicName: !If [IsProd, a, b]\n",
            "conditional-value",
        ),
    ],
    ids=["macro", "import", "conditional", "nested", "count", "foreach", "fn-if"],
)
def test_what_a_template_hides_is_reported(tmp_path: Path, resource: str, kind: str) -> None:
    write(tmp_path, "s.yaml", f"AWSTemplateFormatVersion: '2010-09-09'\nResources:\n{resource}")
    result = inv(tmp_path)
    assert kind in {u["kind"] for u in result["unresolved"]}
    if kind == "loop":
        assert result["resources"] == []


def test_a_transform_at_the_top_is_a_macro(tmp_path: Path) -> None:
    template = "Transform: AWS::Serverless-2016-10-31\nResources:\n  T:\n    Type: AWS::SNS::Topic\n"
    write(tmp_path, "sam.yaml", template)
    result = inv(tmp_path)
    macro = [u for u in result["unresolved"] if u["kind"] == "macro"]
    assert macro and "AWS::Serverless-2016-10-31" in macro[0]["detail"]


def test_an_anchor_is_a_parse_error_and_other_yaml_is_ignored(tmp_path: Path) -> None:
    write(tmp_path, "broken.yaml", "Resources:\n  A: &a\n    Type: AWS::SNS::Topic\n")
    write(tmp_path, "compose.yaml", "services:\n  web:\n    image: x\n")
    write(tmp_path, ".github/workflows/ci.yml", "name: ci\non: push\n")
    result = inv(tmp_path)
    assert [u["file"] for u in result["unresolved"] if u["kind"] == "parse-error"] == ["broken.yaml"]
    assert result["read"]["cloudformation"] == []


def test_parameter_files_are_not_read(tmp_path: Path) -> None:
    write(tmp_path, "stack.yaml", "Resources:\n  T:\n    Type: AWS::SNS::Topic\n")
    write(tmp_path, "params.json", '[{"ParameterKey": "x", "ParameterValue": "params-secret-do-not-print"}]')
    write(tmp_path, "prod.parameters.json", '{"Parameters": {"x": "other-secret-do-not-print"}}')
    out = stdout_of(tmp_path)
    assert "secret-do-not-print" not in out
    assert {n["file"] for n in json.loads(out)["not_read"]} == {"params.json", "prod.parameters.json"}


def test_a_dynamic_reference_is_not_a_secret(tmp_path: Path) -> None:
    write(
        tmp_path,
        "s.yaml",
        "Resources:\n  D:\n    Type: AWS::RDS::DBInstance\n    Properties:\n"
        "      MasterUserPassword: '{{resolve:secretsmanager:prod/db:SecretString:password}}'\n",
    )
    result = inv(tmp_path, "--checks")
    assert hits_of(result, "password-in-code") == []
    assert by_id(result)["s.yaml:D"]["attributes"]["master_password"].startswith("{{resolve:secretsmanager")


def test_a_password_literal_in_a_template_is_a_hit_and_hidden(tmp_path: Path) -> None:
    write(
        tmp_path,
        "s.yaml",
        "Resources:\n  D:\n    Type: AWS::RDS::DBInstance\n    Properties:\n"
        "      MasterUserPassword: hunter2-do-not-print\n",
    )
    out = stdout_of(tmp_path, "--checks")
    assert "hunter2" not in out
    assert hits_of(json.loads(out), "password-in-code")


# ---------------------------------------------------------------------------- Terraform on AWS


def test_a_policy_from_a_data_document_and_a_jsonencode_are_both_read(tmp_path: Path) -> None:
    write(
        tmp_path,
        "main.tf",
        """
data "aws_iam_policy_document" "open" {
  statement {
    actions   = ["*"]
    resources = ["*"]
  }
}
data "aws_iam_policy_document" "narrow" {
  statement {
    effect    = "Deny"
    actions   = ["*"]
    resources = ["*"]
  }
}
resource "aws_iam_policy" "from_document" {
  name   = "a"
  policy = data.aws_iam_policy_document.open.json
}
resource "aws_iam_policy" "denied" {
  name   = "b"
  policy = data.aws_iam_policy_document.narrow.json
}
resource "aws_iam_policy" "from_json" {
  name   = "c"
  policy = jsonencode({
    Statement = [{ Effect = "Allow", Action = ["s3:*", "*"], Resource = "*" }]
  })
}
resource "aws_iam_policy" "from_heredoc" {
  name   = "d"
  policy = <<EOT
{"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}
EOT
}
""",
    )
    result = inv(tmp_path, "--checks")
    assert {h["resource"] for h in hits_of(result, "iam-action-star")} == {
        "aws_iam_policy.from_document",
        "aws_iam_policy.from_json",
        "aws_iam_policy.from_heredoc",
    }


def test_an_aliased_provider_gives_its_own_region(tmp_path: Path) -> None:
    write(
        tmp_path,
        "main.tf",
        """
provider "aws" {
  region = "eu-west-1"
}
provider "aws" {
  alias  = "eu"
  region = "eu-central-1"
}
resource "aws_sqs_queue" "main" {
  name = "a"
}
resource "aws_sqs_queue" "other" {
  provider = aws.eu
  name     = "b"
}
""",
    )
    rows = by_id(inv(tmp_path))
    assert rows["aws_sqs_queue.main"]["nesting"]["region"] == "eu-west-1"
    assert rows["aws_sqs_queue.other"]["nesting"]["region"] == "eu-central-1"
    assert rows["aws_sqs_queue.other"]["location"] == "eu-central-1"


def test_count_for_each_and_unknown_types_are_reported(tmp_path: Path) -> None:
    write(
        tmp_path,
        "main.tf",
        """
resource "aws_subnet" "many" {
  count = 3
  cidr_block = "10.0.${count.index}.0/24"
}
resource "aws_something_new" "x" {
  name = "x"
}
""",
    )
    kinds = {u["kind"] for u in inv(tmp_path)["unresolved"]}
    assert {"count", "unknown-type"} <= kinds


@pytest.mark.parametrize(
    ("resource", "state", "why"),
    [
        ('resource "aws_lb" "a" {\n  name = "a"\n}\n', "public", "an internet-facing load balancer"),
        ('resource "aws_lb" "a" {\n  name = "a"\n  internal = true\n}\n', "private", "an internal load balancer"),
        ('resource "aws_db_instance" "a" {\n  identifier = "a"\n}\n', "private", "left to the Terraform default"),
        (
            'resource "aws_db_instance" "a" {\n  identifier = "a"\n  publicly_accessible = false\n}\n',
            "private",
            "not publicly",
        ),
    ],
)
def test_exposure_for_common_terraform_cases(tmp_path: Path, resource: str, state: str, why: str) -> None:
    write(tmp_path, "main.tf", resource)
    row = next(iter(by_id(inv(tmp_path)).values()))
    assert row["exposure"]["state"] == state and row["exposure"]["why"].startswith(why)


@pytest.mark.parametrize(
    ("resource", "state", "anonymous"),
    [
        ('resource "aws_apigatewayv2_api" "a" {\n  name = "a"\n  protocol_type = "HTTP"\n}\n', "public", False),
        (
            'resource "aws_api_gateway_rest_api" "a" {\n  name = "a"\n  endpoint_configuration {\n'
            '    types = ["PRIVATE"]\n  }\n}\n',
            "private",
            False,
        ),
        ('resource "aws_lambda_function_url" "a" {\n  authorization_type = "NONE"\n}\n', "public", True),
        ('resource "aws_lambda_function_url" "a" {\n  authorization_type = "AWS_IAM"\n}\n', "restricted", False),
    ],
)
def test_api_gateways_and_function_urls(tmp_path: Path, resource: str, state: str, anonymous: bool) -> None:
    write(tmp_path, "main.tf", resource)
    exposure = next(iter(by_id(inv(tmp_path)).values()))["exposure"]
    assert exposure["state"] == state and exposure["anonymous"] is anonymous


def test_cloudformation_rds_default_depends_on_the_subnet_group(tmp_path: Path) -> None:
    write(
        tmp_path,
        "s.yaml",
        "Resources:\n  G:\n    Type: AWS::RDS::DBSubnetGroup\n    Properties:\n      DBSubnetGroupDescription: d\n"
        "  WithGroup:\n    Type: AWS::RDS::DBInstance\n    Properties:\n      DBSubnetGroupName: !Ref G\n"
        "  NoGroup:\n    Type: AWS::RDS::DBInstance\n    Properties: {}\n",
    )
    rows = by_id(inv(tmp_path))
    assert rows["s.yaml:WithGroup"]["exposure"]["state"] == "private"
    assert rows["s.yaml:NoGroup"]["exposure"]["state"] == "restricted"


def test_a_bucket_with_a_block_off_is_a_hit_and_a_full_block_is_private(tmp_path: Path) -> None:
    write(
        tmp_path,
        "main.tf",
        """
resource "aws_s3_bucket" "partial" {
  bucket = "partial"
}
resource "aws_s3_bucket_public_access_block" "partial" {
  bucket              = aws_s3_bucket.partial.id
  block_public_acls   = true
  block_public_policy = false
}
resource "aws_s3_bucket" "full" {
  bucket = "full"
}
resource "aws_s3_bucket_public_access_block" "full" {
  bucket                  = aws_s3_bucket.full.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket" "public_acl" {
  bucket = "public-acl"
  acl    = "public-read"
}
""",
    )
    result = inv(tmp_path, "--checks")
    hit = {h["resource"] for h in hits_of(result, "s3-no-public-access-block")}
    assert hit == {"aws_s3_bucket.partial", "aws_s3_bucket.public_acl"}
    rows = by_id(result)
    assert rows["aws_s3_bucket.full"]["exposure"]["state"] == "private"
    assert rows["aws_s3_bucket.partial"]["exposure"]["state"] == "restricted"
    assert rows["aws_s3_bucket.public_acl"]["exposure"]["anonymous"] is True


def test_a_block_set_inside_a_cloudformation_bucket_counts(tmp_path: Path) -> None:
    write(
        tmp_path,
        "s.yaml",
        "Resources:\n  B:\n    Type: AWS::S3::Bucket\n    Properties:\n      PublicAccessBlockConfiguration:\n"
        "        BlockPublicAcls: true\n        BlockPublicPolicy: true\n"
        "        IgnorePublicAcls: true\n        RestrictPublicBuckets: true\n",
    )
    result = inv(tmp_path, "--checks")
    assert by_id(result)["s.yaml:B"]["exposure"]["state"] == "private"
    assert hits_of(result, "s3-no-public-access-block") == []


def test_a_waf_association_stops_the_walk(tmp_path: Path) -> None:
    write(
        tmp_path,
        "main.tf",
        """
resource "aws_lb" "a" {
  name = "a"
}
resource "aws_wafv2_web_acl_association" "a" {
  resource_arn = aws_lb.a.arn
  web_acl_arn  = "arn:aws:wafv2:eu-central-1:000000000000:regional/webacl/a/x"
}
""",
    )
    result = inv(tmp_path)
    assert result["exposure"]["stops"][0]["id"] == "aws_lb.a"


def test_egress_and_port_443_rules_are_not_open_rule_hits(tmp_path: Path) -> None:
    write(
        tmp_path,
        "main.tf",
        """
resource "aws_security_group" "web" {
  name = "web"
}
resource "aws_security_group_rule" "egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.web.id
}
resource "aws_security_group_rule" "https" {
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.web.id
}
resource "aws_security_group_rule" "ssh" {
  type              = "ingress"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.web.id
}
""",
    )
    result = inv(tmp_path, "--checks")
    assert {h["resource"] for h in hits_of(result, "sg-open-from-anywhere")} == {"aws_security_group_rule.ssh"}


# ---------------------------------------------------------------------------- exports


def test_a_tagging_export_gives_types_names_and_placement(aws_repo: Path) -> None:
    result: dict[str, Any] = run_json(INVENTORY, "--from-export", str(aws_repo / EXPORT))
    rows = list(result["resources"])
    assert result["providers"] == ["aws"] and len(rows) == 37
    types = {r["name"]: r["type"] for r in rows}
    assert types["stagefront-prod-web"] == "AWS::ElasticLoadBalancingV2::LoadBalancer"
    assert types["stagefront-prod-vpc"] == "AWS::EC2::VPC"  # the name comes from the Name tag
    assert types["stagefront/prod/db"] == "AWS::SecretsManager::Secret"  # the random suffix is dropped
    assert types["stagefront-reports-prod"] == "AWS::S3::Bucket"
    redis = next(r for r in rows if r["name"] == "stagefront-sessions-prod")
    assert redis["nesting"]["account"] == "000000000000" and redis["nesting"]["region"] == "eu-central-1"
    assert result["exposure"]["public"] == []


def test_an_aws_config_export_is_read_in_both_of_its_shapes(tmp_path: Path) -> None:
    write(
        tmp_path,
        "main.tf",
        'provider "aws" {\n  region = "eu-west-1"\n}\nresource "aws_sqs_queue" "q" {\n  name = "a"\n}\n',
    )
    identifiers = {"resourceIdentifiers": [{"resourceType": "AWS::SQS::Queue", "resourceId": "a", "resourceName": "a"}]}
    write(tmp_path, "list.json", json.dumps(identifiers))
    row = {"resourceId": "a", "resourceName": "a", "resourceType": "AWS::SQS::Queue", "awsRegion": "eu-central-1"}
    select = {"Results": [json.dumps(row)]}
    write(tmp_path, "select.json", json.dumps(select))
    for name, difference in (("list.json", False), ("select.json", True)):
        compare = inv(tmp_path, "--compare", str(tmp_path / name))["compare"]
        assert compare["only_in_code"] == [] and compare["only_in_export"] == []
        assert bool(compare["differences"]) is difference


def test_an_arn_no_row_knows_is_kept_as_unknown_type(tmp_path: Path) -> None:
    doc = {"ResourceTagMappingList": [{"ResourceARN": "arn:aws:foo:eu-central-1:000000000000:thing/name", "Tags": []}]}
    write(tmp_path, "export.json", json.dumps(doc))
    result: dict[str, Any] = run_json(INVENTORY, "--from-export", str(tmp_path / "export.json"))
    assert result["resources"][0]["type"] == "foo:thing" and result["resources"][0]["name"] == "name"


# ---------------------------------------------------------------------------- cloud_prices on AWS


def bom_file(tmp: Path, items: list[dict[str, Any]], **extra: Any) -> Path:
    path = tmp / "bom.json"
    path.write_text(json.dumps({"cloud": "aws", "region": "eu-central-1", "currency": "USD", "items": items, **extra}))
    return path


def priced(tmp: Path, table: Path, items: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = run_json(PRICE, str(bom_file(tmp, items, **extra)), "--prices", str(table))
    return result


RDS = {
    "id": "db",
    "label": "Database",
    "service": "AmazonRDS",
    "product": "Database Instance",
    "sku": "db.m6i.2xlarge / PostgreSQL / Multi-AZ / No license required",
    "meter": "Multi-AZUsage:db.m6i.2xl",
    "unit": "Hrs",
    "quantity": 730,
}


def test_an_aws_item_is_priced_with_date_and_source(aws_repo: Path, tmp_path: Path) -> None:
    result = priced(tmp_path, aws_repo / PRICES, [RDS])
    item = result["items"][0]
    assert item["status"] == "priced" and item["monthly"] == pytest.approx(730 * 1.696)
    assert item["as_of"] == "2026-11-10" and "pricing.us-east-1.amazonaws.com" in item["source"]
    assert item["region"] == "eu-central-1" and item["currency"] == "USD"
    assert result["totals"][0]["monthly"] == item["monthly"]


def test_aws_graduated_tiers_work(aws_repo: Path, tmp_path: Path) -> None:
    item = {
        "id": "s3",
        "service": "AmazonS3",
        "product": "Storage",
        "sku": "General Purpose / Standard",
        "meter": "TimedStorage-ByteHrs",
        "unit": "GB-Mo",
        "quantity": 60000,
    }
    result = priced(tmp_path, aws_repo / PRICES, [item])["items"][0]
    assert result["status"] == "priced"
    assert result["monthly"] == pytest.approx(51200 * 0.0245 + 8800 * 0.0235)
    assert [t["from"] for t in result["tiers"]] == [0.0, 51200.0]


def test_a_two_cloud_bill_gets_a_total_for_each_cloud(aws_repo: Path, tmp_path: Path) -> None:
    items = [
        {**RDS, "variant": "aws"},
        {
            "id": "sql",
            "cloud": "azure",
            "region": "westeurope",
            "variant": "azure",
            "service": "SQL Database",
            "product": "SQL Database Single/Elastic Pool General Purpose - Compute Gen5",
            "sku": "8 vCore",
            "meter": "vCore",
            "unit": "1 Hour",
            "quantity": 730,
        },
    ]
    result: dict[str, Any] = run_json(
        PRICE,
        str(bom_file(tmp_path, items)),
        "--prices",
        str(aws_repo / PRICES),
        "--prices",
        str(aws_repo / AZURE_PRICES),
    )
    assert result["not_priced"] == []
    totals = {t["cloud"]: t for t in result["totals"]}
    assert set(totals) == {"aws", "azure"}
    assert totals["aws"]["monthly"] == pytest.approx(730 * 1.696)
    assert totals["azure"]["monthly"] > 0 and totals["azure"]["as_of"] == ["2026-11-10"]
    assert "prices.azure.com" in totals["azure"]["source"][0]


def test_a_row_that_two_options_share_is_not_guessed(tmp_path: Path) -> None:
    table = {
        "cloud": "aws",
        "as_of": "2026-11-10",
        "source": "t",
        "currency": "USD",
        "rows": [
            {
                "service": "S",
                "product": "P",
                "sku": "A",
                "meter": "M",
                "region": "r",
                "unit": "Hrs",
                "unit_price": 1.0,
                "tier_min": 0,
                "effective_from": None,
            },
            {
                "service": "S",
                "product": "P",
                "sku": "A",
                "meter": "M",
                "region": "r",
                "unit": "Hrs",
                "unit_price": 2.0,
                "tier_min": 0,
                "effective_from": None,
            },
        ],
    }
    path = tmp_path / "t.json"
    path.write_text(json.dumps(table))
    item = priced(tmp_path, path, [{"id": "a", "service": "S", "region": "r", "quantity": 1}])["items"][0]
    assert item["status"] == "ambiguous" and "two prices for the same tier" in item["reason"]


OFFER = {
    "formatVersion": "v1.0",
    "offerCode": "AmazonRDS",
    "version": "20260910",
    "products": {
        "SKU1": {
            "sku": "SKU1",
            "productFamily": "Database Instance",
            "attributes": {
                "instanceType": "db.m6i.large",
                "databaseEngine": "PostgreSQL",
                "deploymentOption": "Multi-AZ",
                "licenseModel": "No license required",
                "usagetype": "EUC1-Multi-AZUsage:db.m6i.large",
                "regionCode": "eu-central-1",
            },
        },
        "SKU2": {
            "sku": "SKU2",
            "productFamily": "Database Instance",
            "attributes": {
                "instanceType": "db.m6i.large",
                "databaseEngine": "MySQL",
                "deploymentOption": "Multi-AZ",
                "licenseModel": "No license required",
                "usagetype": "EUC1-Multi-AZUsage:db.m6i.large",
            },
        },
    },
    "terms": {
        "Reserved": {"SKU1": {"SKU1.R": {"priceDimensions": {"a": {"unit": "Hrs", "pricePerUnit": {"USD": "0.1"}}}}}},
        "OnDemand": {
            "SKU1": {
                "SKU1.T": {
                    "effectiveDate": "2026-10-01T00:00:00Z",
                    "priceDimensions": {
                        "SKU1.T.A": {
                            "unit": "Hrs",
                            "beginRange": "0",
                            "endRange": "Inf",
                            "pricePerUnit": {"USD": "0.4240000000"},
                        }
                    },
                }
            },
            "SKU2": {"SKU2.T": {"priceDimensions": {"SKU2.T.A": {"unit": "Hrs", "pricePerUnit": {"USD": "0.9"}}}}},
        },
    },
}


def offer_item(**extra: Any) -> dict[str, Any]:
    return {
        "id": "db",
        "cloud": "aws",
        "region": "eu-central-1",
        "service": "AmazonRDS",
        "product": "Database Instance",
        "sku": "db.m6i.large / PostgreSQL / Multi-AZ / No license required",
        "meter": "Multi-AZUsage:db.m6i.large",
        "unit": "Hrs",
        "quantity": 730,
        **extra,
    }


@pytest.fixture
def module() -> Any:
    return load(PRICE)


def test_online_reads_a_price_file_through_a_temporary_download(
    module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_download(url: str, dest: Path, timeout: float, max_bytes: int, max_seconds: float) -> int:
        calls.append(url)
        assert timeout == 7.0 and max_bytes == 32 * 1_000_000 and max_seconds == 30.0
        dest.write_text(json.dumps(OFFER))
        return dest.stat().st_size

    monkeypatch.setattr(module, "download_file", fake_download)
    bom = {"cloud": "aws", "region": "eu-central-1", "currency": "USD", "items": [offer_item(), offer_item(id="db2")]}
    result = module.run(bom, None, True, 7.0, 32, 30.0)
    assert len(calls) == 1  # both items share one file and one region
    assert calls[0] == (
        "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRDS/current/eu-central-1/index.json"
    )
    item = result["items"][0]
    assert item["status"] == "priced" and item["monthly"] == pytest.approx(730 * 0.424)
    assert item["effective_from"] == "2026-10-01" and result["as_of"] == item["as_of"]


def test_a_file_over_the_limit_is_reported_with_the_way_out(
    module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def too_big(url: str, dest: Path, timeout: float, max_bytes: int, max_seconds: float) -> int:
        raise module.PriceFileTooLarge("434 MB, over the limit of 64 MB")

    monkeypatch.setattr(module, "download_file", too_big)
    result = module.run({"region": "eu-central-1", "items": [offer_item()]}, None, True, 5.0)
    item = result["items"][0]
    assert item["status"] == "too_large" and item["monthly"] is None
    assert "--prices" in item["reason"] and "--max-file-mb" in item["reason"]
    assert result["not_priced"] == ["db"] and result["errors"]


def test_a_slow_file_is_reported(module: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def too_slow(url: str, dest: Path, timeout: float, max_bytes: int, max_seconds: float) -> int:
        raise module.PriceFileTooSlow("not finished after 120 seconds")

    monkeypatch.setattr(module, "download_file", too_slow)
    item = module.run({"region": "eu-central-1", "items": [offer_item()]}, None, True, 5.0)["items"][0]
    assert item["status"] == "too_slow" and "--prices" in item["reason"]


def test_a_missing_file_says_to_check_the_code(module: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def gone(url: str, dest: Path, timeout: float, max_bytes: int, max_seconds: float) -> int:
        raise HTTPError(url, 404, "not found", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(module, "download_file", gone)
    item = module.run({"region": "eu-central-1", "items": [offer_item()]}, None, True, 5.0)["items"][0]
    assert item["status"] == "not_found" and "offers/v1.0/aws/index.json" in item["reason"]


def test_a_download_is_cut_off_at_the_ceiling(module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        headers: ClassVar[dict[str, str]] = {}
        chunks: ClassVar[list[bytes]] = [b"x" * 40, b"x" * 40, b"x" * 40]

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            return self.chunks.pop() if self.chunks else b""

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: Response())
    with pytest.raises(module.PriceFileTooLarge):
        module.download_file("https://example.com/f", tmp_path / "f", 5.0, 100, 60.0)


def test_a_declared_size_over_the_ceiling_stops_before_reading(
    module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Response:
        headers: ClassVar[dict[str, str]] = {"Content-Length": "500"}

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            raise AssertionError("must not read a file already known to be too big")

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda *a, **k: Response())
    with pytest.raises(module.PriceFileTooLarge):
        module.download_file("https://example.com/f", tmp_path / "f", 5.0, 100, 60.0)


def test_a_price_file_is_read_as_a_stream_across_chunk_boundaries(module: Any, tmp_path: Path) -> None:
    spec = json.loads(AWS_FILE.read_text(encoding="utf-8"))["prices"]
    many = {f"F{i}": dict(OFFER["products"]["SKU1"], sku=f"F{i}") for i in range(30000)}
    many["SKU1"] = OFFER["products"]["SKU1"]
    doc = dict(OFFER, products=many)
    path = tmp_path / "offer.json"
    path.write_text(json.dumps(doc, indent=2))
    assert path.stat().st_size > 3 * module.JsonStream.CHUNK
    rows = module.read_bulk_file(path, "AmazonRDS", "eu-central-1", [offer_item()], spec, "USD")
    # Only SKU1 has a term and matches this sku; the 30000 filler products have no price and SKU2 another engine.
    assert [r["unit_price"] for r in rows] == [0.424]
    assert rows[0]["meter"] == "Multi-AZUsage:db.m6i.large" and rows[0]["tier_min"] == 0.0


def test_online_for_a_query_provider_still_works(module: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(url: str, timeout: float) -> dict[str, Any]:
        return {"Items": [], "NextPageLink": None}

    monkeypatch.setattr(module, "_fetch_json", fake)
    item = {"id": "a", "cloud": "azure", "service": "Azure App Service", "quantity": 1}
    assert module.run({"region": "westeurope", "items": [item]}, None, True, 5.0)["items"][0]["status"] == "not_found"


def test_the_price_table_prices_the_design_items_a_page_needs(aws_repo: Path, tmp_path: Path) -> None:
    """Every row aws.md tells a bill to use exists in the saved table with the same values."""
    items = [
        {"id": "cpu", "service": "AmazonECS", "meter": "Fargate-vCPU-Hours:perCPU", "unit": "hours", "quantity": 730},
        {"id": "mem", "service": "AmazonECS", "meter": "Fargate-GB-Hours", "unit": "hours", "quantity": 730},
        {
            "id": "alb",
            "service": "AWSELB",
            "product": "Load Balancer-Application",
            "meter": "LoadBalancerUsage",
            "unit": "Hrs",
            "quantity": 730,
        },
        {
            "id": "lcu",
            "service": "AWSELB",
            "product": "Load Balancer-Application",
            "meter": "LCUUsage",
            "unit": "LCU-Hrs",
            "quantity": 730,
        },
        {
            "id": "nat",
            "service": "AmazonEC2",
            "product": "NAT Gateway",
            "meter": "NatGateway-Hours",
            "unit": "Hrs",
            "quantity": 1460,
        },
        {
            "id": "natgb",
            "service": "AmazonEC2",
            "product": "NAT Gateway",
            "meter": "NatGateway-Bytes",
            "unit": "GB",
            "quantity": 100,
        },
        {
            "id": "store",
            "service": "AmazonRDS",
            "product": "Database Storage",
            "sku": "General Purpose-GP3 / PostgreSQL / Multi-AZ",
            "meter": "RDS:Multi-AZ-GP3-Storage",
            "unit": "GB-Mo",
            "quantity": 400,
        },
        {
            "id": "s3",
            "service": "AmazonS3",
            "product": "Storage",
            "sku": "General Purpose / Standard",
            "meter": "TimedStorage-ByteHrs",
            "unit": "GB-Mo",
            "quantity": 500,
        },
        {
            "id": "sqs",
            "service": "AWSQueueService",
            "sku": "Standard / SQS-APIRequest-Tier1",
            "meter": "Requests-Tier1",
            "unit": "Requests",
            "quantity": 10000000,
        },
        {
            "id": "sec",
            "service": "AWSSecretsManager",
            "product": "Secret",
            "meter": "AWSSecretsManager-Secrets",
            "unit": "Secrets",
            "quantity": 5,
        },
        {
            "id": "ep",
            "service": "AmazonVPC",
            "product": "VpcEndpoint",
            "sku": "PrivateLink / VPCE:VpcEndpoint",
            "meter": "VpcEndpoint-Hours",
            "unit": "Hrs",
            "quantity": 4380,
        },
        {
            "id": "log",
            "service": "AmazonCloudWatch",
            "product": "Data Payload",
            "sku": "Ingested Logs",
            "meter": "DataProcessing-Bytes",
            "unit": "GB",
            "quantity": 100,
        },
        {
            "id": "waf",
            "service": "awswaf",
            "product": "Web Application Firewall",
            "sku": "Web ACL",
            "meter": "WebACL",
            "unit": "month",
            "quantity": 1,
        },
        {
            "id": "out",
            "service": "AWSDataTransfer",
            "sku": "AWS Outbound / EU (Frankfurt) / External",
            "meter": "DataTransfer-Out-Bytes",
            "unit": "GB",
            "quantity": 500,
        },
    ]
    result = priced(tmp_path, aws_repo / PRICES, items)
    assert result["not_priced"] == [], [i for i in result["items"] if i["status"] != "priced"]
    for row in result["items"]:
        assert row["monthly"] > 0
