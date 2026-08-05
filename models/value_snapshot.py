from odoo import api, fields, models


class InventoryValueSnapshot(models.Model):
    """Daily on-hand value per watched location, feeding the Dashboard's
    Inventory Value Trend chart.

    Deliberately forward-only: populated once a day by the same cron
    cadence as the low-stock alert engine, starting from whenever this
    feature is installed. No backfilled or approximated history — the
    trend simply accumulates real data points as the system is used.
    """

    _name = "inventory.value.snapshot"
    _description = "Inventory Value Snapshot"
    _order = "date"

    date = fields.Date(required=True, readonly=True)
    location_id = fields.Many2one("stock.location", string="Location", required=True, readonly=True)
    warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse", readonly=True)
    scope = fields.Selection(
        [("warehouse", "Warehouse"), ("store", "Store")], required=True, readonly=True
    )
    store_id = fields.Many2one("inventory.store", string="Store", readonly=True)
    value = fields.Float(string="On-Hand Value", readonly=True)

    _uniq_date_location = models.Constraint(
        "unique(date, location_id)",
        "Only one snapshot is kept per location per day.",
    )

    @api.model
    def _compute_snapshot(self):
        """Same watched-location list as the alert engine (warehouse +
        every store) — reused rather than duplicated."""
        Quant = self.env["stock.quant"].sudo()
        Alert = self.env["inventory.low.stock.alert"]
        today = fields.Date.context_today(self)

        for location, scope, store, warehouse in Alert._get_watched_locations():
            quants = Quant.search([("location_id", "=", location.id)])
            value = sum(quant.quantity * quant.product_id.standard_price for quant in quants)

            vals = {
                "date": today,
                "location_id": location.id,
                "warehouse_id": warehouse.id if warehouse else False,
                "scope": scope,
                "store_id": store.id if store else False,
                "value": value,
            }
            existing = self.sudo().search(
                [("date", "=", today), ("location_id", "=", location.id)], limit=1
            )
            if existing:
                existing.write(vals)
            else:
                self.sudo().create(vals)
        return True
