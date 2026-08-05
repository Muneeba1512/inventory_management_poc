from odoo import api, fields, models, tools


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
    store_id = fields.Many2one(
        "inventory.store",
        string="Store",
        readonly=True,
        help="Set when this location is a store's stock location; blank for "
        "warehouse-only locations.",
    )
    quantity = fields.Float(string="On Hand", readonly=True)
    reserved_quantity = fields.Float(string="Reserved", readonly=True)
    uom_id = fields.Many2one(
        related="product_id.uom_id", string="Unit", readonly=True
    )
    days_of_cover = fields.Float(
        string="Days of Cover",
        compute="_compute_alert_info",
        help="From the low-stock alert engine (Sprint 3). Blank until the "
        "daily job has run at least once, or when there is not enough "
        "consumption history to project.",
    )
    alert_status = fields.Selection(
        [
            ("active", "Active"),
            ("resolved", "Resolved"),
            ("not_enough_data", "Not Enough Data"),
        ],
        string="Cover Status",
        compute="_compute_alert_info",
    )

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
                    ist.id AS store_id,
                    sq.quantity AS quantity,
                    sq.reserved_quantity AS reserved_quantity
                FROM stock_quant sq
                JOIN stock_location sl ON sl.id = sq.location_id
                LEFT JOIN inventory_store ist ON ist.stock_location_id = sq.location_id
                WHERE sl.usage = 'internal'
                  AND sq.quantity != 0
            )
            """
            % self._table
        )

    # Deliberately a Python compute, not part of the SQL view above: baking
    # a JOIN to inventory_low_stock_alert directly into the CREATE VIEW
    # statement would make this view's table-creation order depend on that
    # model's table already existing, which Odoo does not guarantee for
    # unrelated _auto=False models. A batched ORM lookup avoids that
    # fragility entirely.
    @api.depends("product_id", "location_id")
    def _compute_alert_info(self):
        alerts = self.env["inventory.low.stock.alert"].search(
            [
                ("product_id", "in", self.product_id.ids),
                ("location_id", "in", self.location_id.ids),
            ]
        )
        alert_by_key = {(a.product_id.id, a.location_id.id): a for a in alerts}
        for row in self:
            alert = alert_by_key.get((row.product_id.id, row.location_id.id))
            row.days_of_cover = alert.days_of_cover if alert else 0.0
            row.alert_status = alert.status if alert else False
