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
        required=True,
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
    # Constraints
    # ==========================================================

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("Quantity must be greater than zero.")
