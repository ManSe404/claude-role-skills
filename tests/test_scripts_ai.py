"""The ai-architect scripts, run the way Claude runs them, on the acme-assist fixture and small made-up inputs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import ROOT, ai_script, make_repo, run_json
from test_fixture_acme_assist import PLANTED_AT

DECIDE = ai_script("ai-pattern", "decide.py")
CORPUS = ai_script("ai-pattern", "corpus_stats.py")
COST = ai_script("ai-stack", "cost_model.py")
PRICES = ROOT / "plugins" / "ai-architect" / "skills" / "ai-stack" / "references" / "prices.example.json"
INVENTORY = ai_script("ai-review", "ai_inventory.py")

SUPPORT = {
    "needs_language": True,
    "uses_documents": True,
    "corpus_tokens": 1_200_000,
    "context_budget_tokens": 150_000,
    "live_state": True,
    "steps_known": True,
    "distinct_steps": 3,
    "independent_subtasks": False,
    "error_cost": "high",
    "human_review": False,
    "latency_budget_s": 5,
    "seconds_per_call": 1.5,
}
TAGGING = {
    "needs_language": True,
    "uses_documents": False,
    "live_state": False,
    "steps_known": True,
    "distinct_steps": 1,
    "error_cost": "low",
}


def decide(facts: dict[str, Any]) -> Any:
    return run_json(DECIDE, "-", stdin=json.dumps(facts))


# ---------------------------------------------------------------------------- decide.py


def test_the_support_brief_leaves_only_a_workflow() -> None:
    out = decide(SUPPORT)
    assert out["open"] == ["workflow"] and out["lowest_open"] == "workflow"
    rules = {o["id"]: [r["rule"] for r in o["eliminated_by"]] for o in out["options"]}
    assert rules["rag"] == ["live-state"]
    assert rules["long_context"] == ["live-state", "does-not-fit"]
    assert rules["multi_agent"] == ["steps-known", "nothing-to-split", "unreviewed-autonomy"]
    assert out["open_facts"] == []


def test_the_tagging_brief_stops_at_one_call() -> None:
    out = decide(TAGGING)
    assert out["lowest_open"] == "single_call"
    assert out["open"] == ["single_call"]
    assert {f["fact"] for f in out["open_facts"]} == {"latency_budget_s", "seconds_per_call"}


def test_unknown_facts_decide_nothing_and_are_listed() -> None:
    out = decide({"needs_language": True})
    assert out["lowest_open"] == "single_call"
    assert len(out["open"]) == 7
    asked = {f["fact"] for f in out["open_facts"]}
    assert {"live_state", "steps_known", "error_cost", "human_review"} <= asked


def test_a_slow_model_rules_out_the_long_chains() -> None:
    out = decide({"latency_budget_s": 2, "seconds_per_call": 0.9})
    assert [o["id"] for o in out["options"] if o["status"] == "eliminated"] == ["multi_agent"]


def test_bad_facts_are_refused() -> None:
    done = subprocess.run(
        [sys.executable, str(DECIDE), "-"],
        input=json.dumps({"live_state": "yes", "error_cost": "huge", "colour": 1}),
        capture_output=True,
        text=True,
    )
    assert done.returncode == 1
    assert "live_state: must be a bool" in done.stderr
    assert "error_cost: must be one of low, medium, high" in done.stderr
    assert "colour: unknown fact" in done.stderr


# ---------------------------------------------------------------------------- corpus_stats.py


def test_corpus_stats_of_the_fixture(assist: Path) -> None:
    out = run_json(CORPUS, str(assist / "knowledge"), "--window", "150000")
    assert out["files"] == 21 and out["read"] == 21 and out["not_read"] == []
    assert out["scripts"] == {"latin": 14, "serbian latin": 4, "cyrillic": 3}
    assert out["pdf_pages"] == 5 and out["needs_ocr"] == []
    assert out["duplicates"] == [["archive/faq-en-old.md", "faq-en.md"]]
    assert out["window"]["fits"] is True and 8_000 < out["tokens_est"] < 16_000
    assert {r["changed_from"] for r in out["files_detail"]} == {"git"}
    assert out["changed"]["first"].startswith("2026-08-11") and out["changed"]["last"].startswith("2026-10-02")
    pdf = next(r for r in out["files_detail"] if r["path"] == "quick-start/k200-quick-start.pdf")
    assert pdf["pages"] == 2 and pdf["chars"] > 300


def test_corpus_stats_reads_compressed_pdfs_and_flags_scans(tmp_path: Path) -> None:
    import zlib

    line = b"Descale the machine every three months, or when the E4 light blinks."
    stream = zlib.compress(b"BT /F1 12 Tf 72 720 Td (" + line + b") Tj ET")
    pdf = (
        b"%PDF-1.4\n1 0 obj << /Type /Page >> endobj\n2 0 obj << /Length "
        + str(len(stream)).encode()
        + b" /Filter /FlateDecode >>\nstream\n"
        + stream
        + b"\nendstream\nendobj\n%%EOF\n"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.pdf").write_bytes(pdf)
    (tmp_path / "docs" / "scan.pdf").write_bytes(
        b"%PDF-1.4\n1 0 obj << /Type /Page >> endobj\n2 0 obj << /Type /Page >>"
    )
    (tmp_path / "docs" / "photo.png").write_bytes(b"\x89PNG\r\n")
    (tmp_path / "docs" / "upute.txt").write_text("Очистите апарат сваког месеца.", encoding="utf-8")
    out = run_json(CORPUS, str(tmp_path / "docs"))
    detail = {r["path"]: r for r in out["files_detail"]}
    assert detail["guide.pdf"]["chars"] == len(line)
    assert out["needs_ocr"] == ["scan.pdf"] and out["not_read"] == ["photo.png"]
    assert detail["upute.txt"]["script"] == "cyrillic"
    assert detail["upute.txt"]["changed_from"] == "file time"


# ---------------------------------------------------------------------------- cost_model.py


def design(**extra: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "requests_per_day": 3000,
        "days_per_month": 30,
        "variants": [
            {
                "id": "cloud",
                "steps": [
                    {"name": "route", "model": "example-small", "input_tokens": 700, "output_tokens": 20,
                     "cached_share": 0.8, "latency_s": 0.5},
                    {"name": "search", "share": 0.55, "latency_s": 0.2, "group": "fetch"},
                    {"name": "erp", "share": 0.25, "latency_s": 0.4, "group": "fetch"},
                    {"name": "answer", "model": "example-large", "input_tokens": 3500, "output_tokens": 350,
                     "cached_share": 0.3, "share": 0.8, "latency_s": 2.4},
                ],
                "paths": [{"name": "how-to", "steps": ["route", "search", "answer"]},
                          {"name": "both", "steps": ["route", "search", "erp", "answer"]}],
                "fixed_monthly": [{"name": "vector store", "amount": 75, "source": "example", "as_of": "2026-11-01"}],
            }
        ],
    }  # fmt: skip
    base.update(extra)
    return base


def cost(tmp_path: Path, data: dict[str, Any], *args: str) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "design.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(COST), str(path), "--prices", str(PRICES), *args], capture_output=True, text=True
    )


def test_cost_model_counts_at_volume(tmp_path: Path) -> None:
    done = cost(tmp_path, design(), "--today", "2026-11-08")
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    var = out["variants"][0]
    answer = next(s for s in var["steps"] if s["name"] == "answer")
    # (2450 x 3.00 + 1050 x 0.30 + 350 x 15.00) / 1e6 per call, on 80% of 3,000 requests a day for 30 days
    assert answer["cost_per_call"] == pytest.approx(0.012915)
    assert answer["cost_per_month"] == pytest.approx(929.88)
    assert var["total_per_month"] == pytest.approx(var["models_per_month"] + 75)
    assert var["latency_s"] == [{"path": "how-to", "seconds": 3.1}, {"path": "both", "seconds": 3.3}]
    assert out["warnings"] == [
        "EXAMPLE PRICES: the table is marked as an example; replace it before quoting any number."
    ]
    assert out["prices_used"]["example-large"]["as_of"] == "2026-11-01"


def test_cost_model_flags_old_prices_and_refuses_unknown_models(tmp_path: Path) -> None:
    old = json.loads(cost(tmp_path, design(), "--today", "2027-06-01").stdout)
    assert any("days old" in w for w in old["warnings"])
    bad = design()
    bad["variants"][0]["steps"][0]["model"] = "gpt-from-memory"
    bad["variants"][0]["fixed_monthly"] = [{"name": "gpu", "amount": 300}]
    done = cost(tmp_path, bad)
    assert done.returncode == 1
    assert "'gpt-from-memory' is not in the price table" in done.stderr
    assert "fixed_monthly[0]: needs name, amount and source" in done.stderr


def test_cost_model_converts_with_a_dated_rate(tmp_path: Path) -> None:
    fx = {"currency": "EUR", "per_price_unit": 0.5, "as_of": "2026-11-07", "source": "example"}
    out = json.loads(cost(tmp_path, design(fx=fx), "--today", "2026-11-08").stdout)
    var = out["variants"][0]
    assert var["total_per_month_eur"] == pytest.approx(var["total_per_month"] / 2, abs=0.01)


# ---------------------------------------------------------------------------- ai_inventory.py


def test_inventory_finds_the_planted_flaws(assist: Path) -> None:
    out = run_json(INVENTORY, str(assist))
    summary = out["summary"]
    at = {f"{h['file']}:{h['line']}" for key in ("loops", "clients", "models", "secrets", "tools") for h in out[key]}
    assert PLANTED_AT[2] in at  # the unbounded loop
    assert PLANTED_AT[3] in at  # send_email, a tool with a side effect
    assert PLANTED_AT[4] in at  # the key literal
    assert PLANTED_AT[6] in at  # the client without a timeout
    assert PLANTED_AT[7] in at  # the model alias
    assert summary["agent_loops_without_visible_limit"] == 1
    assert summary["tools_with_side_effects"] == ["send_email"]
    assert summary["tools_that_read_outside_content"] == ["fetch_url"]
    assert summary["untrusted_text_can_reach_a_side_effect"] is True
    assert summary["undated_models"] == ["gpt-4o"]
    assert summary["tracing"] == [] and summary["evals"] == []
    assert summary["clients_without_timeout"] == 1
    assert {v["name"] for v in out["vector_stores"]} == {"Qdrant"}
    assert any(h["file"] == "src/acme_assist/stock.py" for h in out["vector_stores"])  # stock lives in the index
    secret = out["secrets"][0]
    assert secret == {"file": "src/acme_assist/config.py", "line": 5, "kind": "openai-style key", "length": 43,
                      "looks_fake": True}  # fmt: skip
    assert "sk-example" not in json.dumps(out)


def test_inventory_never_reads_env_files_or_prints_values(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path / "r",
        {
            "app.py": (
                "import os\nfrom anthropic import Anthropic\n"
                "client = Anthropic(timeout=20, max_retries=2)\n"
                "TOKEN = 'sk-ant-REALLOOKING0123456789abcdef'\n"
                "def ask(q):\n"
                "    for step in range(6):\n"
                "        r = client.messages.create(model='claude-sonnet-4-5-20250929', max_tokens=300, messages=[])\n"
                "    return os.environ['SUPPORT_INBOX']\n"
            ),
            ".env": "ANTHROPIC_API_KEY=sk-ant-hunter2hunter2hunter2\n",
        },
    )
    raw = run_json(INVENTORY, str(repo))
    text = json.dumps(raw)
    assert "hunter2" not in text and "REALLOOKING" not in text
    assert raw["env_files_not_read"] == [".env"]
    assert raw["clients"][0]["timeout"] is True and raw["clients"][0]["retries"] is True
    assert raw["models"][0] == {"file": "app.py", "line": 7, "name": "claude-sonnet-4-5-20250929", "kind": "dated"}
    assert raw["secrets"][0]["looks_fake"] is False
    assert raw["env_vars"] == [{"file": "app.py", "line": 8, "name": "SUPPORT_INBOX", "literal_default": False}]
    assert raw["loops"] == []  # a for loop over range() is bounded


def test_inventory_reads_csharp_and_typescript(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path / "r",
        {
            "Api/Chat.cs": (
                "using Azure.AI.OpenAI;\nusing Microsoft.SemanticKernel;\n"
                "var client = new AzureOpenAIClient(endpoint, credential);\n"
                'var key = Environment.GetEnvironmentVariable("AZURE_OPENAI_KEY");\n'
                "while (true) {\n  var r = await chat.GetChatMessageContentAsync(history);\n}\n"
                "[KernelFunction] public Task SendAsync() => smtp.SendMailAsync(msg);\n"
            ),
            "web/agent.ts": (
                "import OpenAI from 'openai';\nimport { QdrantClient } from '@qdrant/js-client-rest';\n"
                "const model = 'gpt-4.1-mini';\n"
                "const r = await openai.chat.completions.create({ model, messages, timeout: 20000 });\n"
                "const page = await fetch(url);\n"
            ),
        },
    )
    out = run_json(INVENTORY, str(repo))
    assert {s["name"] for s in out["sdks"]} == {"OpenAI / Azure OpenAI"}
    assert {f["name"] for f in out["frameworks"]} == {"Semantic Kernel"}
    assert {v["name"] for v in out["vector_stores"]} == {"Qdrant"}
    assert out["clients"][0]["file"] == "Api/Chat.cs" and out["clients"][0]["timeout"] is False
    calls = {(c["file"], c["timeout"]) for c in out["model_calls"]}
    assert calls == {("Api/Chat.cs", False), ("web/agent.ts", True)}
    assert out["loops"][0]["file"] == "Api/Chat.cs"
    assert out["models"] == [{"file": "web/agent.ts", "line": 3, "name": "gpt-4.1-mini", "kind": "alias"}]
    assert {e["name"] for e in out["env_vars"]} == {"AZURE_OPENAI_KEY"}
    assert out["side_effects"][0]["file"] == "Api/Chat.cs" and out["outside_content"][0]["file"] == "web/agent.ts"
