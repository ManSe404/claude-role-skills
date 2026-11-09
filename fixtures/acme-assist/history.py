"""The git history of the acme-assist fixture.

The files under files/ are the state after the last commit. Each commit lists the files it adds
and the edits it makes, as (path, before, after). The builder walks the list backwards, undoing
each edit, to recover the state after every commit, then replays it forwards with git.

The story: Acme Devices in Novi Sad makes the Kestrel coffee machines and sells them in Serbia
and the EU. In August and September 2026 a contractor built a quick support chat prototype: chat
over the manuals, stock answers from the nightly warehouse export, then an agent with tools that
can read web pages and send e-mail. In October Acme's head of customer service added two briefs
for what comes next: a support assistant for all customers and a small e-mail tagger. Everything
here is fictional.
"""

# One commit edits the Serbian Cyrillic warranty policy, so Cyrillic letters in strings are intended.
# ruff: noqa: RUF001

DEJAN = ("Dejan Popov", "dejan.popov@example.com")
JELENA = ("Jelena Radin", "jelena.radin@example.com")

COMMITS = [
    {
        "date": "2026-08-11T10:05:00+02:00",
        "author": DEJAN,
        "message": "Prototype: chat over the Kestrel manuals",
        "add": [
            "README.md",
            "pyproject.toml",
            ".gitignore",
            "src/acme_assist/__init__.py",
            "src/acme_assist/__main__.py",
            "src/acme_assist/config.py",
            "src/acme_assist/llm.py",
            "src/acme_assist/knowledge.py",
            "src/acme_assist/app.py",
            "src/acme_assist/prompts/system.md",
            "knowledge/manuals/k200-manual-en.md",
            "knowledge/manuals/k300-manual-en.md",
            "knowledge/manuals/mf1-frother-manual-en.md",
            "knowledge/faq-en.md",
            "knowledge/troubleshooting/error-codes.txt",
            "knowledge/care/cleaning-guide.txt",
        ],
    },
    {
        "date": "2026-08-18T14:20:00+02:00",
        "author": DEJAN,
        "message": "Add the warranty, returns and shipping policies and the spare parts list",
        "add": [
            "knowledge/policies/warranty-en.md",
            "knowledge/policies/returns-en.md",
            "knowledge/policies/shipping-en.md",
            "knowledge/parts/spare-parts.md",
        ],
        "edit": [
            (
                "src/acme_assist/prompts/system.md",
                "- Be friendly and short.",
                "- For returns, explain the policy and tell the customer that a return needs an RMA number.\n"
                "- Be friendly and short.",
            ),
        ],
    },
    {
        "date": "2026-08-26T11:40:00+02:00",
        "author": DEJAN,
        "message": "Serbian manuals, FAQ and policies, in Latin and Cyrillic",
        "add": [
            "knowledge/manuals/k200-uputstvo-sr.md",
            "knowledge/faq-sr.md",
            "knowledge/faq-sr-cyrl.md",
            "knowledge/policies/garancija-sr.md",
            "knowledge/policies/garancija-sr-cyrl.md",
            "knowledge/policies/povracaj-sr.md",
            "knowledge/care/ciscenje-sr-cyrl.txt",
        ],
        "edit": [
            (
                "src/acme_assist/prompts/system.md",
                "- Answer in English.\n",
                "- Answer in the language the customer writes in. Customers write in Serbian or English. If they\n"
                "  write Serbian in Cyrillic, answer in Cyrillic.\n",
            ),
        ],
    },
    {
        "date": "2026-09-03T09:15:00+02:00",
        "author": DEJAN,
        "message": "Stock answers from the nightly warehouse export",
        "add": [
            "src/acme_assist/snapshot.py",
            "src/acme_assist/stock.py",
            "tests/test_snapshot.py",
        ],
        "edit": [
            (".gitignore", ".env\n", ".env\ndata/\n"),
            (
                "src/acme_assist/config.py",
                'KNOWLEDGE_DIR = "knowledge"\n',
                'KNOWLEDGE_DIR = "knowledge"\n'
                "\n"
                'STOCK_COLLECTION = "acme_stock"\n'
                'STOCK_SNAPSHOT = "data/stock_snapshot.csv"\n',
            ),
            (
                "src/acme_assist/knowledge.py",
                "def search(query: str, limit: int = 4) -> list[str]:",
                "def search(query: str, collection: str = config.KNOWLEDGE_COLLECTION, limit: int = 4) -> list[str]:",
            ),
            (
                "src/acme_assist/knowledge.py",
                "query_points(collection_name=config.KNOWLEDGE_COLLECTION, query=vector",
                "query_points(collection_name=collection, query=vector",
            ),
            (
                "src/acme_assist/app.py",
                "from acme_assist import knowledge, llm\n",
                "from acme_assist import knowledge, llm, stock\n",
            ),
            (
                "src/acme_assist/app.py",
                "    context = knowledge.search(question)\n",
                "    context = knowledge.search(question) + [stock.stock_level(question)]\n",
            ),
            (
                "src/acme_assist/__main__.py",
                '"""Command line: index the knowledge folder or serve the chat API."""',
                '"""Command line: index the knowledge folder or the stock export, or serve the chat API."""',
            ),
            (
                "src/acme_assist/__main__.py",
                '    sub.add_parser("index", help="index the knowledge folder into Qdrant")\n',
                '    sub.add_parser("index", help="index the knowledge folder into Qdrant")\n'
                '    sub.add_parser("index-stock", help="index the nightly stock export into Qdrant")\n',
            ),
            (
                "src/acme_assist/__main__.py",
                '        print(f"indexed {knowledge.index_folder()} chunks")\n',
                '        print(f"indexed {knowledge.index_folder()} chunks")\n'
                '    elif args.command == "index-stock":\n'
                "        from acme_assist import stock\n"
                "\n"
                '        print(f"indexed {stock.index_stock()} stock rows")\n',
            ),
            (
                "README.md",
                "  and stores their embeddings in Qdrant.\n",
                "  and stores their embeddings in Qdrant.\n"
                "- The warehouse system exports stock every night to `data/stock_snapshot.csv`. A cron job runs\n"
                "  `python -m acme_assist index-stock` after the export.\n",
            ),
            (
                "README.md",
                "finds the closest chunks\n  and asks the model to answer from them.\n",
                "finds the closest chunks\n"
                "  and the closest line of the stock export, and asks the model to answer from them.\n",
            ),
            (
                "README.md",
                "    python -m acme_assist index\n",
                "    python -m acme_assist index\n    python -m acme_assist index-stock\n",
            ),
            ("README.md", "", "\n## Test\n\n    PYTHONPATH=src python -m unittest discover -s tests\n"),
        ],
    },
    {
        "date": "2026-09-15T16:30:00+02:00",
        "author": DEJAN,
        "message": "Agent with tools: manual search, stock check, web lookup and e-mail follow-up",
        "add": ["src/acme_assist/agent.py", "src/acme_assist/tools.py"],
        "edit": [
            ("pyproject.toml", 'version = "0.1.0"', 'version = "0.2.0"'),
            ("pyproject.toml", '    "uvicorn",\n', '    "uvicorn",\n    "httpx",\n'),
            ("src/acme_assist/__init__.py", '__version__ = "0.1.0"', '__version__ = "0.2.0"'),
            (
                "src/acme_assist/config.py",
                'STOCK_SNAPSHOT = "data/stock_snapshot.csv"\n',
                'STOCK_SNAPSHOT = "data/stock_snapshot.csv"\n'
                "\n"
                'SMTP_HOST = os.getenv("SMTP_HOST")\n'
                'SMTP_USER = os.getenv("SMTP_USER")\n'
                'SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")\n'
                'MAIL_FROM = os.getenv("MAIL_FROM")\n',
            ),
            (
                "src/acme_assist/llm.py",
                "def chat(messages: list[dict[str, Any]]) -> Any:",
                "def chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> Any:",
            ),
            (
                "src/acme_assist/llm.py",
                '"temperature": 0.2}\n',
                '"temperature": 0.2}\n    if tools:\n        kwargs["tools"] = tools\n',
            ),
            (
                "src/acme_assist/app.py",
                "from pathlib import Path\nfrom typing import Any, Literal\n",
                "from typing import Literal\n",
            ),
            (
                "src/acme_assist/app.py",
                "from acme_assist import knowledge, llm, stock\n",
                "from acme_assist import agent\n",
            ),
            (
                "src/acme_assist/app.py",
                'app = FastAPI(title="Acme Assist")\n'
                "\n"
                'SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system.md").read_text(encoding="utf-8")\n',
                'app = FastAPI(title="Acme Assist")\n',
            ),
            (
                "src/acme_assist/app.py",
                "class ChatResponse(BaseModel):\n"
                "    answer: str\n"
                "\n"
                "\n"
                "def answer(history: list[dict[str, Any]]) -> str:\n"
                '    question = history[-1]["content"]\n'
                "    context = knowledge.search(question) + [stock.stock_level(question)]\n"
                '    documents = "\\n\\n---\\n\\n".join(context)\n'
                "    messages = [\n"
                '        {"role": "system", "content": SYSTEM_PROMPT},\n'
                '        {"role": "system", "content": f"Documents:\\n\\n{documents}"},\n'
                "        *history,\n"
                "    ]\n"
                '    return llm.chat(messages).content or ""\n'
                "\n"
                "\n",
                "class ChatResponse(BaseModel):\n    answer: str\n\n\n",
            ),
            (
                "src/acme_assist/app.py",
                "    return ChatResponse(answer=answer(history))\n",
                "    return ChatResponse(answer=agent.answer(history))\n",
            ),
            (
                "src/acme_assist/prompts/system.md",
                "- Answer only from the documents you are given.\n",
                "- Use search_manuals for how-to, troubleshooting, error codes, warranty, returns and shipping,\n"
                "  and answer from what it returns.\n"
                "- Use check_stock when the customer asks whether a machine, part or accessory is available.\n"
                "- If the customer sends a link, read it with fetch_url.\n"
                "- If the customer wants the steps by e-mail, or a follow-up would help, send it with send_email.\n",
            ),
            (
                "README.md",
                "MF-1 milk frother. Customers ask in the chat widget on the shop. The assistant answers from\n"
                "the manuals in `knowledge/`.\n",
                "MF-1 milk frother. Customers ask in the chat widget on the shop, in Serbian or English. The\n"
                "assistant answers from the manuals and policies in `knowledge/`, checks stock, reads links the\n"
                "customer sends and can e-mail a follow-up.\n",
            ),
            (
                "README.md",
                "- `POST /chat` takes the customer's message and the conversation so far, finds the closest chunks\n"
                "  and the closest line of the stock export, and asks the model to answer from them.\n",
                "- `POST /chat` takes the customer's message and the conversation so far. The agent answers and\n"
                "  calls tools as it needs them: `search_manuals`, `check_stock`, `fetch_url` and `send_email`.\n",
            ),
            (
                "README.md",
                "`OPENAI_API_KEY`, `OPENAI_BASE_URL` and `QDRANT_URL`.\n",
                "`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `QDRANT_URL`,\n"
                "`SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` and `MAIL_FROM`.\n",
            ),
        ],
    },
    {
        "date": "2026-09-24T10:10:00+02:00",
        "author": JELENA,
        "message": "Warranty policy 2026: digital receipts, new unit when dead on arrival",
        "edit": [
            (
                "knowledge/policies/warranty-en.md",
                "Effective 1 March 2025.\n",
                "Effective 1 October 2026. Replaces the version of 1 March 2025.\n",
            ),
            (
                "knowledge/policies/warranty-en.md",
                "The original receipt or invoice with the date of purchase.\n",
                "The receipt or invoice with the date of purchase. Digital receipts and the order confirmation\n"
                "e-mail from the Acme shop are accepted.\n",
            ),
            (
                "knowledge/policies/warranty-en.md",
                "",
                "## Dead on arrival\n"
                "\n"
                "If a product does not work when you first unpack it, report it within 30 days of delivery. Once\n"
                "support confirms the fault, our staff issue an RMA number and we send a new unit instead of\n"
                "repairing the old one.\n"
                "\n",
            ),
            (
                "knowledge/policies/garancija-sr.md",
                "Važe od 1. marta 2025.\n",
                "Važe od 1. oktobra 2026. Zamenjuju verziju od 1. marta 2025.\n",
            ),
            (
                "knowledge/policies/garancija-sr.md",
                "Originalni fiskalni račun ili faktura sa datumom kupovine.\n",
                "Fiskalni račun ili faktura sa datumom kupovine. Prihvatamo i elektronski račun i e-poruku sa\n"
                "potvrdom porudžbine iz Acme prodavnice.\n",
            ),
            (
                "knowledge/policies/garancija-sr.md",
                "",
                "## Neispravan pri isporuci\n"
                "\n"
                "Ako proizvod ne radi kada ga prvi put raspakujete, prijavite to u roku od 30 dana od isporuke.\n"
                "Kada podrška potvrdi kvar, naše osoblje izdaje RMA broj i šaljemo vam nov uređaj umesto da\n"
                "popravljamo stari.\n"
                "\n",
            ),
            (
                "knowledge/policies/garancija-sr-cyrl.md",
                "Важе од 1. марта 2025.\n",
                "Важе од 1. октобра 2026. Замењују верзију од 1. марта 2025.\n",
            ),
            (
                "knowledge/policies/garancija-sr-cyrl.md",
                "Оригинални фискални рачун или фактура са датумом куповине.\n",
                "Фискални рачун или фактура са датумом куповине. Прихватамо и електронски рачун и е-поруку са\n"
                "потврдом поруџбине из Acme продавнице.\n",
            ),
            (
                "knowledge/policies/garancija-sr-cyrl.md",
                "",
                "## Неисправан при испоруци\n"
                "\n"
                "Ако производ не ради када га први пут распакујете, пријавите то у року од 30 дана од испоруке.\n"
                "Када подршка потврди квар, наше особље издаје RMA број и шаљемо вам нов уређај уместо да\n"
                "поправљамо стари.\n"
                "\n",
            ),
        ],
    },
    {
        "date": "2026-10-02T15:30:00+02:00",
        "author": DEJAN,
        "message": "Add the PDF quick-start guides and the safety sheet, keep a copy of the FAQ before the rewrite",
        "add": [
            "knowledge/quick-start/k200-quick-start.pdf",
            "knowledge/quick-start/k300-quick-start.pdf",
            "knowledge/safety/safety-sheet.pdf",
            "knowledge/archive/faq-en-old.md",
        ],
        "edit": [
            (
                "README.md",
                "  and stores their embeddings in Qdrant.\n",
                "  and stores their embeddings in Qdrant. The PDF quick-start guides and the safety sheet are kept\n"
                "  in `knowledge/` for reference.\n",
            ),
        ],
    },
    {
        "date": "2026-10-14T09:30:00+02:00",
        "author": JELENA,
        "message": "Brief: support assistant v2",
        "add": ["docs/briefs/support-v2.md"],
        "edit": [
            (
                "README.md",
                "",
                "\n## Next steps\n\nAcme's briefs for what comes after the prototype are in `docs/briefs/`.\n",
            ),
        ],
    },
    {
        "date": "2026-10-21T13:15:00+02:00",
        "author": JELENA,
        "message": "Brief: e-mail tagging for the shared inbox",
        "add": ["docs/briefs/email-tagging.md"],
    },
]
