"""The docs-draft facts script: what the code exposes, what the documents say, and where they drift."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import ROOT, SKILLS, make_repo, run_json

FACTS = SKILLS / "docs-draft" / "scripts" / "docs_facts.py"


@pytest.fixture(scope="module")
def facts(acme: Path) -> dict[str, Any]:
    result: dict[str, Any] = run_json(FACTS, str(acme))
    return result


def by(facts: dict[str, Any], kind: str, name: str) -> dict[str, Any]:
    return next(i for i in facts["exposed"] if i["kind"] == kind and i["name"] == name)


def test_documents_and_their_commands(facts: dict[str, Any]) -> None:
    docs = {d["path"]: d for d in facts["docs"]}
    assert set(docs) == {"README.md", "docs/api.md", "docs/finance-export.md"}
    assert docs["README.md"]["headings"] == ["acme-orders", "Run", "Test"]
    assert [c["command"] for c in docs["README.md"]["commands"]][:2] == [
        "pip install -e .",
        "python -m acme_orders import data/orders-2026-10-02.csv",
    ]
    assert "text" not in docs["README.md"]


def test_commands_flags_and_their_help_come_from_argparse(facts: dict[str, Any]) -> None:
    assert {i["name"] for i in facts["exposed"] if i["kind"] == "command"} == {"import", "check", "report", "serve"}
    assert by(facts, "command", "check")["detail"] == "price an export without saving it"
    notify = by(facts, "flag", "--notify")
    assert notify["command"] == "import" and notify["detail"] == "send receipts" and notify["status"] == "undocumented"
    assert by(facts, "flag", "--adjustments")["status"] == "undocumented"
    assert by(facts, "flag", "--port")["documented_in"] == ["README.md"]


def test_entries_config_and_routes(facts: dict[str, Any]) -> None:
    assert by(facts, "entry", "python -m acme_orders")["status"] == "documented"
    assert by(facts, "entry", "acme-orders")["detail"] == "console script acme_orders.cli:main"
    assert by(facts, "config", "ACME_DB_PATH")["documented_in"] == ["README.md"]
    assert by(facts, "config", "db_path")["detail"] == "key of an example file"
    health = by(facts, "route", "GET /health")
    assert health["status"] == "guessed" and health["documented_in"] == ["docs/api.md"]
    assert by(facts, "target", "PYTHONPATH=src python -m unittest discover -s tests")["detail"] == "CI step"
    assert facts["counts"]["stale"] == 0 and facts["counts"]["exposed"]["command"] == 4


def test_stale_lines_name_what_the_code_no_longer_has(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path / "drift",
        {
            "app/__main__.py": "from app.cli import main\nmain()\n",
            "app/cli.py": (
                "import argparse\nimport os\n\n\ndef main():\n    p = argparse.ArgumentParser(prog='app')\n"
                "    sub = p.add_subparsers(dest='command')\n    run = sub.add_parser('run', help='run it')\n"
                "    run.add_argument('--fast', help='skip checks')\n    os.environ.get('APP_DB')\n"
            ),
            "Makefile": "test:\n\tpytest\n",
            "README.md": (
                "# app\n\n    python -m app frob --nope\n    python -m app run --fast\n    make lint\n\n"
                "Set `APP_DB` and `APP_TOKEN` first.\n\nThe API answers `GET /items` and `GET /health`.\n"
            ),
            "api.py": "@app.get('/items')\ndef items():\n    return []\n",
        },
    )
    out = run_json(FACTS, str(repo))
    whys = sorted(s["why"] for s in out["stale"])
    assert whys == [
        "no Makefile target lint",
        "no command frob in the code",
        "no flag --nope in the code",
        "no route /health in the code",
        "no setting APP_TOKEN in the code",
    ]
    assert all(s["doc"] == "README.md" and s["line"] > 0 for s in out["stale"])
    assert next(i for i in out["exposed"] if i["name"] == "--fast")["status"] == "documented"


def test_env_files_are_never_opened_and_example_files_give_names_only(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path / "env",
        {"app.py": "import os\nos.getenv('APP_SECRET')\n", ".env.example": "APP_SECRET=changeme\nAPP_PORT=8080\n"},
    )
    (repo / ".env").write_text("APP_SECRET=hunter2-real-value\n")
    out = run_json(FACTS, str(repo))
    text = json.dumps(out)
    assert "hunter2" not in text and "changeme" not in text
    names = {i["name"] for i in out["exposed"] if i["kind"] == "config"}
    assert names == {"APP_SECRET", "APP_PORT"}


def test_package_scripts_and_container_commands(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path / "node",
        {
            "package.json": json.dumps({"scripts": {"build": "tsc", "test": "vitest"}}),
            "Dockerfile": 'FROM node:20\nCMD ["node", "dist/server.js"]\n',
            "src/server.ts": "app.get('/ping', (req, res) => res.send('ok'));\nconst db = process.env.DATABASE_URL;\n",
            "README.md": "# svc\n\n    npm run build\n    npm run deploy\n",
        },
    )
    out = run_json(FACTS, str(repo))
    assert {i["name"] for i in out["exposed"] if i["kind"] == "target"} == {"npm run build", "npm run test"}
    assert by(out, "route", "GET /ping")["status"] == "guessed"
    assert by(out, "config", "DATABASE_URL")["detail"] == "process.env"
    assert [s["why"] for s in out["stale"]] == ["no script deploy in package.json"]


def test_path_limits_the_scope_but_keeps_the_top_documents(acme: Path) -> None:
    out = run_json(FACTS, str(acme), "--path", "src")
    assert out["scope"] == "src" and [d["path"] for d in out["docs"]] == ["README.md"]
    assert {i["kind"] for i in out["exposed"]} <= {"command", "flag", "config", "route", "entry"}


@pytest.fixture(scope="module")
def pipeline_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The acme-pipeline fixture of the data-engineer pack, built once for this module. Tests must not change it.
    The fixture lands with that pack; until then these tests skip instead of failing a fresh clone."""
    import build_fixture

    if not (ROOT / "fixtures" / "acme-pipeline" / "history.py").is_file():
        pytest.skip("fixtures/acme-pipeline is not in this checkout yet")
    target = tmp_path_factory.mktemp("fixture") / "acme-pipeline"
    build_fixture.build("acme-pipeline", target)
    return target


