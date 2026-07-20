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
    # Constraints
    # ==========================================================

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("Quantity must be greater than zero.")
