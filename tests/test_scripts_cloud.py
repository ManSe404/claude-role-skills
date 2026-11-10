"""The cloud-architect scripts, on the acme-cloud fixture and on small cases of their own."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest
from conftest import ROOT, load, run_json
from test_fixture_acme_cloud import (
    ONLY_IN_CODE,
    ONLY_IN_EXPORT,
    PLANTED_AT,
    PRICES,
    PUBLIC,
    RESOURCES,
    SECRET,
    ZERO_GUID,
)

INVENTORY = ROOT / "shared" / "cloud_inventory.py"
PRICE = ROOT / "shared" / "cloud_prices.py"
RULES = ROOT / "plugins" / "cloud-architect" / "skills" / "cloud-design" / "scripts" / "cloud_rules.py"
EXPORT = "exports/az-resource-list-2026-11-08.json"

CHECK_FOR_PLANTED = {
    1: "database-open-to-internet",
    2: "storage-public-blobs",
    3: "secret-in-settings",
    4: "no-diagnostics",
    5: "single-zone-database",
    6: "nsg-open-from-anywhere",
    7: "no-managed-identity",
    8: "unpinned-image",
}


def inv(path: Path, *args: str) -> dict[str, Any]:
    result: dict[str, Any] = run_json(INVENTORY, str(path), *args)
    return result


def by_id(result: dict[str, Any]) -> dict[str, Any]:
    return {r["id"]: r for r in result["resources"]}


@pytest.fixture(scope="module")
def full(cloud_repo: Path) -> dict[str, Any]:
    return inv(cloud_repo, "--checks", "--compare", str(cloud_repo / EXPORT))


# ---------------------------------------------------------------------------- cloud_inventory on the fixture


def test_every_format_is_read_and_counted(full: dict[str, Any]) -> None:
    assert full["summary"]["resources"] == RESOURCES and full["providers"] == ["azure"]
    assert "infra/terraform/app.tf" in full["read"]["terraform"]
    assert "infra/bicep/modules/reports.bicep" in full["read"]["bicep"]
    assert full["read"]["arm"] == ["infra/arm/alerts.json"]
    assert full["summary"]["by_category"]["compute"] == 6
    assert full["summary"]["helpers_skipped"] == 1


def test_a_resource_has_the_normalised_shape(full: dict[str, Any]) -> None:
    server = by_id(full)["azurerm_mssql_server.main"]
    assert server["type"] == "Microsoft.Sql/servers" and server["category"] == "database"
    assert server["name"] == "sql-acme-tickets-prod" and server["location"] == "westeurope"
    assert server["file"] == "infra/terraform/data.tf" and server["line"] == 1


@pytest.mark.parametrize(
    ("rid", "subscription", "group", "vnet", "subnet"),
    [
        ("azurerm_linux_web_app.portal", ZERO_GUID, "rg-acme-tickets-prod-app", "vnet-acme-tickets-prod", "snet-app"),
        ("azurerm_subnet.data", ZERO_GUID, "rg-acme-tickets-prod-network", "vnet-acme-tickets-prod", None),
        (
            "azurerm_private_endpoint.vault",
            ZERO_GUID,
            "rg-acme-tickets-prod-network",
            "vnet-acme-tickets-prod",
            "snet-data",
        ),
        (
            "module.worker.azurerm_container_app.worker",
            ZERO_GUID,
            "rg-acme-tickets-prod-app",
            "vnet-acme-tickets-prod",
            "snet-jobs",
        ),
        ("infra/bicep/main.bicep:reports.reportsStorage", None, "rg-acme-reports-prod", None, None),
        ("infra/bicep/main.bicep:reportsRg", None, None, None, None),
        ("azurerm_network_security_group.jobs/allow-ssh-admin", ZERO_GUID, "rg-acme-tickets-prod-network", None, None),
    ],
)
def test_nesting_is_followed_to_the_top(
    full: dict[str, Any], rid: str, subscription: str | None, group: str | None, vnet: str | None, subnet: str | None
) -> None:
    nesting = by_id(full)[rid]["nesting"]
    assert (nesting["subscription"], nesting["resource_group"], nesting["vnet"], nesting["subnet"]) == (
        subscription,
        group,
        vnet,
        subnet,
    )


def test_modules_are_read_with_their_inputs_and_get_a_prefix(full: dict[str, Any]) -> None:
    worker = by_id(full)["module.worker.azurerm_container_app.worker"]
    assert worker["name"] == "ca-acme-tickets-prod-worker"
    assert worker["attributes"]["images"] == "acrticketsprod.azurecr.io/tickets-worker:1.8.2"
    assert worker["parent"] == "azurerm_container_app_environment.jobs"
    assert worker["module"] == "module.worker"


def test_bicep_parent_and_nested_properties_are_read(full: dict[str, Any]) -> None:
    rows = by_id(full)
    prefix = "infra/bicep/main.bicep:reports."
    container = rows[f"{prefix}exportsContainer"]
    assert container["parent"] == f"{prefix}blobServices" and container["attributes"]["public_access"] == "Blob"
    assert rows[f"{prefix}blobServices"]["parent"] == f"{prefix}reportsStorage"
    api = rows[f"{prefix}reportsApi"]
    assert api["attributes"]["external_ingress"] is True and api["parent"] == f"{prefix}reportsEnv"
    assert api["attributes"]["images"] == "acrticketsprod.azurecr.io/reports-api:latest"


def test_inline_blocks_become_resources_with_their_own_lines(full: dict[str, Any]) -> None:
    rule = by_id(full)["azurerm_network_security_group.jobs/allow-ssh-admin"]
    assert rule["type"] == "Microsoft.Network/networkSecurityGroups/securityRules" and rule["parent"]
    assert rule["attributes"]["source"] == "*" and rule["file"] == "infra/terraform/network.tf"


def test_arm_is_read_with_expressions_and_data_sources_stay_separate(full: dict[str, Any]) -> None:
    rows = by_id(full)
    assert rows["infra/arm/alerts.json:actionGroups/ag-acme-tickets-prod"]["name"] == "ag-acme-tickets-prod"
    zone = rows["data.azurerm_dns_zone.public"]
    assert zone["mode"] == "data" and zone["nesting"]["resource_group"] == "rg-acme-shared-dns"


def test_references_carry_how_they_were_made(full: dict[str, Any]) -> None:
    refs = {(r["to"], r["kind"]) for r in by_id(full)["azurerm_linux_web_app.portal"]["references"]}
    assert ("azurerm_mssql_server.main", "uses") in refs
    assert ("azurerm_subnet.app", "placement") in refs
    assert ("azurerm_resource_group.app", "placement") in refs


def test_what_could_not_be_read_is_reported_not_guessed(full: dict[str, Any]) -> None:
    kinds = {(u["kind"], u["resource"]) for u in full["unresolved"]}
    assert ("for_each", "azurerm_servicebus_queue.queues") in kinds
    assert ("dynamic-name", "azurerm_storage_account.tickets") in kinds
    assert ("unknown-type", "azurerm_dns_cname_record.portal") in kinds
    queues = by_id(full)["azurerm_servicebus_queue.queues"]
    assert queues["repeated"] == "for_each" and queues["name"] is None
    assert by_id(full)["azurerm_storage_account.tickets"]["name_unknown"] == "random_string.suffix.result"


def test_public_exposure_is_computed_with_a_reason(full: dict[str, Any]) -> None:
    exposure = full["exposure"]
    assert {r["id"] for r in exposure["public"]} == PUBLIC
    reasons = {r["id"]: r for r in exposure["public"]}
    assert reasons["azurerm_mssql_server.main"]["why"] == "a firewall rule opens every address"
    assert reasons["infra/bicep/main.bicep:reports.reportsStorage"]["anonymous"] is True
    assert {r["id"] for r in exposure["private"]} >= {
        "azurerm_key_vault.main",
        "azurerm_storage_account.tickets",
        "azurerm_storage_account.backups",
        "module.worker.azurerm_container_app.worker",
    }


def test_reach_stops_at_private_boundaries(full: dict[str, Any]) -> None:
    exposure = full["exposure"]
    stops = {s["id"] for s in exposure["stops"]}
    assert "azurerm_key_vault.main" in stops
    reach = {r["to"]: r for r in exposure["reach"]}
    vault = reach["azurerm_key_vault.main"]
    assert vault["path"] == ["internet", "azurerm_linux_web_app.portal", "azurerm_key_vault.main"]
    assert vault["behind_stop"] is True and vault["direct"] is False
    assert reach["azurerm_mssql_server.main"]["path"] == ["internet", "azurerm_mssql_server.main"]


def test_the_open_nsg_rule_is_reported_with_where_it_applies(full: dict[str, Any]) -> None:
    rules = full["exposure"]["permissive_rules"]
    assert [r["name"] for r in rules] == ["allow-ssh-admin"]
    assert rules[0]["port"] == "22" and "azurerm_subnet.jobs" in rules[0]["attached_to"]


@pytest.mark.parametrize("number", sorted(PLANTED_AT), ids=[f"planted-{n}" for n in sorted(PLANTED_AT)])
def test_every_planted_problem_has_a_hit_at_its_line(full: dict[str, Any], number: int) -> None:
    file, _, line = PLANTED_AT[number].rpartition(":")
    hits = [h for family in full["checks"].values() for h in family if h["check"] == CHECK_FOR_PLANTED[number]]
    assert (file, int(line)) in {(h["file"], h["line"]) for h in hits}


def test_clean_resources_have_no_such_hits(full: dict[str, Any]) -> None:
    hits = [h for family in full["checks"].values() for h in family]
    flagged = {(h["check"], h["resource"]) for h in hits}
    assert ("no-diagnostics", "azurerm_linux_web_app.portal") not in flagged
    assert ("no-managed-identity", "module.worker.azurerm_container_app.worker") not in flagged
    assert ("unpinned-image", "module.worker.azurerm_container_app.worker") not in flagged


def test_drift_finds_the_one_only_in_code_and_the_one_only_in_export(full: dict[str, Any]) -> None:
    compare = full["compare"]
    assert [r["id"] for r in compare["only_in_code"]] == [ONLY_IN_CODE[0]]
    assert [(r["type"], r["name"]) for r in compare["only_in_export"]] == [ONLY_IN_EXPORT]
    assert compare["not_comparable"] == [
        {
            "id": "azurerm_storage_account.tickets",
            "type": "Microsoft.Storage/storageAccounts",
            "why": "the name is not known from the code: random_string.suffix.result",
            "candidates": ["stacmeticketsqx7k2p"],
        }
    ]
    assert {i["name"] for i in compare["ignored"]} >= {"sql-acme-tickets-prod/master"}
    assert any(r["name"] == "sql-acme-tickets-prod" for r in compare["in_both"])


def test_no_secret_value_reaches_stdout_on_the_fixture(cloud_repo: Path) -> None:
    for args in ([], ["--checks"], ["--compare", str(cloud_repo / EXPORT)]):
        out = subprocess.run(
            [sys.executable, str(INVENTORY), str(cloud_repo), *args], capture_output=True, text=True, check=True
        ).stdout
        assert SECRET not in out
        assert "<hidden: looks like a secret>" in out


# ---------------------------------------------------------------------------- cloud_inventory on small cases


def write(tmp: Path, name: str, text: str) -> None:
    path = tmp / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def stdout_of(tmp: Path, *args: str) -> str:
    return subprocess.run(
        [sys.executable, str(INVENTORY), str(tmp), *args], capture_output=True, text=True, check=True
    ).stdout


def test_hcl_comments_heredocs_ternaries_and_nested_quotes(tmp_path: Path) -> None:
    write(
        tmp_path,
        "main.tf",
        """
