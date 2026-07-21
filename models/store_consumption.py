from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


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

    product_summary = fields.Char(
        string="Product",
        compute="_compute_product_summary",
        help="Display-only summary of the products on this consumption "
        "entry, for the list view. Not a real relation — a consumption "
        "record can cover several products.",
    )

    total_quantity = fields.Float(
        string="Quantity",
        compute="_compute_total_quantity",
        help="Display-only sum of all line quantities, for the list view.",
    )

    # ==========================================================
    # Compute (display-only — no effect on the confirm workflow)
    # ==========================================================

    @api.depends("line_ids.product_id")
    def _compute_product_summary(self):
        for consumption in self:
            names = consumption.line_ids.mapped("product_id.display_name")
            if not names:
                consumption.product_summary = ""
            elif len(names) == 1:
                consumption.product_summary = names[0]
            else:
                consumption.product_summary = "%s (+%d more)" % (
                    names[0],
                    len(names) - 1,
                )

    @api.depends("line_ids.quantity")
    def _compute_total_quantity(self):
        for consumption in self:
            consumption.total_quantity = sum(consumption.line_ids.mapped("quantity"))

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
            consumption._check_stock_availability()
            consumption._create_stock_moves()
            consumption.state = "done"

    def _check_stock_availability(self):
        """Block confirmation if any product's total quantity on this
        consumption exceeds what is currently available at the store
        location — prevents negative inventory through this workflow."""
        self.ensure_one()
        requested_by_product = {}
        for line in self.line_ids:
            requested_by_product[line.product_id] = (
                requested_by_product.get(line.product_id, 0.0) + line.quantity
            )

        for product, requested_qty in requested_by_product.items():
            available_qty = self.env["stock.quant"]._get_available_quantity(
                product, self.store_id.stock_location_id
            )
            if requested_qty > available_qty:
                raise ValidationError(
                    "Cannot confirm: requested quantity for '%s' (%s) exceeds "
                    "the available stock at %s (%s available)."
                    % (
                        product.display_name,
                        requested_qty,
                        self.store_id.name,
                        available_qty,
                    )
                )

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
