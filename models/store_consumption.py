from odoo import api, fields, models
from odoo.exceptions import UserError


class InventoryStoreConsumption(models.Model):
    _name = "inventory.store.consumption"
    _description = "Store Stock Consumption"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"
    _order = "id desc"

    # ==========================================================
    # Basic Information
    # ==========================================================

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: "New",
        help="Automatically generated unique consumption reference.",
    )

    store_id = fields.Many2one(
        "inventory.store",
        string="Store",
        required=True,
        default=lambda self: self.env["inventory.store"].search(
            [("store_manager_id", "=", self.env.uid)], limit=1
        ),
        tracking=True,
    )

    date = fields.Date(
        string="Date",
        required=True,
        default=fields.Date.context_today,
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("done", "Done"),
        ],
        string="Status",
        default="draft",
        copy=False,
        tracking=True,
        help="Draft records can still be edited; Done records are permanent history.",
    )

    line_ids = fields.One2many(
        "inventory.store.consumption.line",
        "consumption_id",
        string="Lines",
    )

    # ==========================================================
    # Create
    # ==========================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("inventory.store.consumption")
                    or "New"
                )
        return super().create(vals_list)

    # ==========================================================
    # Confirm — lowers store stock (Decision 1, feeds 7-day history)
    # ==========================================================

    def action_confirm(self):
        for consumption in self:
            if consumption.state != "draft":
                raise UserError("Only draft consumption records can be confirmed.")
            if not consumption.line_ids:
                raise UserError("Add at least one line before confirming.")
            consumption._create_stock_moves()
            consumption.state = "done"

    def _create_stock_moves(self):
        """Move stock from the store location to the generic Customers location,
        as standalone moves (no natural picking type applies to a store's own
        usage/sale of stock). Runs as sudo — see receipt.py for the same
        rationale (TDD §1.1: native stock models are backend-only)."""
        self.ensure_one()
        customer_location = self.env.ref("stock.stock_location_customers")

        moves = (
            self.env["stock.move"]
            .sudo()
            .create(
                [
                    {
                        "product_id": line.product_id.id,
                        "product_uom_qty": line.quantity,
                        "product_uom": line.product_id.uom_id.id,
                        "location_id": self.store_id.stock_location_id.id,
                        "location_dest_id": customer_location.id,
                        "origin": self.name,
                    }
                    for line in self.line_ids
                ]
            )
        )

        for move in moves:
            move.quantity = move.product_uom_qty
            move.picked = True
        moves._action_done()

        return moves

    # ==========================================================
    # Delete Guard — permanent history once confirmed
    # ==========================================================

    def unlink(self):
        for consumption in self:
            if consumption.state == "done":
                raise UserError(
                    "Confirmed consumption records are permanent history and cannot be deleted."
                )
        return super().unlink()
