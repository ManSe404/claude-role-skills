"""The tools the assistant can call, with their function schemas."""

import json
import smtplib
from collections.abc import Callable
from email.message import EmailMessage

import httpx

from acme_assist import config, knowledge, stock


def _function(name: str, description: str, **params: str) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {key: {"type": "string", "description": text} for key, text in params.items()},
                "required": list(params),
            },
        },
    }


TOOLS = [
    _function(
        "search_manuals",
        "Search the Kestrel manuals, FAQ, error codes and the warranty, returns and shipping policies.",
        query="What to look for, in the customer's words.",
    ),
    _function(
        "check_stock",
        "Check whether a machine, spare part or accessory is in stock.",
        sku_or_name="A SKU such as K200-BLK, or a product name.",
    ),
    _function(
        "fetch_url",
        "Fetch a web page, for example a link the customer sent, and return its text.",
        url="The full URL.",
    ),
    _function(
        "send_email",
        "Send the customer an e-mail, for example a summary of the steps or a follow-up.",
        to="The customer's e-mail address.",
        subject="The subject line.",
        body="The plain-text body.",
    ),
]


def search_manuals(query: str) -> str:
    return "\n\n---\n\n".join(knowledge.search(query))


def check_stock(sku_or_name: str) -> str:
    return stock.stock_level(sku_or_name)


def fetch_url(url: str) -> str:
    response = httpx.get(url, follow_redirects=True)
    response.raise_for_status()
    return response.text[:20_000]


def send_email(to: str, subject: str, body: str) -> str:
    message = EmailMessage()
    message["From"] = config.MAIL_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(config.SMTP_HOST, 587, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(message)
    return f"E-mail sent to {to}."


HANDLERS: dict[str, Callable[..., str]] = {
    "search_manuals": search_manuals,
    "check_stock": check_stock,
    "fetch_url": fetch_url,
    "send_email": send_email,
}


def run(name: str, arguments: str) -> str:
    """Run the tool the model asked for, with the JSON arguments it gave."""
    return HANDLERS[name](**json.loads(arguments))