# a comment
/* another
   comment */
variable "env" { default = "prod" }
locals { name = var.env == "prod" ? "live" : "test" }
resource "azurerm_resource_group" "a" {
  name     = "rg-${local.name}-${upper("x")}" // trailing comment
  location = "westeurope"
  tags     = { note = <<EOT
some ${var.env} text
EOT
  }
}
""",
    )
    result = inv(tmp_path)
    assert by_id(result)["azurerm_resource_group.a"]["name"] == "rg-live-X"
    assert result["unresolved"] == []


def test_count_for_each_and_unknown_variables_are_reported(tmp_path: Path) -> None:
    write(
        tmp_path,
        "main.tf",
        """
variable "region" {}
resource "azurerm_subnet" "many" {
  count = 3
  name  = "s-${count.index}"
}
resource "azurerm_storage_account" "s" {
  name     = "acct${var.region}"
  location = var.region
}
""",
    )
    result = inv(tmp_path)
    kinds = {u["kind"] for u in result["unresolved"]}
    assert {"count", "dynamic-name"} <= kinds
    assert by_id(result)["azurerm_storage_account.s"]["location"] == "<unknown: var.region>"
    assert by_id(result)["azurerm_subnet.many"]["name"] is None


def test_a_remote_module_is_reported_and_a_local_one_followed(tmp_path: Path) -> None:
    write(
        tmp_path,
        "main.tf",
        """
