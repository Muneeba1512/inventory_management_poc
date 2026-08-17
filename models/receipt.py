import base64
import mimetypes
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.gemini_service import GeminiExtractionError, extract_invoice

# Files accepted for AI Smart Receiving (FDD F4 — "PDF or image").
ALLOWED_AI_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

# Invoice date formats accepted from Gemini's extraction, tried in order.
# Gemini is instructed to return YYYY-MM-DD (see services/gemini_service.py),
# but that instruction is not a guarantee — %m/%d/%Y and %m-%d-%Y each
# already match BOTH the single-digit (M/D/YYYY, M-D-YYYY) and zero-padded
# (MM/DD/YYYY, MM-DD-YYYY) variants, since strptime's %m/%d don't require
# zero-padding.
AI_INVOICE_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y")


class InventoryReceipt(models.Model):
    _name = "inventory.receipt"
    _description = "Inventory Receipt"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "id desc"

    # ==========================================================
    # Basic Information
    # ==========================================================

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: "New",
        help="Automatically generated unique receipt reference.",
    )

    receipt_type = fields.Selection(
        [
            ("manual", "Manual"),
            ("barcode", "Barcode / QR"),
            ("ai_smart", "AI Smart Receiving"),
        ],
        string="Receiving Method",
        required=True,
        default="manual",
        tracking=True,
        help="How this receipt's lines were added.",
    )

    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse",
        required=True,
        default=lambda self: self.env["stock.warehouse"].search([], limit=1),
        help="Warehouse receiving the stock.",
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("review", "Review"),
            ("done", "Done"),
        ],
        string="Status",
        default="draft",
        copy=False,
        tracking=True,
        help="Draft receipts can still be edited; Done receipts are permanent "
        "history. 'Review' is only ever used by AI Smart Receiving, between "
        "extraction and confirmation — manual and barcode receipts go "
        "straight from Draft to Done.",
    )

    line_ids = fields.One2many(
        "inventory.receipt.line",
        "receipt_id",
        string="Lines",
    )

    picking_id = fields.Many2one(
        "stock.picking",
        string="Stock Transfer",
        readonly=True,
        copy=False,
        help="The internal stock transfer generated when this receipt was confirmed.",
    )

    # ==========================================================
    # Barcode Scan (not stored on confirm — used only to add lines)
    # ==========================================================

    scan_barcode = fields.Char(
        string="Scan Barcode",
        help="Scan or type a product barcode to add a line.",
    )

    # ==========================================================
    # AI Smart Receiving (F4) — header fields extracted from the
    # uploaded invoice. Only meaningful when receipt_type == 'ai_smart';
    # left blank for manual/barcode receipts.
    # ==========================================================

    source_file = fields.Binary(
        string="Source File",
        attachment=True,
        help="The uploaded invoice or receipt (PDF, JPG or PNG) read by Gemini.",
    )
    source_filename = fields.Char(string="Source Filename")

    supplier = fields.Char(
        string="Supplier",
        tracking=True,
        help="Supplier name as extracted from the invoice (Decision 3 — "
        "used with Invoice Number for the duplicate check). Plain text for "
        "this POC — not matched against res.partner.",
    )
    invoice_number = fields.Char(string="Invoice Number", tracking=True)
    invoice_date = fields.Date(string="Invoice Date")

    ai_raw_response = fields.Text(
        string="AI Raw Response",
        readonly=True,
        copy=False,
        help="Full Gemini response for the last successful extraction, kept "
        "for troubleshooting extraction quality. Not shown on the normal form.",
    )

    # ==========================================================
    # Create
    # ==========================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("inventory.receipt") or "New"
                )
        return super().create(vals_list)

    # ==========================================================
    # Barcode Scan Handling (Decision 9 — barcode/QR carry the UPC only)
    # ==========================================================

    def action_scan_barcode(self):
        self.ensure_one()
        barcode = (self.scan_barcode or "").strip()
        if not barcode:
            return False

        product = self.env["product.product"].search(
            [("barcode", "=", barcode)], limit=1
        )

        if not product:
            return {
                "type": "ir.actions.act_window",
                "name": "Create Product",
                "res_model": "inventory.product.create.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_barcode": barcode,
                    "default_receipt_id": self.id,
                },
            }

        self.receipt_type = "barcode"
        existing_line = self.line_ids.filtered(lambda l: l.product_id == product)
        if existing_line:
            existing_line[0].quantity += 1
        else:
            self.env["inventory.receipt.line"].create(
                {
                    "receipt_id": self.id,
                    "product_id": product.id,
                    "quantity": 1,
                }
            )

        self.scan_barcode = False
        return True

    # ==========================================================
    # AI Smart Receiving — extraction (F4). Gemini's only job is to read
    # the document; it never decides which Odoo product a line matches
    # (see _match_ai_product below) — that stays deterministic and local.
    # ==========================================================

    def action_extract_ai(self):
        self.ensure_one()
        if self.receipt_type != "ai_smart":
            raise UserError("Extraction is only available for AI Smart Receiving.")
        if self.state != "draft":
            raise UserError("Extraction can only be run once, while the receipt is in Draft.")
        if not self.source_file:
            raise UserError("Upload an invoice or receipt file first.")

        filename = self.source_filename or ""
        extension = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
        if extension not in ALLOWED_AI_EXTENSIONS:
            raise UserError(
                "Unsupported file type. Upload a PDF, JPG or PNG invoice/receipt."
            )
        mimetype = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        ICP = self.env["ir.config_parameter"].sudo()
        api_key = ICP.get_param("inventory_management_poc.gemini_api_key")
        model = ICP.get_param("inventory_management_poc.gemini_model") or "gemini-2.5-flash"

        try:
            data, raw_response = extract_invoice(
                base64.b64decode(self.source_file), mimetype, api_key, model
            )
        except GeminiExtractionError as exc:
            raise UserError(str(exc)) from exc

        supplier = (data.get("supplier") or "").strip()
        invoice_number = (data.get("invoice_number") or "").strip()

        self._check_duplicate_invoice(supplier, invoice_number)

        vals = {
            "supplier": supplier,
            "invoice_number": invoice_number,
            "ai_raw_response": raw_response,
            "state": "review",
        }
        invoice_date = (data.get("invoice_date") or "").strip()
        if invoice_date:
            vals["invoice_date"] = self._normalize_ai_invoice_date(invoice_date)
        self.write(vals)

        Line = self.env["inventory.receipt.line"]
        for line_data in data.get("lines", []):
            raw_name = (line_data.get("product_name") or "").strip()
            upc = (line_data.get("upc") or "").strip() or False
            product, match_status, candidates = self._match_ai_product(raw_name, upc)
            Line.create(
                {
                    "receipt_id": self.id,
                    "product_id": product.id if product else False,
                    "upc": upc,
                    "raw_product_name": raw_name,
                    "quantity": line_data.get("quantity") or 0.0,
                    "unit_price": line_data.get("unit_price") or 0.0,
                    "match_status": match_status,
                    "candidate_product_ids": [(6, 0, candidates.ids)],
                }
            )

    def _check_duplicate_invoice(self, supplier, invoice_number):
        """Decision 3 — Supplier + Invoice Number, blocked before any line
        is created or any stock is touched. Application-level check (not a
        DB constraint): normalizes both values the same way, and only ever
        applies to receipts that actually have both fields populated
        (manual/barcode receipts never do, so they're never affected)."""
        if not supplier or not invoice_number:
            raise UserError(
                "Gemini could not read both a supplier and an invoice number "
                "from this document — cannot check for duplicates, so nothing "
                "was processed."
            )
        duplicate = self.env["inventory.receipt"].search(
            [
                ("id", "!=", self.id),
                ("supplier", "=ilike", supplier),
                ("invoice_number", "=ilike", invoice_number),
            ],
            limit=1,
        )
        if duplicate:
            raise UserError(
                "This invoice has already been received (%s). Duplicate "
                "invoices are blocked — no changes were made." % duplicate.name
            )

    @api.model
    def _normalize_ai_invoice_date(self, raw_value):
        """Converts Gemini's extracted invoice_date text into a date Odoo
        can store, tolerating the formats it has actually been observed to
        return (not just the YYYY-MM-DD it's instructed to use — see
        AI_INVOICE_DATE_FORMATS above). `fields.Date.to_date()` only
        accepts YYYY-MM-DD and raises a raw ValueError on anything else,
        which previously reached the user as an unhandled RPC error; this
        tries every supported format first and raises a clear UserError
        only if none of them match, so a bad date is reported the same
        way every other extraction failure is (no partial state)."""
        for date_format in AI_INVOICE_DATE_FORMATS:
            try:
                return datetime.strptime(raw_value, date_format).date()
            except ValueError:
                continue
        raise UserError(
            "Gemini returned an invoice date ('%s') that could not be "
            "read. Supported formats: YYYY-MM-DD, M/D/YYYY, MM/DD/YYYY, "
            "M-D-YYYY, MM-DD-YYYY. Nothing was processed — review the "
            "document and try Extract with AI again." % raw_value
        )

    @api.model
    def _match_ai_product(self, name, upc):
        """Deterministic matching, run entirely in Odoo — Gemini never
        sees or influences this. Returns (product_or_empty, match_status,
        candidate_products_or_empty).

        Order (as specified): UPC exact -> name exact/case-insensitive ->
        ilike near-match fallback -> one candidate = matched by name,
        several = uncertain (user must pick), none = new.
        """
        Product = self.env["product.product"]
        empty = Product.browse()

        if upc:
            match = Product.search([("barcode", "=", upc)], limit=1)
            if match:
                return match, "upc", empty

        if name:
            exact = Product.search([("name", "=ilike", name)])
            if len(exact) == 1:
                return exact, "name", empty
            if len(exact) > 1:
                return empty, "uncertain", exact

            near = Product.search([("name", "ilike", name)], limit=10)
            if len(near) == 1:
                return near, "name", empty
            if len(near) > 1:
                return empty, "uncertain", near

        return empty, "new", empty

    # ==========================================================
    # Confirm — creates the real stock transfer (TDD §4)
    # ==========================================================

    def action_confirm(self):
        for receipt in self:
            is_ai = receipt.receipt_type == "ai_smart"
            expected_state = "review" if is_ai else "draft"
            if receipt.state != expected_state:
                raise UserError(
                    "Only receipts in Review can be confirmed."
                    if is_ai
                    else "Only draft receipts can be confirmed."
                )
            if not receipt.line_ids:
                raise UserError("Add at least one line before confirming.")
            if is_ai:
                # match_status is kept as a permanent audit label (e.g. a
                # line stays "Uncertain" even after the user resolves it
                # by picking a candidate), so the only real precondition
                # is that every line ended up with a product — not that
                # match_status itself changed.
                unresolved = receipt.line_ids.filtered(lambda l: not l.product_id)
                if unresolved:
                    raise UserError(
                        "Every line must have a product before confirming. "
                        "Resolve any 'Uncertain' or unmatched lines first."
                    )

            picking = receipt._create_stock_picking()
            receipt.picking_id = picking.id
            receipt.state = "done"

    def _create_stock_picking(self):
        """Create and validate an incoming stock transfer for this receipt's
        lines. Runs as sudo: the security boundary for receiving stock is
        this model's own access rights, not the underlying native stock
        models (see TDD §1.1 — native stock models are backend-only)."""
        self.ensure_one()
        picking_type = self.warehouse_id.in_type_id
        if not picking_type:
            raise UserError(
                "The selected warehouse has no incoming operation type configured."
            )

        picking = (
            self.env["stock.picking"]
            .sudo()
            .create(
                {
                    "picking_type_id": picking_type.id,
                    "location_id": picking_type.default_location_src_id.id,
                    "location_dest_id": picking_type.default_location_dest_id.id,
                    "origin": self.name,
                    "move_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": line.product_id.id,
                                "product_uom_qty": line.quantity,
                                "product_uom": line.product_id.uom_id.id,
                                "location_id": picking_type.default_location_src_id.id,
                                "location_dest_id": picking_type.default_location_dest_id.id,
                            },
                        )
                        for line in self.line_ids
                    ],
                }
            )
        )

        picking.button_validate()

        return picking

    # ==========================================================
    # Delete Guard — receipts are permanent history (Decision 11)
    # ==========================================================

    def unlink(self):
        for receipt in self:
            if receipt.state == "done":
                raise UserError(
                    "Confirmed receipts are permanent history and cannot be deleted."
                )
        return super().unlink()
