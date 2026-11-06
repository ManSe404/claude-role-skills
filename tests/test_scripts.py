"""The skills' scripts, run the way Claude runs them, against the fixture and small made-up repos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import load, make_repo, run_json, script

# ---------------------------------------------------------------------------- codebase-map


def test_inventory_counts_the_fixture(acme: Path) -> None:
    out = run_json(script("codebase-map", "inventory.py"), str(acme))
    assert out["git"]["commits"] == 13
    assert out["git"]["head"] == "f36ec1c"
    assert out["git"]["churn"][0] == {"path": "src/acme_orders/cli.py", "commits": 5}
    assert out["git"]["commits_per_file"]["src/acme_orders/storage.py"] == 1
    kinds = {(e["kind"], e["path"]) for e in out["entry_points"]}
    assert ("console script", "src/acme_orders/cli.py") in kinds
    assert ("python -m package", "src/acme_orders/__main__.py") in kinds
    assert ("container command", "Dockerfile") in kinds
    assert {v["name"] for v in out["env_vars"]} == {
        "ACME_DB_PATH",
        "ACME_MAIL_API_KEY",
        "ACME_MAIL_API_URL",
        "ACME_VAT_RATE",
    }
    assert out["tests"]["files"] == 2
    assert ".github/workflows/ci.yml" in out["ci"]


def test_inventory_never_reads_env_files(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path / "r",
        {
            "app.py": "import os\nURL = os.environ['SERVICE_URL']\n",
            ".env": "SERVICE_URL=https://user:hunter2@example.com\n",
            ".env.example": "SERVICE_URL=\n",
        },
    )
    raw = json.dumps(run_json(script("codebase-map", "inventory.py"), str(repo)))
    assert "hunter2" not in raw
    out = json.loads(raw)
    assert out["env_files_not_read"] == [".env"]
    assert out["env_vars"][0]["name"] == "SERVICE_URL"


def test_imports_graph_of_the_fixture(acme: Path) -> None:
    out = run_json(script("codebase-map", "imports.py"), str(acme))["python"]
    edges = {(e["from"], e["to"]) for e in out["edges"]}
    assert ("acme_orders.cli", "acme_orders.importer") in edges
    assert ("acme_orders.importer", "acme_orders.pricing") in edges
    assert ("acme_orders.report", "acme_orders.pricing") in edges
    assert {e["package"] for e in out["external"]} == {"jinja2", "requests", "yaml"}


def test_imports_resolves_relative_python_and_js(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path / "r",
        {
            "pkg/__init__.py": "",
            "pkg/a/__init__.py": "",
            "pkg/a/x.py": "from ..b import y\nimport numpy\n",
            "pkg/b/__init__.py": "",
            "pkg/b/y.py": "",
            "web/src/app/main.ts": "import { h } from '../lib/util';\nimport React from 'react';\n",
            "web/src/lib/util.ts": "export const h = 1;\n",
        },
    )
    out = run_json(script("codebase-map", "imports.py"), str(repo))
    assert {"from": "pkg.a", "to": "pkg.b", "imports": 1} in out["python"]["edges"]
    assert [e["package"] for e in out["python"]["external"]] == ["numpy"]
    assert {"from": "app", "to": "lib", "imports": 1} in out["javascript"]["edges"]
    assert [e["package"] for e in out["javascript"]["external"]] == ["react"]


# ---------------------------------------------------------------------------- impact


def test_refs_classifies_and_finds_the_dynamic_call(acme: Path) -> None:
    out = run_json(script("impact", "refs.py"), "order_total", "--repo", str(acme), "--dynamic")
    matches = out["names"]["order_total"]["matches"]
    definition = [m for m in matches if m["kind"] == "definition"]
    assert [(m["path"], m["line"]) for m in definition] == [("src/acme_orders/pricing.py", 35)]
    code_uses = {(m["path"], m["enclosing"]) for m in matches if m["area"] == "code" and m["kind"] == "use"}
    assert ("src/acme_orders/importer.py", "import_file") in code_uses
    assert ("src/acme_orders/cli.py", "main") in code_uses
    related = [s for s in out["dynamic_sites"] if "order_total" in s["related_to"]]
    assert [(s["path"], s["line"]) for s in related] == [("src/acme_orders/report.py", 34)]


def test_refs_kinds() -> None:
    refs = load(script("impact", "refs.py"))
    assert refs.kind_of("def order_total(order):", "order_total") == "definition"
    assert refs.kind_of("export async function load() {", "load") == "definition"
    assert refs.kind_of("    public decimal Total(Order o) {", "Total") == "definition"
    assert refs.kind_of("from acme import order_total", "order_total") == "import"
    assert refs.kind_of('x = registry["order_total"]', "order_total") == "string"
    assert refs.kind_of("y = order_total(o)", "order_total") == "use"


# ---------------------------------------------------------------------------- bug-hunt


def test_suspects_maps_the_deployed_trace_and_blames_the_commit(acme: Path) -> None:
    out = run_json(script("bug-hunt", "suspects.py"), str(acme / "logs" / "acme-orders.log"), "--repo", str(acme))
    assert out["tracebacks_in_input"] == 2
    assert out["error"] == "decimal.InvalidOperation: [<class 'decimal.ConversionSyntax'>]"
    inner = out["innermost_in_repo"]
    assert (inner["repo_path"], inner["line"], inner["code_moved"]) == ("src/acme_orders/importer.py", 28, False)
    assert inner["last_change_of_line"]["commit"] == "49bc16d"
    assert inner["last_change_of_line"]["summary"] == "importer: simplify amount parsing"
    assert [f["in_repo"] for f in out["frames"][:2]] == [False, False]  # <frozen runpy>


def test_suspects_reads_other_trace_styles(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path / "r",
        {"src/api/orders.ts": "a\nb\nc\n", "src/Shop/Cart.cs": "x\ny\n", "a/util.py": "1\n", "b/util.py": "2\n"},
    )
    trace = (
        "TypeError: x is undefined\n"
        "    at handler (/app/src/api/orders.ts:2:13)\n"
        "   at Shop.Cart.Total() in C:\\build\\src\\Shop\\Cart.cs:line 1\n"
        '  File "/srv/util.py", line 1, in f\n'
    )
    out = run_json(script("bug-hunt", "suspects.py"), "-", "--repo", str(repo), stdin=trace)
    by_style = {f["style"]: f for f in out["frames"]}
    assert by_style["node"]["repo_path"] == "src/api/orders.ts"
    assert by_style["node"]["code_now"] == "b"
    assert by_style["python"]["repo_path"] is None
    assert sorted(by_style["python"]["ambiguous"]) == ["a/util.py", "b/util.py"]
    assert "dotnet" in by_style


# ---------------------------------------------------------------------------- test-gap


def test_gaps_ranks_the_fixture(acme: Path) -> None:
    out = run_json(script("test-gap", "gaps.py"), str(acme))
    assert out["coverage_source"] is None
    by_path = {r["path"]: r for r in out["ranked"]}
    assert by_path["src/acme_orders/storage.py"]["named_by_tests"] == []
    assert "tests/test_importer.py" in by_path["src/acme_orders/importer.py"]["named_by_tests"]
    assert "sql" in by_path["src/acme_orders/storage.py"]["risk_families"]
    assert "parsing" not in by_path["src/acme_orders/cli.py"]["risk_families"]  # parse_args is not parsing
    assert out["tests"] == {"tests": 7, "no_assert": [], "skipped": []}


def test_gaps_reads_coverage_and_judges_tests(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path / "r",
        {
            "src/app/money.py": "def total(a):\n    return a\n",
            "src/app/other.py": "def f():\n    return 1\n",
            "tests/test_money.py": (
                "import pytest\nfrom app import money\n\n"
                "def test_nothing():\n    money.total(1)\n\n"
                "@pytest.mark.skip\ndef test_later():\n    assert False\n"
            ),
            "lcov.info": "SF:/ci/build/src/app/money.py\nLF:10\nLH:4\nend_of_record\n",
        },
    )
    out = run_json(script("test-gap", "gaps.py"), str(repo))
    by_path = {r["path"]: r for r in out["ranked"]}
    assert out["coverage_source"] == "lcov.info"
    assert by_path["src/app/money.py"]["covered"] == 0.4
    assert out["tests"]["no_assert"] == ["tests/test_money.py:4 test_nothing"]
    assert out["tests"]["skipped"] == ["tests/test_money.py:8 test_later"]


# ---------------------------------------------------------------------------- dependency-audit


def test_deps_offline_on_the_fixture(acme: Path) -> None:
    out = run_json(script("dependency-audit", "deps.py"), str(acme))
    deps = {d["name"]: d for d in out["dependencies"]}
    assert deps["requests"]["version"] == "2.19.1"
    assert deps["requests"]["imported_in"] == ["src/acme_orders/notify.py"]
    assert deps["PyYAML"]["imported_in"] == ["src/acme_orders/config.py"]
    assert deps["python-dateutil"]["imported_in"] == []
    assert deps["Jinja2"]["lookup"] == {"version": "2.10", "basis": "lowest version the range allows"}
    kinds = {f["kind"] for f in out["offline_findings"]}
    assert {"no lock file", "no version constraint"} <= kinds
    assert out["online"] == {"done": False}


def test_deps_reads_npm_nuget_and_locks(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path / "r",
        {
            "web/package.json": json.dumps(
                {"dependencies": {"left-pad": "^1.3.0"}, "devDependencies": {"vite": "5.4.0"}}
            ),
            "web/package-lock.json": json.dumps(
                {
                    "lockfileVersion": 3,
                    "packages": {
                        "": {},
                        "node_modules/left-pad": {"version": "1.3.0"},
                        "node_modules/vite": {"version": "5.4.0"},
                        "node_modules/vite/node_modules/esbuild": {"version": "0.21.5"},
                    },
                }
            ),
            "Directory.Packages.props": (
                '<Project><ItemGroup><PackageVersion Include="Serilog" Version="3.1.1" /></ItemGroup></Project>'
            ),
            "src/Api/Api.csproj": '<Project><ItemGroup><PackageReference Include="Serilog" /></ItemGroup></Project>',
            "pyproject.toml": '[project]\nname="x"\ndependencies=["httpx>=0.27"]\n',
            "uv.lock": (
                '[[package]]\nname = "x"\nversion = "0.1.0"\nsource = { virtual = "." }\n\n'
                '[[package]]\nname = "httpx"\nversion = "0.28.1"\n\n[[package]]\nname = "anyio"\nversion = "4.6.0"\n'
            ),
        },
    )
    out = run_json(script("dependency-audit", "deps.py"), str(repo))
    deps = {(d["ecosystem"], d["name"]): d for d in out["dependencies"]}
    assert deps[("npm", "left-pad")]["locked"] == "1.3.0"
    assert deps[("npm", "esbuild")]["direct"] is False
    assert deps[("nuget", "Serilog")]["version"] == "3.1.1"
    assert deps[("python", "httpx")]["version"] == "0.28.1"
    assert deps[("python", "anyio")]["direct"] is False
    assert ("python", "x") not in deps
    assert not any(f["kind"] == "no lock file" for f in out["offline_findings"])


def test_deps_online_merges_advisories_and_finds_the_fix(acme: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    deps = load(script("dependency-audit", "deps.py"))
    result = deps.inventory(acme)

    def fake(url: str, timeout: float, body: Any = None) -> Any:
        assert timeout == 5
        if url.endswith("/querybatch"):
            return {
                "results": [
                    {"vulns": [{"id": "GHSA-a"}, {"id": "PYSEC-a"}]} if q["package"]["name"] == "PyYAML" else {}
                    for q in body["queries"]
                ]
            }
        if "/vulns/" in url:
            vid = url.rsplit("/", 1)[1]
            return {
                "id": vid,
                "aliases": ["CVE-2020-14343"],
                "summary": "FullLoader runs code" if vid.startswith("GHSA") else "",
                "database_specific": {"severity": "CRITICAL"} if vid.startswith("GHSA") else {},
                "affected": [
                    {
                        "package": {"ecosystem": "PyPI", "name": "pyyaml"},
                        "ranges": [{"events": [{"introduced": "0"}, {"fixed": "5.4"}]}],
                    }
                ],
            }
        if "pypi.org" in url:
            return {"info": {"version": "6.0.3", "license": "MIT"}, "releases": {}}
        raise AssertionError(url)

    monkeypatch.setattr(deps, "http_json", fake)
    deps.go_online(result, 5)
    yaml = next(d for d in result["dependencies"] if d["name"] == "PyYAML")
    assert len(yaml["vulns"]) == 1
    vuln = yaml["vulns"][0]
    assert (vuln["cve"], vuln["severity"], vuln["fixed_in"]) == ("CVE-2020-14343", "critical", "5.4")
    assert sorted(vuln["ids"]) == ["GHSA-a", "PYSEC-a"]
    assert yaml["major_behind"] == 1
    assert result["online"]["errors"] == []


def test_version_order() -> None:
    deps = load(script("dependency-audit", "deps.py"))
    ordered = ["1.0.0rc1", "1.0.0", "1.0.1", "1.2", "1.10", "2.0.0-beta.2", "2.0.0"]
    assert sorted(reversed(ordered), key=deps.vkey) == ordered
    assert deps.exact("python", "==2.19.1") == "2.19.1"
    assert deps.exact("python", ">=2.10,<3") is None
    assert deps.exact("npm", "^1.3.0") is None
    assert deps.lowest_allowed("npm", "^1.3.0") == "1.3.0"
    assert deps.lowest_allowed("python", "~=3.1") == "3.1"
