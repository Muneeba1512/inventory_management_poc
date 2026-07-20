from odoo import api, fields, models
from odoo.exceptions import UserError


class InventoryStoreRequest(models.Model):
    _name = "inventory.store.request"
    _description = "Store Stock Request"
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
        help="Automatically generated unique request reference.",
    )

    store_id = fields.Many2one(
        "inventory.store",
        string="Store",
        required=True,
        default=lambda self: self.env["inventory.store"].search(
            [("store_manager_id", "=", self.env.uid)], limit=1
        ),
        tracking=True,
        help="The store requesting stock.",
    )

    requested_by = fields.Many2one(
        "res.users",
        string="Requested By",
        default=lambda self: self.env.user,
        readonly=True,
    )

    approver_id = fields.Many2one(
        "res.users",
        string="Approved / Rejected By",
        readonly=True,
        copy=False,
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("fulfilled", "Fulfilled"),
        ],
        string="Status",
        default="draft",
        copy=False,
        tracking=True,
    )

    reject_reason = fields.Text(
        string="Rejection Reason",
        readonly=True,
        copy=False,
    )

    picking_id = fields.Many2one(
        "stock.picking",
        string="Stock Transfer",
        readonly=True,
        copy=False,
        help="The internal transfer generated when this request was fulfilled.",
    )

    line_ids = fields.One2many(
        "inventory.store.request.line",
        "request_id",
        string="Lines",
    )

    line_count = fields.Integer(string="Items", compute="_compute_line_count")

    has_short_lines = fields.Boolean(
        string="Has Short Lines",
        compute="_compute_has_short_lines",
        help="True when at least one line requests more than is currently "
        "available at the warehouse — this request cannot be fulfilled and "
        "must be rejected instead (Decision 5, no partial fulfillment).",
    )

    # ==========================================================
    # Compute
    # ==========================================================

    @api.depends("line_ids")
    def _compute_line_count(self):
        for request in self:
            request.line_count = len(request.line_ids)

    @api.depends("line_ids.qty_requested", "line_ids.qty_available")
    def _compute_has_short_lines(self):
        for request in self:
            request.has_short_lines = any(
                line.qty_requested > line.qty_available for line in request.line_ids
            )

    # ==========================================================
    # Create
    # ==========================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("inventory.store.request")
                    or "New"
                )
        return super().create(vals_list)

    # ==========================================================
    # Workflow
    # ==========================================================

    def action_submit(self):
        for request in self:
            if request.state != "draft":
                raise UserError("Only draft requests can be submitted.")
            if not request.line_ids:
                raise UserError("Add at least one line before submitting.")
            request.state = "submitted"

    def _check_can_decide(self):
        if not (
            self.env.user.has_group("inventory_management_poc.group_inventory_warehouse")
            or self.env.user.has_group("inventory_management_poc.group_inventory_admin")
        ):
            raise UserError(
                "Only Warehouse Staff or Administrators can approve, reject or fulfill requests."
            )

    def action_approve(self):
        self._check_can_decide()
        for request in self:
            if request.state != "submitted":
                raise UserError("Only submitted requests can be approved.")
            request.write({"state": "approved", "approver_id": self.env.uid})

    def action_open_reject_wizard(self):
        self.ensure_one()
        self._check_can_decide()
        if self.state not in ("submitted", "approved"):
            raise UserError("Only submitted or approved requests can be rejected.")
        return {
            "type": "ir.actions.act_window",
            "name": "Reject Request",
            "res_model": "inventory.store.request.reject.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_request_id": self.id},
        }

    def action_reject(self, reason):
        self._check_can_decide()
        for request in self:
            if request.state not in ("submitted", "approved"):
                raise UserError("Only submitted or approved requests can be rejected.")
            if not reason or not reason.strip():
                raise UserError("A rejection reason is required.")
            request.write(
                {
                    "state": "rejected",
                    "approver_id": self.env.uid,
                    "reject_reason": reason,
                }
            )

    def action_fulfill(self):
        self._check_can_decide()
        for request in self:
            if request.state != "approved":
                raise UserError("Only approved requests can be fulfilled.")

            short_lines = request.line_ids.filtered(
                lambda line: line.qty_requested > line.qty_available
            )
            if short_lines:
                names = ", ".join(short_lines.mapped("product_id.display_name"))
                raise UserError(
                    "Cannot fulfill: insufficient warehouse stock for: %s. "
                    "This request must be rejected instead (no partial fulfillment)."
                    % names
                )

            picking = request._create_stock_picking()
            request.write({"picking_id": picking.id, "state": "fulfilled"})

    def _create_stock_picking(self):
        """Create and validate an internal transfer from the warehouse to this
        request's store. Runs as sudo — see receipt.py for the same rationale
        (TDD §1.1: native stock models are backend-only)."""
        self.ensure_one()
        warehouse = self.env["stock.warehouse"].search([], limit=1)
        picking_type = warehouse.int_type_id
        if not picking_type:
            raise UserError(
                "The warehouse has no internal transfer operation type configured."
            )

        picking = (
            self.env["stock.picking"]
            .sudo()
            .create(
                {
                    "picking_type_id": picking_type.id,
                    "location_id": warehouse.lot_stock_id.id,
                    "location_dest_id": self.store_id.stock_location_id.id,
                    "origin": self.name,
                    "move_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": line.product_id.id,
                                "product_uom_qty": line.qty_requested,
                                "product_uom": line.product_id.uom_id.id,
                                "location_id": warehouse.lot_stock_id.id,
                                "location_dest_id": self.store_id.stock_location_id.id,
                            },
                        )
                        for line in self.line_ids
                    ],
                }
            )
        )

        picking.button_validate()

        return picking

    # ==========================================================
    # Delete Guard
    # ==========================================================

    def unlink(self):
        for request in self:
            if request.state != "draft":
                raise UserError("Only draft requests can be deleted.")
        return super().unlink()
