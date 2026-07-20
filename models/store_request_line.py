from odoo import api, fields, models
from odoo.exceptions import ValidationError


class InventoryStoreRequestLine(models.Model):
    _name = "inventory.store.request.line"
    _description = "Store Stock Request Line"
    _rec_name = "product_id"

    # ==========================================================
    # Relationships
    # ==========================================================

    request_id = fields.Many2one(
        "inventory.store.request",
        string="Request",
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

    qty_requested = fields.Float(
        string="Quantity Requested",
        required=True,
        default=1.0,
        help="Quantity requested, in the product's base unit.",
    )

    uom_id = fields.Many2one(
        related="product_id.uom_id",
        string="Unit",
        readonly=True,
    )

    qty_available = fields.Float(
        string="Available at Warehouse",
        compute="_compute_qty_available",
        help="Live on-hand quantity for this product at the warehouse.",
    )

    request_state = fields.Selection(
        related="request_id.state",
        string="Request Status",
        store=True,
    )

    # ==========================================================
    # Compute
    # ==========================================================

    @api.depends("product_id")
    def _compute_qty_available(self):
        warehouse = self.env["stock.warehouse"].search([], limit=1)
        for line in self:
            if line.product_id and warehouse:
                line.qty_available = self.env["stock.quant"]._get_available_quantity(
                    line.product_id, warehouse.lot_stock_id
                )
            else:
                line.qty_available = 0.0

    # ==========================================================
    # Constraints
    # ==========================================================

    @api.constrains("qty_requested")
    def _check_qty_requested(self):
        for line in self:
            if line.qty_requested <= 0:
                raise ValidationError("Requested quantity must be greater than zero.")