def test_jobs_with_their_schedules_and_steps(pipeline_repo: Path) -> None:
    out = run_json(FACTS, str(pipeline_repo))
    jobs = {i["name"]: i for i in out["exposed"] if i["kind"] == "job"}
    assert set(jobs) == {
        "build_sales_daily",
        "ingest_crm",
        "load_erp_finance",
        "load_erp_orders",
        "rebuild_customers",
        "refresh_stock",
    }
    orders = jobs["load_erp_orders"]
    assert orders["schedule"] == "30 6 * * *" and orders["schedule_text"] == "daily at 06:30 (Europe/Belgrade)"
    assert (
        orders["steps"] == ["wait_for_file", "bronze.erp_orders", "silver.orders"] and orders["status"] == "documented"
    )
    assert jobs["refresh_stock"]["schedule_text"].startswith("every 5 minutes")
    assert jobs["ingest_crm"]["enabled"] is False and jobs["ingest_crm"]["status"] == "undocumented"
    assert jobs["build_sales_daily"]["sla"] == "08:00"


def test_runbook_drift_on_a_data_platform(pipeline_repo: Path) -> None:
    """The planted drifts of the fixture's runbook: a renamed job, a renamed target, a renamed setting, a cron that
    moved. The missing contract step of the how-to needs the loader read, not a pattern. `make dq` is a real alias."""
    out = run_json(FACTS, str(pipeline_repo))
    whys = sorted(s["why"] for s in out["stale"])
    assert whys == [
        "job load_erp_orders runs daily at 06:30 (Europe/Belgrade) by its schedule; the document says 05:00",
        "no Makefile target backfill",
        "no job load_crm in the job files",
        "no setting ACME_WAREHOUSE_URL in the code",
    ]
    assert all(s["doc"] == "docs/runbook.md" for s in out["stale"])
    assert not [s for s in out["stale"] if "dq" in s["why"] or "08:00" in s["why"] or "ingest_" in s["why"]]


def test_dags_ci_schedules_and_crontabs_are_jobs(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path / "sched",
        {
            "dags/sales.py": (
                "from airflow import DAG\n\n"
                "with DAG(dag_id='sales_daily', schedule_interval='0 6 * * 1-5') as dag:\n"
                "    a = PythonOperator(task_id='extract')\n"
                "    b = PythonOperator(task_id='load')\n"
            ),
            ".github/workflows/nightly.yml": (
                "name: nightly\non:\n  schedule:\n    - cron: '15 2 * * *'\n"
                "jobs:\n  x:\n    steps:\n      - run: make samples\n"
            ),
            "ops/crontab": "# nightly\n0 */4 * * * acme python3 -m pipeline.runner run refresh_stock\n",
            "Makefile": "samples:\n\tpython3 -m tools.samples\n",
            "README.md": (
                "# p\n\n`sales_daily` runs at 06:00 on weekdays; `old_dag` is gone.\n\n"
                "| job | when |\n|---|---|\n| `old_dag` | 05:00 |\n"
            ),
        },
    )
    out = run_json(FACTS, str(repo))
    jobs = {i["name"]: i for i in out["exposed"] if i["kind"] == "job"}
    assert jobs["sales_daily"]["schedule_text"] == "at 06:00 on Monday, Tuesday, Wednesday, Thursday, Friday"
    assert jobs["sales_daily"]["steps"] == ["extract", "load"] and jobs["sales_daily"]["detail"] == "Airflow DAG"
    assert jobs["nightly"]["schedule_text"] == "daily at 02:15" and jobs["nightly"]["detail"] == "CI schedule"
    crontab = next(j for j in jobs.values() if j["detail"] == "crontab line")
    assert crontab["schedule_text"] == "every 4 hours at :00"
    assert [s["why"] for s in out["stale"]] == ["no job old_dag in the job files"]
