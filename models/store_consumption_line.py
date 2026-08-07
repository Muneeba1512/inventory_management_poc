from odoo import api, fields, models
from odoo.exceptions import ValidationError


class InventoryStoreConsumptionLine(models.Model):
    _name = "inventory.store.consumption.line"
    _description = "Store Stock Consumption Line"
    _rec_name = "product_id"

    consumption_id = fields.Many2one(
        "inventory.store.consumption",
        string="Consumption",
        required=True,
        ondelete="cascade",
    )

    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
    )

    quantity = fields.Float(
        string="Quantity",
        required=True,
        default=1.0,
        help="Quantity consumed, in the product's base unit.",
    )

    uom_id = fields.Many2one(
        related="product_id.uom_id",
        string="Unit",
        readonly=True,
    )

    consumption_state = fields.Selection(
        related="consumption_id.state",
        string="Consumption Status",
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
    consumed_value = fields.Monetary(
        string="Consumed Value",
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
            line.consumed_value = line.quantity * line.product_id.standard_price

    @api.depends_context("company")
    def _compute_currency_id(self):
        currency = self.env.company.currency_id
        for line in self:
            line.currency_id = currency

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("Quantity must be greater than zero.")
