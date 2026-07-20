from odoo import fields, models, tools


class InventoryStockByLocation(models.Model):
    """Read-only presentation of on-hand stock per product and location.

    Backed by a SQL view over stock.quant so that the native stock models
    stay backend-only and invisible to end users (TDD §1.1), while still
    giving Warehouse Staff / Admin a screen to verify received stock.
    """

    _name = "inventory.stock.by.location"
    _description = "Stock by Location"
    _auto = False
    _order = "location_id, product_id"

    product_id = fields.Many2one("product.product", string="Product", readonly=True)
    location_id = fields.Many2one("stock.location", string="Location", readonly=True)
    warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse", readonly=True)
    quantity = fields.Float(string="On Hand", readonly=True)
    reserved_quantity = fields.Float(string="Reserved", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE VIEW %s AS (
                SELECT
                    sq.id AS id,
                    sq.product_id AS product_id,
                    sq.location_id AS location_id,
                    sl.warehouse_id AS warehouse_id,
                    sq.quantity AS quantity,
                    sq.reserved_quantity AS reserved_quantity
                FROM stock_quant sq
                JOIN stock_location sl ON sl.id = sq.location_id
                WHERE sl.usage = 'internal'
                  AND sq.quantity != 0
            )
            """
            % self._table
        )
