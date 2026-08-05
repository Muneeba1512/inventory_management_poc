from datetime import timedelta

from odoo import api, fields, models


class InventoryLowStockAlert(models.Model):
    """Warehouse and store low-stock alerts (FDD F7, TDD §7, Decisions 6/7/8).

    One persistent row per (product, location) — never duplicated. The
    daily cron (and any manual "Run Manually" trigger) recomputes every
    watched location with the same routine and flips each row's status
    between active / resolved / not_enough_data, which is what gives the
    auto-resolve behaviour: the row just changes state, nothing new to
    clean up.
    """

    _name = "inventory.low.stock.alert"
    _description = "Low Stock Alert"
    _rec_name = "product_id"
    _order = "status, days_of_cover"

    # Fixed thresholds (Decision 8) — deliberately not configurable.
    CONSUMPTION_WINDOW = 7
    THRESHOLD_DAYS = 10

    product_id = fields.Many2one("product.product", string="Product", required=True, readonly=True)
    location_id = fields.Many2one("stock.location", string="Location", required=True, readonly=True)
    warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse", readonly=True)
    scope = fields.Selection(
        [("warehouse", "Warehouse"), ("store", "Store")],
        string="Scope",
        required=True,
        readonly=True,
    )
    store_id = fields.Many2one(
        "inventory.store",
        string="Store",
        readonly=True,
        help="Set only for store-scoped alerts.",
    )
    current_qty = fields.Float(string="On Hand", readonly=True)
    avg_daily_consumption = fields.Float(string="Avg / Day", readonly=True)
    days_of_cover = fields.Float(
        string="Days of Cover",
        readonly=True,
        help="Blank when there is not enough consumption history to project.",
    )
    status = fields.Selection(
        [
            ("active", "Active"),
            ("resolved", "Resolved"),
            ("not_enough_data", "Not Enough Data"),
        ],
        string="Status",
        required=True,
        readonly=True,
    )
    last_computed = fields.Datetime(string="Last Computed", readonly=True)

    _uniq_product_location = models.Constraint(
        "unique(product_id, location_id)",
        "Only one alert record is kept per product and location.",
    )

    # ==========================================================
    # Computation (TDD §7 — same routine for warehouse and store)
    # ==========================================================

    @api.model
    def _get_watched_locations(self):
        """Returns [(location, scope, store_or_False), ...] — the
        warehouse's own stock location plus every store's location."""
        warehouse = self.env["stock.warehouse"].search([], limit=1)
        watched = []
        if warehouse:
            watched.append((warehouse.lot_stock_id, "warehouse", False, warehouse))
        for store in self.env["inventory.store"].search([]):
            watched.append((store.stock_location_id, "store", store, warehouse))
        return watched

    @api.model
    def _compute_alerts(self):
        """Recompute every watched location. Safe to call as often as
        needed (cron, or manually) — always upserts, never duplicates."""
        Quant = self.env["stock.quant"].sudo()
        Move = self.env["stock.move"].sudo()
        window_start = fields.Datetime.now() - timedelta(days=self.CONSUMPTION_WINDOW)

        for location, scope, store, warehouse in self._get_watched_locations():
            quants = Quant.search([("location_id", "=", location.id)])
            moves = Move.search(
                [
                    ("location_id", "=", location.id),
                    ("state", "=", "done"),
                    ("date", ">=", window_start),
                ]
            )
            products = quants.product_id | moves.product_id

            for product in products:
                product_moves = moves.filtered(lambda m, p=product: m.product_id == p)
                outflow_7d = sum(product_moves.mapped("product_qty"))
                avg_per_day = outflow_7d / self.CONSUMPTION_WINDOW

                current_qty = Quant._get_available_quantity(product, location)

                vals = {
                    "product_id": product.id,
                    "location_id": location.id,
                    "warehouse_id": warehouse.id if warehouse else False,
                    "scope": scope,
                    "store_id": store.id if store else False,
                    "current_qty": current_qty,
                    "last_computed": fields.Datetime.now(),
                }

                if avg_per_day == 0:
                    vals.update(
                        {"avg_daily_consumption": 0.0, "days_of_cover": 0.0, "status": "not_enough_data"}
                    )
                else:
                    days_of_cover = current_qty / avg_per_day
                    vals.update(
                        {
                            "avg_daily_consumption": avg_per_day,
                            "days_of_cover": days_of_cover,
                            "status": "active" if days_of_cover < self.THRESHOLD_DAYS else "resolved",
                        }
                    )

                existing = self.sudo().search(
                    [("product_id", "=", product.id), ("location_id", "=", location.id)], limit=1
                )
                if existing:
                    existing.write(vals)
                else:
                    self.sudo().create(vals)

        return True
