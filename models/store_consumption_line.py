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

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("Quantity must be greater than zero.")
