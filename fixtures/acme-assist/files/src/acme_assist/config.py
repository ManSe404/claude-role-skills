"""Settings, read from the environment."""

import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-example-4f9c2a7e1b3d8f6a0c5e9b2d7a1f3c8e")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
CHAT_MODEL = "gpt-4o"
EMBEDDING_MODEL = "text-embedding-3-small"

QDRANT_URL = os.getenv("QDRANT_URL")
KNOWLEDGE_COLLECTION = "acme_knowledge"
KNOWLEDGE_DIR = "knowledge"

STOCK_COLLECTION = "acme_stock"
STOCK_SNAPSHOT = "data/stock_snapshot.csv"

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM")