module "net" {
  source  = "hashicorp/network/azurerm"
  version = "1.0.0"
}
module "local" {
  source = "./mods/one"
  label  = "alpha"
}
""",
    )
    write(
        tmp_path,
        "mods/one/main.tf",
        """
variable "label" {}
resource "azurerm_resource_group" "x" {
  name = "rg-${var.label}"
}
""",
    )
    result = inv(tmp_path)
    assert [u["resource"] for u in result["unresolved"] if u["kind"] == "remote-module"] == ["module.net"]
    assert by_id(result)["module.local.azurerm_resource_group.x"]["name"] == "rg-alpha"
    assert result["read"]["terraform"].count("mods/one/main.tf") == 1


def test_values_files_are_never_opened(tmp_path: Path) -> None:
    write(tmp_path, "main.tf", 'resource "azurerm_resource_group" "x" {\n  name = "rg"\n}\n')
    write(tmp_path, "prod.tfvars", 'admin = "tfvars-secret-do-not-print"\n')
    write(tmp_path, "terraform.tfstate", '{"secret": "state-secret-do-not-print"}\n')
    write(tmp_path, "main.bicepparam", "param admin = 'bicep-secret-do-not-print'\n")
    out = stdout_of(tmp_path)
    assert "secret-do-not-print" not in out
    result = json.loads(out)
    assert {n["file"] for n in result["not_read"]} == {"prod.tfvars", "terraform.tfstate", "main.bicepparam"}


def test_the_terraform_cache_is_skipped(tmp_path: Path) -> None:
    write(tmp_path, ".terraform/modules/x/main.tf", 'resource "azurerm_resource_group" "x" { name = "rg" }\n')
    assert inv(tmp_path)["resources"] == []


@pytest.mark.parametrize(
    "line",
    [
        'admin_password = "hunter2-do-not-print"',
        'connection_string = "Server=tcp:x;User=a;Password=hunter2-do-not-print;"',
        'app_settings = { DB = "Server=tcp:x;Password=hunter2-do-not-print" }',
        'custom = "x;AccountKey=hunter2-do-not-print;y"',
        'app_settings = { FOO = "eyJhbGciOiJIUzI1Ni.eyJzdWIiOiIxMjM0.hunter2donotprint" }',
    ],
)
def test_a_secret_in_terraform_never_reaches_stdout(tmp_path: Path, line: str) -> None:
    write(tmp_path, "main.tf", f'resource "azurerm_linux_web_app" "x" {{\n  name = "a"\n  {line}\n}}\n')
    out = stdout_of(tmp_path, "--checks")
    assert "hunter2" not in out


def test_a_secret_through_a_variable_default_never_reaches_stdout(tmp_path: Path) -> None:
    write(
        tmp_path,
        "main.tf",
        """
