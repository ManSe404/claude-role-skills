# What to look for in an AI solution

Go through every item. Give each one a status on the page: **found** (a finding with file:line),
**not found** (say what you checked), or **not checked** (say why). The inventory script gives
leads, never verdicts: read the code at each line before it becomes a finding.

| # | Anti-pattern | Lead in `ai_inventory.py` | Why it fails | Usual severity |
|---|---|---|---|---|
| 1 | **The pattern is too big for the job** | `loops`, `frameworks`, `tools` against what the brief asks | An agent where a workflow would do: slower, dearer, a new path each time, hard to test | medium |
| 2 | **Live state through retrieval** | `vector_stores` used for data that changes: stock, status, prices | The index is as old as its last run; the answer is confidently wrong | high |
| 3 | **Agent loop without a limit** | `loops` with `calls_model` and no `limit_visible` | A confused model loops forever: cost and latency with no ceiling | high |
| 4 | **Untrusted text reaches an action** | `tools_that_read_outside_content` or user input, plus `tools_with_side_effects`, no confirmation | Prompt injection: a web page, a document or a message tells the model to send, write or pay | high |
| 5 | **A key in the code** | `secrets` (kind and length only) | It ends up in git history, logs and copies; a fake default hides a missing setting | high if real, low if fake |
| 6 | **No evals** | `evals` empty | No one knows whether a prompt or model change made it better or worse | high before launch |
| 7 | **No tracing** | `tracing` empty | A wrong answer cannot be explained: which passages, which tool, which step | medium |
| 8 | **No timeout, retry or fallback on model calls** | `clients` and `model_calls` with `timeout: false` | One slow call holds a worker for minutes (SDK defaults can be ten minutes) | medium |
| 9 | **Personal data to an outside model** | model calls with customer messages; base URLs; the brief's data rules | Breaks data-residency or processing terms; leaks through logs | high if the brief forbids it |
| 10 | **The model is not pinned** | `models` with kind `alias` or `tag` | The provider moves the alias; behaviour changes with no deploy | medium |
| 11 | **Cost at volume never estimated** | no max tokens, history appended without a cap, no cost in traces | The first month's bill is the first estimate | medium |

Also worth a look, when they apply:
- an open endpoint (no auth) in front of a model that can act: anyone can drive the tools;
- tool arguments logged in full: e-mail addresses, order numbers and tokens end up in logs;
- documents skipped by the indexer (PDFs, scans) or indexed twice (copies), so answers miss or repeat;
- answers without a source shown to the user, so a wrong one cannot be checked;
- one prompt doing several jobs, so nothing can be tested on its own.

## How to write a finding

- **Title**: what is wrong, in words the client understands.
- **Where**: `file:line` of the line that shows it; several when it spans files.
- **Evidence**: the code fact (quote a line, never a secret value) and the failure it leads to.
- **Fix**: the smallest change that removes the risk. Example: "cap the loop at 6 steps and 20,000
  tokens, then hand over to a person". Not "add guardrails".
- **Severity**: high when it can send, change or leak something, or cost without a ceiling;
  medium when it hurts reliability or the ability to explain; low for hygiene.

## Sources

- OWASP Top 10 for LLM Applications 2025: LLM01 Prompt Injection, LLM02 Sensitive Information
  Disclosure, LLM06 Excessive Agency, LLM10 Unbounded Consumption. https://genai.owasp.org/llm-top-10/
- Simon Willison, *The lethal trifecta for AI agents* (2025): private data, untrusted content and
  a way to send data out, in one agent. https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/
- Anthropic, *Building effective agents* (2024): start simple, add complexity only when it pays.
