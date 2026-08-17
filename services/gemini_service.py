"""Gemini REST client for AI Smart Receiving invoice extraction.

Deliberately isolated from the Odoo ORM — this module only knows how to
turn a file's bytes into an extraction dict via a plain HTTPS call (the
`requests` package, already a dependency of Odoo itself; no Gemini SDK is
installed or required). `inventory.receipt` is the only caller. Keeping
ORM code out of this file is what makes it possible to unit test the
Gemini call in isolation (mock `requests.post`) without a database.

Product matching is NOT done here on purpose — Gemini's only job is to
read the document; deciding which Odoo product a line refers to is a
deterministic job handled by inventory.receipt._match_ai_product().
"""

import base64
import json

import requests

GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# Gemini 2.5 Flash is fast; this is a generous ceiling for a POC, not a
# tuned production timeout.
REQUEST_TIMEOUT = 60

EXTRACTION_PROMPT = (
    "You are reading a supplier invoice or delivery receipt for a retail "
    "warehouse. Extract the supplier name, the invoice number, the "
    "invoice date if present, and every line item: product name, "
    "UPC/barcode if printed, quantity, and unit price. Quantities must be "
    "the base-unit count as printed on the document (e.g. a line reading "
    "'1 case of 12' is quantity 12) — do not invent a conversion if the "
    "document does not state one. If a value is not present on the "
    "document, omit it or use null rather than guessing. If a date is "
    "present, convert it to strict ISO 8601 YYYY-MM-DD format regardless "
    "of how it is printed on the document."
)

# Gemini's structured-output schema (a constrained subset of OpenAPI's
# Schema object) — the model is forced to return JSON matching this shape,
# so no free-form text parsing is needed downstream. The `description` on
# invoice_date is extra guidance for the model, not a guarantee — the
# backend (inventory.receipt._normalize_ai_invoice_date) still tolerates
# and normalizes other common formats rather than trusting this.
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "supplier": {"type": "STRING"},
        "invoice_number": {"type": "STRING"},
        "invoice_date": {
            "type": "STRING",
            "nullable": True,
            "description": "Invoice date in strict ISO 8601 YYYY-MM-DD format.",
        },
        "lines": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "product_name": {"type": "STRING"},
                    "upc": {"type": "STRING", "nullable": True},
                    "quantity": {"type": "NUMBER"},
                    "unit_price": {"type": "NUMBER"},
                },
                "required": ["product_name", "quantity"],
            },
        },
    },
    "required": ["supplier", "invoice_number", "lines"],
}


class GeminiExtractionError(Exception):
    """Any failure that must leave the receipt in Draft with no lines
    created: missing configuration, an unreadable file, a network/timeout
    error, a non-200 response, or a response that doesn't match the
    expected shape."""


def extract_invoice(file_bytes, mimetype, api_key, model):
    """Calls Gemini with the uploaded file and returns
    (extraction_dict, raw_response_text).

    extraction_dict has keys: supplier, invoice_number, invoice_date
    (optional), lines (list of {product_name, upc, quantity, unit_price}).

    Raises GeminiExtractionError on any failure — callers must not create
    receipt lines or change the receipt's state if this raises.
    """
    if not api_key:
        raise GeminiExtractionError(
            "Gemini API key is not configured. Set it under "
            "Configuration > Settings before extracting."
        )

    url = GEMINI_ENDPOINT.format(model=model)
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": EXTRACTION_PROMPT},
                    {
                        "inline_data": {
                            "mime_type": mimetype,
                            "data": base64.b64encode(file_bytes).decode("ascii"),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }

    try:
        response = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise GeminiExtractionError("Could not reach Gemini: %s" % exc) from exc

    if response.status_code != 200:
        raise GeminiExtractionError(
            "Gemini returned an error (HTTP %s): %s"
            % (response.status_code, response.text[:500])
        )

    try:
        body = response.json()
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(text)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise GeminiExtractionError(
            "Gemini returned a response that could not be understood: %s" % exc
        ) from exc

    if not data.get("supplier") or not data.get("invoice_number"):
        raise GeminiExtractionError(
            "Gemini could not find a supplier and invoice number on this document."
        )
    if not data.get("lines"):
        raise GeminiExtractionError(
            "Gemini did not find any line items on this document."
        )

    return data, response.text