variable "smtp_password" { default = "hunter2-default-do-not-print" }
variable "sneaky" {
  sensitive = true
  default   = "hunter3-default-do-not-print"
}
resource "azurerm_linux_web_app" "x" {
  name = "a"
  app_settings = {
    A = var.smtp_password
    B = var.sneaky
    C = "ok-${var.sneaky}"
  }
}
""",
    )
    out = stdout_of(tmp_path, "--checks")
    assert "hunter" not in out
    settings = json.loads(out)["resources"][0]["attributes"]["settings"]
    assert settings["A"] == "<unknown: var.smtp_password>"


def test_a_secret_in_bicep_and_arm_never_reaches_stdout(tmp_path: Path) -> None:
    write(
        tmp_path,
        "main.bicep",
        """
param sqlPassword string = 'hunter2-bicep-do-not-print'
resource app 'Microsoft.Web/sites@2023-01-01' = {
  name: 'a'
  properties: {
    siteConfig: {
      appSettings: [
        { name: 'DB_PASSWORD', value: 'hunter2-inline-do-not-print' }
        { name: 'KV_REF', value: '@Microsoft.KeyVault(SecretUri=https://kv.example.com/x)' }
      ]
    }
  }
}
""",
    )
    write(
        tmp_path,
        "t.json",
        json.dumps(
            {
                "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
                "parameters": {"adminPassword": {"type": "string", "defaultValue": "hunter2-arm-do-not-print"}},
                "resources": [
                    {
                        "type": "Microsoft.Compute/virtualMachines",
                        "name": "vm",
                        "properties": {"osProfile": {"adminPassword": "[parameters('adminPassword')]"}},
                    }
                ],
            }
        ),
    )
    out = stdout_of(tmp_path, "--checks")
    assert "hunter2" not in out
    result = json.loads(out)
    settings = by_id(result)["main.bicep:app"]["attributes"]["settings"]
    assert settings["DB_PASSWORD"] == "<hidden: looks like a secret>"
    assert settings["KV_REF"].startswith("@Microsoft.KeyVault")


def test_bicep_scope_modules_loops_conditions_and_existing(tmp_path: Path) -> None:
    write(
        tmp_path,
        "main.bicep",
        """
targetScope = 'subscription'
param region string = 'westeurope'
resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-x'
  location: region
}
module part 'part.bicep' = {
  name: 'part'
  scope: rg
  params: {
    name: 'vault-x'
  }
}
module registry 'br:example.azurecr.io/x:1' = {
  name: 'reg'
  scope: rg
}
""",
    )
    write(
        tmp_path,
        "part.bicep",
        """
param name string
param names array = ['a', 'b']
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: resourceGroup().location
  properties: {
    publicNetworkAccess: 'Disabled'
  }
}
resource many 'Microsoft.Storage/storageAccounts@2023-05-01' = [for n in names: {
  name: 'st${n}'
}]
resource maybe 'Microsoft.Cache/Redis@2024-03-01' = if (name == 'x') {
  name: 'redis'
}
resource old 'Microsoft.Network/virtualNetworks@2023-11-01' existing = {
  name: 'vnet-old'
}
""",
    )
    result = inv(tmp_path)
    rows = by_id(result)
    kv = rows["main.bicep:part.kv"]
    assert kv["name"] == "vault-x" and kv["location"] == "westeurope"
    assert kv["attributes"]["public_network_access"] is False
    assert kv["nesting"]["resource_group"] == "rg-x"
    assert rows["main.bicep:part.many"]["repeated"] == "loop"
    assert rows["main.bicep:part.maybe"]["conditional"] is True
    assert rows["main.bicep:part.old"]["mode"] == "data"
    kinds = {(u["kind"], u["resource"]) for u in result["unresolved"]}
    assert ("loop", "main.bicep:part.many") in kinds
    assert ("conditional", "main.bicep:part.maybe") in kinds
    assert ("remote-module", "main.bicep:registry") in kinds


def test_bicep_nested_child_resources_and_inline_subnets(tmp_path: Path) -> None:
    write(
        tmp_path,
        "main.bicep",
        """
resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: 'vnet-x'
  location: 'westeurope'
  properties: {
    subnets: [
      {
        name: 'a'
        properties: {
          addressPrefix: '10.0.0.0/24'
        }
      }
    ]
  }
  resource b 'subnets' = {
    name: 'b'
  }
}
""",
    )
    rows = by_id(inv(tmp_path))
    assert "main.bicep:vnet/a" in rows and rows["main.bicep:vnet/a"]["type"].endswith("/subnets")
    assert rows["main.bicep:b"]["parent"] == "main.bicep:vnet"
    assert rows["main.bicep:b"]["type"] == "Microsoft.Network/virtualNetworks/subnets"
    assert rows["main.bicep:vnet/a"]["nesting"]["vnet"] is None or rows["main.bicep:vnet/a"]["parent"]


def test_arm_expressions_and_compiled_bicep(tmp_path: Path) -> None:
    template = {
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "parameters": {"site": {"type": "string", "defaultValue": "web1"}},
        "variables": {"plan": "[concat('plan-', parameters('site'))]"},
        "resources": [
            {"type": "Microsoft.Web/serverfarms", "name": "[variables('plan')]", "location": "westeurope"},
            {
                "type": "Microsoft.Web/sites",
                "name": "[parameters('site')]",
                "location": "westeurope",
                "properties": {"serverFarmId": "[resourceId('Microsoft.Web/serverfarms', variables('plan'))]"},
            },
            {"type": "Microsoft.Sql/servers", "name": "[uniqueString(resourceGroup().id)]"},
        ],
    }
    write(tmp_path, "site.json", json.dumps(template, indent=2))
    compiled = dict(template)
    compiled["metadata"] = {"_generator": {"name": "bicep", "version": "0.30"}}
    write(tmp_path, "compiled.json", json.dumps(compiled, indent=2))
    write(
        tmp_path,
        "site.parameters.json",
        '{"$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#"}',
    )
    result = inv(tmp_path)
    rows = by_id(result)
    assert rows["site.json:serverfarms/plan-web1"]["name"] == "plan-web1"
    site = rows["site.json:sites/web1"]
    assert site["references"] == [
        {
            "to": "site.json:serverfarms/plan-web1",
            "via": "properties.serverFarmId",
            "line": site["references"][0]["line"],
            "kind": "uses",
        }
    ]
    assert site["line"] > 0
    assert "compiled.json" in {n["file"] for n in result["not_read"]}
    assert result["read"]["arm"] == ["site.json"]
    assert any(u["kind"] == "dynamic-name" for u in result["unresolved"])


def test_a_broken_file_is_reported_and_the_rest_still_read(tmp_path: Path) -> None:
    write(tmp_path, "a.tf", 'resource "azurerm_resource_group" "ok" { name = "good" }\n')
    write(tmp_path, "b.tf", "resource = = {\n")
    result = inv(tmp_path)
    assert by_id(result)["azurerm_resource_group.ok"]["name"] == "good"
    assert any(u["kind"] == "parse-error" and u["file"] == "b.tf" for u in result["unresolved"])


@pytest.mark.parametrize(
    ("image", "hit"),
    [
        ("example.azurecr.io/app:latest", True),
        ("example.azurecr.io/app", True),
        ("example.azurecr.io/app:1.2.3", False),
        ("example.azurecr.io/app@sha256:abc123", False),
        ("DOTNETCORE|8.0", False),
    ],
)
def test_an_unpinned_image_is_a_hit(tmp_path: Path, image: str, hit: bool) -> None:
    write(
        tmp_path,
        "main.bicep",
        f"""
