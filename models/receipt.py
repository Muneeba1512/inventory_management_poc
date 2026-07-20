from odoo import api, fields, models
from odoo.exceptions import UserError


class InventoryReceipt(models.Model):
    _name = "inventory.receipt"
    _description = "Inventory Receipt"
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
        help="Automatically generated unique receipt reference.",
    )

    receipt_type = fields.Selection(
        [
            ("manual", "Manual"),
            ("barcode", "Barcode / QR"),
        ],
        string="Receiving Method",
        required=True,
        default="manual",
        tracking=True,
        help="How this receipt's lines were added.",
    )

    warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Warehouse",
        required=True,
        default=lambda self: self.env["stock.warehouse"].search([], limit=1),
        help="Warehouse receiving the stock.",
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
        help="Draft receipts can still be edited; Done receipts are permanent history.",
    )

    line_ids = fields.One2many(
        "inventory.receipt.line",
        "receipt_id",
        string="Lines",
    )

    picking_id = fields.Many2one(
        "stock.picking",
        string="Stock Transfer",
        readonly=True,
        copy=False,
        help="The internal stock transfer generated when this receipt was confirmed.",
    )

    # ==========================================================
    # Barcode Scan (not stored on confirm — used only to add lines)
    # ==========================================================

    scan_barcode = fields.Char(
        string="Scan Barcode",
        help="Scan or type a product barcode to add a line.",
    )

    # ==========================================================
    # Create
    # ==========================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"].next_by_code("inventory.receipt") or "New"
                )
        return super().create(vals_list)

    # ==========================================================
    # Barcode Scan Handling (Decision 9 — barcode/QR carry the UPC only)
    # ==========================================================

    def action_scan_barcode(self):
        self.ensure_one()
        barcode = (self.scan_barcode or "").strip()
        if not barcode:
            return False

        product = self.env["product.product"].search(
            [("barcode", "=", barcode)], limit=1
        )

        if not product:
            return {
                "type": "ir.actions.act_window",
                "name": "Create Product",
                "res_model": "inventory.product.create.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_barcode": barcode,
                    "default_receipt_id": self.id,
                },
            }

        self.receipt_type = "barcode"
        existing_line = self.line_ids.filtered(lambda l: l.product_id == product)
        if existing_line:
            existing_line[0].quantity += 1
        else:
            self.env["inventory.receipt.line"].create(
                {
                    "receipt_id": self.id,
                    "product_id": product.id,
                    "quantity": 1,
                }
            )

        self.scan_barcode = False
        return True

    # ==========================================================
    # Confirm — creates the real stock transfer (TDD §4)
    # ==========================================================

    def action_confirm(self):
        for receipt in self:
            if receipt.state != "draft":
                raise UserError("Only draft receipts can be confirmed.")
            if not receipt.line_ids:
                raise UserError("Add at least one line before confirming.")

            picking = receipt._create_stock_picking()
            receipt.picking_id = picking.id
            receipt.state = "done"

    def _create_stock_picking(self):
        """Create and validate an incoming stock transfer for this receipt's
        lines. Runs as sudo: the security boundary for receiving stock is
        this model's own access rights, not the underlying native stock
        models (see TDD §1.1 — native stock models are backend-only)."""
        self.ensure_one()
        picking_type = self.warehouse_id.in_type_id
        if not picking_type:
            raise UserError(
                "The selected warehouse has no incoming operation type configured."
            )

        picking = (
            self.env["stock.picking"]
            .sudo()
            .create(
                {
                    "picking_type_id": picking_type.id,
                    "location_id": picking_type.default_location_src_id.id,
                    "location_dest_id": picking_type.default_location_dest_id.id,
                    "origin": self.name,
                    "move_ids": [
                        (
                            0,
                            0,
                            {
                                "product_id": line.product_id.id,
                                "product_uom_qty": line.quantity,
                                "product_uom": line.product_id.uom_id.id,
                                "location_id": picking_type.default_location_src_id.id,
                                "location_dest_id": picking_type.default_location_dest_id.id,
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
    # Delete Guard — receipts are permanent history (Decision 11)
    # ==========================================================

    def unlink(self):
        for receipt in self:
            if receipt.state == "done":
                raise UserError(
                    "Confirmed receipts are permanent history and cannot be deleted."
                )
        return super().unlink()
