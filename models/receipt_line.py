from odoo import api, fields, models
from odoo.exceptions import ValidationError


class InventoryReceiptLine(models.Model):
    _name = "inventory.receipt.line"
    _description = "Inventory Receipt Line"
    _rec_name = "product_id"

    # ==========================================================
    # Relationships
    # ==========================================================

    receipt_id = fields.Many2one(
        "inventory.receipt",
        string="Receipt",
        required=True,
        ondelete="cascade",
    )

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        # Not required at the model level: an AI Smart Receiving line can
        # exist mid-review with no product yet (match_status 'new' or
        # 'uncertain'). Manual and barcode receipts always set this
        # immediately in their own flows, so nothing changes for them.
        # action_confirm() enforces that no line reaches Done without a
        # product, for every receipt type.
        required=False,
    )

    # ==========================================================
    # Quantity (Decision 2 — single base unit, no conversions)
    # ==========================================================

    quantity = fields.Float(
        string="Quantity",
        required=True,
        default=1.0,
        help="Quantity received, in the product's base unit.",
    )

    uom_id = fields.Many2one(
        related="product_id.uom_id",
        string="Unit",
        readonly=True,
    )

    receipt_state = fields.Selection(
        related="receipt_id.state",
        string="Receipt Status",
        store=True,
    )

    # ==========================================================
    # Financials — reuses the product's existing cost
    # (standard_price), calculated dynamically, nothing duplicated.
    # ==========================================================

    unit_cost = fields.Monetary(
        string="Unit Cost",
        compute="_compute_financials",
        currency_field="currency_id",
    )
    line_total = fields.Monetary(
        string="Line Total",
        compute="_compute_financials",
        currency_field="currency_id",
        help="Quantity x Unit Cost.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        compute="_compute_currency_id",
    )

    @api.depends("quantity", "product_id.standard_price")
    def _compute_financials(self):
        for line in self:
            line.unit_cost = line.product_id.standard_price
            line.line_total = line.quantity * line.product_id.standard_price

    @api.depends_context("company")
    def _compute_currency_id(self):
        currency = self.env.company.currency_id
        for line in self:
            line.currency_id = currency

    # ==========================================================
    # AI Smart Receiving (F4, Decisions 2/4) — populated only for
    # receipt_type == 'ai_smart' lines; left blank/default for manual
    # and barcode lines.
    # ==========================================================

    upc = fields.Char(
        string="Extracted UPC",
        help="UPC exactly as read from the invoice by Gemini — kept "
        "separate from the matched product's own barcode so a mismatch "
        "stays visible instead of being silently overwritten.",
    )
    raw_product_name = fields.Char(
        string="Extracted Name",
        help="Product name exactly as read from the invoice by Gemini — "
        "preserved even after matching to an existing product.",
    )
    unit_price = fields.Monetary(
        string="Unit Price",
        currency_field="currency_id",
        help="Supplier's invoice price for this line, as extracted (Decision "
        "4). History only — never written to the product's standard cost.",
    )
    match_status = fields.Selection(
        [
            ("upc", "Matched by UPC"),
            ("name", "Matched by Name"),
            ("uncertain", "Uncertain — Select Product"),
            ("new", "New"),
        ],
        string="Match",
        copy=False,
        help="Set by the deterministic matching engine when an AI Smart "
        "Receiving line is created — Gemini never chooses the product "
        "itself. Blank for manual/barcode lines.",
    )
    candidate_product_ids = fields.Many2many(
        "product.product",
        string="Candidate Products",
        help="Populated only for 'uncertain' lines — the set of products "
        "the name matched, restricting the product picker to a safe choice.",
    )

    # ==========================================================
    # Constraints
    # ==========================================================

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("Quantity must be greater than zero.")

    # ==========================================================
    # AI Smart Receiving — "New" product creation. Reuses the same
    # wizard the barcode-scan flow already uses (inventory.product.
    # create.wizard); passing this line's id links the product it
    # creates back onto this line instead of creating a new one.
    # ==========================================================

    def action_open_create_product_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Create Product",
            "res_model": "inventory.product.create.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_barcode": self.upc,
                "default_name": self.raw_product_name,
                "default_receipt_id": self.receipt_id.id,
                "default_line_id": self.id,
            },
        }
