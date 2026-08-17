import base64
from datetime import date
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestAIReceivingInvoiceDate(TransactionCase):
    """AI Smart Receiving — invoice_date normalization.

    Gemini is instructed to return invoice_date as YYYY-MM-DD (see
    services/gemini_service.py), but a real call has been observed to
    return other formats (e.g. '7/7/2026'), which previously crashed
    action_extract_ai() with an unhandled ValueError from
    fields.Date.to_date(). inventory.receipt._normalize_ai_invoice_date()
    is the backend safety net these tests cover, both directly and
    through the actual action_extract_ai() entry point.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.Receipt = cls.env["inventory.receipt"]

    def _make_ai_receipt(self):
        receipt = self.Receipt.create(
            {"receipt_type": "ai_smart", "warehouse_id": self.warehouse.id}
        )
        receipt.source_file = base64.b64encode(b"%PDF-fake-content")
        receipt.source_filename = "invoice.pdf"
        return receipt

    @staticmethod
    def _fake_extract(invoice_date_value):
        """Builds a fake extract_invoice() replacement returning one line
        and the given (unnormalized) invoice_date, so each test can drive
        action_extract_ai() through its real code path without a network
        call — matching mock pattern already used for the rest of this
        feature."""

        def _fake(file_bytes, mimetype, api_key, model):
            return (
                {
                    "supplier": "Acme Distributors",
                    "invoice_number": "INV-%s" % invoice_date_value,
                    "invoice_date": invoice_date_value,
                    "lines": [
                        {
                            "product_name": "Some Product",
                            "upc": None,
                            "quantity": 1,
                            "unit_price": 1.0,
                        }
                    ],
                },
                '{"mock": "raw response"}',
            )

        return _fake

    # ------------------------------------------------------------
    # Unit tests — _normalize_ai_invoice_date() directly
    # ------------------------------------------------------------

    def test_normalize_iso_format(self):
        self.assertEqual(
            self.Receipt._normalize_ai_invoice_date("2026-07-07"), date(2026, 7, 7)
        )

    def test_normalize_single_digit_slash_format(self):
        # The exact format from the reported bug: M/D/YYYY.
        self.assertEqual(
            self.Receipt._normalize_ai_invoice_date("7/7/2026"), date(2026, 7, 7)
        )

    def test_normalize_zero_padded_slash_format(self):
        self.assertEqual(
            self.Receipt._normalize_ai_invoice_date("07/07/2026"), date(2026, 7, 7)
        )

    def test_normalize_single_digit_dash_format(self):
        self.assertEqual(
            self.Receipt._normalize_ai_invoice_date("7-7-2026"), date(2026, 7, 7)
        )

    def test_normalize_zero_padded_dash_format(self):
        self.assertEqual(
            self.Receipt._normalize_ai_invoice_date("07-07-2026"), date(2026, 7, 7)
        )

    def test_normalize_invalid_date_raises_user_error(self):
        with self.assertRaises(UserError):
            self.Receipt._normalize_ai_invoice_date("not-a-real-date")

    # ------------------------------------------------------------
    # Integration — through action_extract_ai(), reproducing the actual
    # reported bug and its required behavior.
    # ------------------------------------------------------------

    def test_extract_ai_accepts_slash_date_from_real_gemini_response(self):
        """Reproduces the exact reported bug: a real Gemini call returned
        invoice_date='7/7/2026', which used to crash with an unhandled
        ValueError. Must now succeed and store the normalized date."""
        receipt = self._make_ai_receipt()
        with patch(
            "odoo.addons.inventory_management_poc.models.receipt.extract_invoice",
            self._fake_extract("7/7/2026"),
        ):
            receipt.action_extract_ai()
        self.assertEqual(receipt.state, "review")
        self.assertEqual(receipt.invoice_date, date(2026, 7, 7))

    def test_extract_ai_invalid_date_raises_user_error_with_no_partial_state(self):
        """An unparseable date must surface as a clear UserError (never a
        raw ValueError/RPC error) and must leave the receipt exactly as
        every other extraction failure does: Draft, no lines, no fields
        written — not a half-created record."""
        receipt = self._make_ai_receipt()
        with patch(
            "odoo.addons.inventory_management_poc.models.receipt.extract_invoice",
            self._fake_extract("13/45/2026"),
        ):
            with self.assertRaises(UserError):
                receipt.action_extract_ai()
        self.assertEqual(receipt.state, "draft")
        self.assertFalse(receipt.line_ids)
        self.assertFalse(receipt.supplier)
        self.assertFalse(receipt.invoice_date)