resource app 'Microsoft.Web/sites@2023-01-01' = {{
  name: 'a'
  properties: {{
    siteConfig: {{
      linuxFxVersion: '{image}'
    }}
  }}
}}
""",
    )
    hits = [
        h for family in inv(tmp_path, "--checks")["checks"].values() for h in family if h["check"] == "unpinned-image"
    ]
    assert bool(hits) is hit


def test_a_compare_reads_resource_graph_shapes_too(tmp_path: Path) -> None:
    write(tmp_path, "main.tf", 'resource "azurerm_key_vault" "v" {\n  name = "kv-a"\n  location = "westeurope"\n}\n')
    row = {
        "id": "/subscriptions/x/resourceGroups/r/providers/Microsoft.KeyVault/vaults/kv-a",
        "name": "kv-a",
        "type": "microsoft.keyvault/vaults",
        "resourceGroup": "r",
        "location": "northeurope",
        "properties": {"secret": "export-secret-do-not-print"},
    }
    write(tmp_path, "list.json", json.dumps({"count": 1, "data": [row]}))
    table = {"data": {"columns": [{"name": k} for k in row], "rows": [list(row.values())]}}
    write(tmp_path, "table.json", json.dumps(table))
    for name in ("list.json", "table.json"):
        out = stdout_of(tmp_path, "--compare", str(tmp_path / name))
        assert "export-secret-do-not-print" not in out
        compare = json.loads(out)["compare"]
        assert compare["only_in_code"] == [] and compare["only_in_export"] == []
        assert compare["differences"] == [
            {"id": "azurerm_key_vault.v", "field": "location", "code": "westeurope", "export": "northeurope"}
        ]


def test_inventory_can_start_from_an_export_alone(cloud_repo: Path) -> None:
    result: dict[str, Any] = run_json(INVENTORY, "--from-export", str(cloud_repo / EXPORT))
    rows = by_id(result)
    assert len(rows) == 26
    redis = next(r for r in rows.values() if r["name"] == "redis-acme-sessions-prod")
    assert redis["category"] == "database" and redis["nesting"]["resource_group"] == "rg-acme-tickets-prod-data"
    assert result["exposure"]["public"] == []


def test_a_missing_folder_is_refused() -> None:
    done = subprocess.run([sys.executable, str(INVENTORY), "/does/not/exist"], capture_output=True, text=True)
    assert done.returncode == 2


# ---------------------------------------------------------------------------- cloud_prices


def bom_file(tmp: Path, items: list[dict[str, Any]], **extra: Any) -> Path:
    path = tmp / "bom.json"
    path.write_text(json.dumps({"cloud": "azure", "region": "westeurope", "currency": "USD", "items": items, **extra}))
    return path


def priced(tmp: Path, table: Path, items: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = run_json(PRICE, str(bom_file(tmp, items, **extra)), "--prices", str(table))
    return result


APP_P1 = {
    "id": "app",
    "label": "App plan",
    "service": "Azure App Service",
    "product": "Azure App Service Premium v3 Plan - Linux",
    "sku": "P1 v3",
    "unit": "1 Hour",
    "quantity": 730,
}


def test_an_item_is_priced_with_date_and_source(cloud_repo: Path, tmp_path: Path) -> None:
    result = priced(tmp_path, cloud_repo / PRICES, [APP_P1])
    item = result["items"][0]
    assert item["status"] == "priced" and item["monthly"] == 129.94  # 0.178 USD an hour, 730 hours
    assert item["unit_price"] == 0.178 and item["unit"] == "1 Hour"
    assert item["as_of"] == "2026-11-10" and "prices.azure.com" in item["source"]
    assert result["totals"] == [
        {
            "cloud": "azure",
            "variant": "",
            "monthly": 129.94,
            "currency": "USD",
            "currencies": [],
            "items_priced": 1,
            "items_not_priced": 0,
            "as_of": ["2026-11-10"],
            "source": [item["source"]],
        }
    ]


def test_tiers_are_graduated(cloud_repo: Path, tmp_path: Path) -> None:
    items = [
        {
            "id": "ops",
            "service": "Service Bus",
            "sku": "Standard",
            "meter": "Standard Messaging Operations",
            "quantity": 200,
        }
    ]
    item = priced(tmp_path, cloud_repo / PRICES, items)["items"][0]
    assert item["monthly"] == pytest.approx(13 * 0.0 + 87 * 0.8 + 100 * 0.5)
    assert [t["from"] for t in item["tiers"]] == [0.0, 13.0, 100.0]


def test_an_ambiguous_item_is_not_guessed(cloud_repo: Path, tmp_path: Path) -> None:
    items = [{"id": "base", "service": "Service Bus", "sku": "Standard", "meter": "Standard Base Unit", "quantity": 1}]
    result = priced(tmp_path, cloud_repo / PRICES, items)
    item = result["items"][0]
    assert item["status"] == "ambiguous" and item["monthly"] is None
    assert {c["unit"] for c in item["candidates"]} == {"1/Hour", "1/Month"}
    assert result["not_priced"] == ["base"]
    assert result["totals"][0]["monthly"] == 0.0 and result["totals"][0]["items_not_priced"] == 1


def test_a_unit_narrows_an_ambiguous_item(cloud_repo: Path, tmp_path: Path) -> None:
    items = [
        {
            "id": "base",
            "service": "Service Bus",
            "sku": "Standard",
            "meter": "Standard Base Unit",
            "unit": "1/Month",
            "quantity": 1,
        }
    ]
    assert priced(tmp_path, cloud_repo / PRICES, items)["items"][0]["monthly"] == 10.0


def test_a_unit_that_does_not_match_is_not_priced(cloud_repo: Path, tmp_path: Path) -> None:
    items = [{**APP_P1, "unit": "1/Month"}]
    item = priced(tmp_path, cloud_repo / PRICES, items)["items"][0]
    assert item["status"] == "unit_mismatch"


def test_an_item_with_no_row_is_reported(cloud_repo: Path, tmp_path: Path) -> None:
    result = priced(
        tmp_path, cloud_repo / PRICES, [{"id": "x", "service": "Azure App Service", "sku": "Z9", "quantity": 1}]
    )
    assert result["items"][0]["status"] == "not_found"


def test_totals_are_per_cloud_and_variant(cloud_repo: Path, tmp_path: Path) -> None:
    items = [{**APP_P1, "id": "a", "variant": "basic"}, {**APP_P1, "id": "b", "variant": "ha", "quantity": 1460}]
    totals = priced(tmp_path, cloud_repo / PRICES, items)["totals"]
    assert [(t["variant"], t["monthly"]) for t in totals] == [("basic", 129.94), ("ha", 259.88)]


def test_a_table_without_a_date_is_refused(tmp_path: Path) -> None:
    table = tmp_path / "t.json"
    table.write_text(json.dumps({"cloud": "azure", "source": "x", "rows": []}))
    done = subprocess.run(
        [sys.executable, str(PRICE), str(bom_file(tmp_path, [APP_P1])), "--prices", str(table)],
        capture_output=True,
        text=True,
    )
    assert done.returncode != 0 and "as_of" in done.stderr


def test_a_bad_bill_is_refused(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(PRICE), "-", "--prices", str(tmp_path / "t.json")],
        input=json.dumps({"items": [{"id": "a"}, {"id": "a", "service": "x", "quantity": "many"}]}),
        capture_output=True,
        text=True,
    )
    assert done.returncode == 1
    assert "service is required" in done.stderr and "duplicate id" in done.stderr and "quantity" in done.stderr


def test_online_or_prices_is_required(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(PRICE), str(bom_file(tmp_path, [APP_P1]))], capture_output=True, text=True
    )
    assert done.returncode != 0


def test_an_installed_skill_finds_its_own_provider_files() -> None:
    skill = ROOT / "plugins" / "cloud-architect" / "skills" / "cloud-design"
    tables = load(skill / "scripts" / "cloud_prices.py")._provider_tables()
    assert tables["azure"]["url"].startswith("https://prices.azure.com/")


def test_a_saved_table_never_touches_the_network(
    cloud_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load(PRICE)

    def no_network(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a saved table must not go online")

    monkeypatch.setattr(module, "_fetch_json", no_network)
    module.run(json.loads(bom_file(tmp_path, [APP_P1]).read_text()), cloud_repo / PRICES, False, 5.0)


ONLINE_ROW = {
    "serviceName": "Azure App Service",
    "productName": "Azure App Service Premium v3 Plan - Linux",
    "skuName": "P1 v3",
    "meterName": "P1 v3 App",
    "armRegionName": "westeurope",
    "unitOfMeasure": "1 Hour",
    "retailPrice": 0.178,
    "tierMinimumUnits": 0.0,
    "currencyCode": "USD",
    "effectiveStartDate": "2020-10-01T00:00:00Z",
    "type": "Consumption",
}


def test_online_asks_the_public_price_list_with_the_right_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load(PRICE)
    urls: list[str] = []

    def fake(url: str, timeout: float) -> dict[str, Any]:
        urls.append(url)
        assert timeout == 7.0
        return {"Items": [ONLINE_ROW], "NextPageLink": None}

    monkeypatch.setattr(module, "_fetch_json", fake)
    result = module.run(json.loads(bom_file(tmp_path, [APP_P1]).read_text()), None, True, 7.0)
    assert urls[0].startswith("https://prices.azure.com/api/retail/prices?")
    assert "serviceName+eq+%27Azure+App+Service%27" in urls[0] and "priceType+eq+%27Consumption%27" in urls[0]
    item = result["items"][0]
    assert item["monthly"] == 129.94 and result["mode"] == "online"
    assert item["as_of"] == result["as_of"] and item["effective_from"] == "2020-10-01"


def test_a_failed_online_call_is_reported_not_raised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = load(PRICE)

    def down(*args: Any, **kwargs: Any) -> None:
        raise URLError("down")

    monkeypatch.setattr(module, "_fetch_json", down)
    result = module.run(json.loads(bom_file(tmp_path, [APP_P1]).read_text()), None, True, 5.0)
    assert result["items"][0]["status"] == "error" and result["not_priced"] == ["app"]
    assert result["errors"][0]["id"] == "app"


# ---------------------------------------------------------------------------- cloud_rules

SMALL = {
    "team_size": 2,
    "platform_engineers": 0,
    "services": 1,
    "containers": False,
    "needs_kubernetes_api": False,
    "needs_os_control": False,
    "event_driven": False,
    "peak_rps": 20,
    "relational": True,
    "data_gb": 30,
    "private_data": False,
    "private_everything": False,
    "many_networks": False,
    "survive_zone_loss": False,
    "survive_region_loss": False,
    "residency_area": "EU",
}
LARGE = {
    "team_size": 8,
    "platform_engineers": 1,
    "services": 6,
    "containers": True,
    "needs_kubernetes_api": False,
    "needs_os_control": False,
    "event_driven": False,
    "max_job_minutes": 1,
    "peak_rps": 600,
    "relational": True,
    "data_gb": 400,
    "private_data": True,
    "private_everything": False,
    "many_networks": False,
    "survive_zone_loss": True,
    "survive_region_loss": False,
    "residency_area": "EU",
}


def rules(facts: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = run_json(RULES, "-", stdin=json.dumps(facts))
    return result


def test_the_small_brief_stays_on_a_managed_platform_and_one_database() -> None:
    ladders = rules(SMALL)["ladders"]
    assert ladders["compute"]["open"] == ["managed_app_platform", "serverless_containers"]
    assert ladders["compute"]["lowest_open"] == "managed_app_platform"
    assert ladders["data"]["open"] == ["managed_relational"]
    assert ladders["network"]["open"] == ["public_restricted", "private_data", "fully_private"]
    assert ladders["availability"]["open"] == ["one_zone"]
    assert ladders["region"]["open"] == ["one_region"]


def test_the_large_brief_needs_containers_private_data_and_zones_but_not_kubernetes() -> None:
    result = rules(LARGE)
    ladders = result["ladders"]
    assert ladders["compute"]["open"] == ["serverless_containers"]
    k8s = next(o for o in ladders["compute"]["options"] if o["id"] == "kubernetes")
    assert {r["rule"] for r in k8s["eliminated_by"]} == {"too-few-platform-engineers", "nothing-asks-for-kubernetes"}
    assert ladders["availability"]["open"] == ["zone_redundant"]
    assert "public_restricted" not in ladders["network"]["open"]
    assert "private_data" in ladders["network"]["open"]
    assert result["thresholds"]["kubernetes_min_platform_engineers"] == 2


def test_unknown_facts_decide_nothing_and_are_listed() -> None:
    result = rules({})
    assert result["ladders"]["compute"]["open"] == [
        "managed_app_platform",
        "serverless_containers",
        "functions",
        "kubernetes",
        "virtual_machines",
    ]
    assert {f["fact"] for f in result["open_facts"]} >= {"services", "platform_engineers", "survive_zone_loss"}


@pytest.mark.parametrize(
    ("facts", "ladder", "closed"),
    [
        ({"services": 5}, "compute", []),
        ({"services": 6}, "compute", ["managed_app_platform"]),
        ({"containers": True}, "compute", ["functions"]),
        ({"event_driven": False}, "compute", ["functions"]),
        ({"max_job_minutes": 30}, "compute", ["functions"]),
        ({"needs_os_control": True}, "compute", ["managed_app_platform", "serverless_containers", "functions"]),
        (
            {"needs_kubernetes_api": True},
            "compute",
            ["managed_app_platform", "serverless_containers", "functions", "virtual_machines"],
        ),
        ({"platform_engineers": 1}, "compute", ["kubernetes"]),
        ({"relational": False}, "data", ["managed_relational", "managed_relational_scaled"]),
        ({"relational": True}, "data", ["managed_document"]),
        ({"data_gb": 5000}, "data", ["managed_relational"]),
        ({"peak_rps": 500}, "data", ["managed_relational_scaled"]),
        ({"private_data": True}, "network", ["public_restricted"]),
        ({"private_everything": True}, "network", ["public_restricted", "private_data"]),
        ({"survive_zone_loss": True}, "availability", ["one_zone"]),
        ({"survive_zone_loss": False}, "availability", ["zone_redundant", "multi_region"]),
        ({"survive_region_loss": True}, "availability", ["one_zone", "zone_redundant"]),
        ({"survive_region_loss": True}, "region", ["one_region"]),
        ({"survive_region_loss": False}, "region", ["two_regions"]),
    ],
)
def test_single_rules(facts: dict[str, Any], ladder: str, closed: list[str]) -> None:
    assert [o["id"] for o in rules(facts)["ladders"][ladder]["options"] if o["status"] == "eliminated"] == closed


def test_the_rules_never_name_a_cloud_or_choose() -> None:
    text = RULES.read_text(encoding="utf-8").lower()
    for word in ("azure", "aws", "google", "app service", "fargate", "cloud run"):
        assert word not in text, word
    assert "chosen" not in text
    output = json.dumps(rules(SMALL)).lower()
    assert "azure" not in output and "chosen" not in output


def test_bad_facts_are_refused() -> None:
    done = subprocess.run(
        [sys.executable, str(RULES), "-"], input='{"services": "many", "colour": 1}', capture_output=True, text=True
    )
    assert done.returncode == 1 and "services: must be a int" in done.stderr and "colour: unknown fact" in done.stderr


def test_the_facts_are_listed_with_what_they_decide() -> None:
    listed: dict[str, Any] = run_json(RULES, "--facts")
    assert listed["services"]["type"] == "int" and "survive_zone_loss" in listed
