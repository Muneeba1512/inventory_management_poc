from odoo import fields, models


class InventoryProductCreateWizard(models.TransientModel):
    """Creates a new product for a scanned barcode that matched nothing
    (F3 — "if not, the system offers to create the product"), or for an
    AI Smart Receiving line whose match_status is 'new' (F4) — same
    wizard, same action, reused for both entry points."""

    _name = "inventory.product.create.wizard"
    _description = "Create Product from Scanned Barcode"

    barcode = fields.Char(
        string="Barcode",
        readonly=True,
        # Not required: an AI-extracted "new" line may have no UPC printed
        # on the invoice at all. The barcode-scan flow always has one
        # (that's how this wizard gets triggered in that case), so nothing
        # changes for it.
    )
    name = fields.Char(string="Product Name", required=True)
    receipt_id = fields.Many2one("inventory.receipt", string="Receipt", required=True)
    line_id = fields.Many2one(
        "inventory.receipt.line",
        string="Receipt Line",
        help="Set only when opened from an AI Smart Receiving review line — "
        "the created product is linked onto this existing line instead of "
        "a new one being created (the barcode-scan flow leaves this blank).",
    )

    def action_create_and_add(self):
        self.ensure_one()

        product = self.env["product.product"].create(
            {
                "name": self.name,
                "barcode": self.barcode or False,
                "type": "consu",
                "is_storable": True,
            }
        )

        if self.line_id:
            self.line_id.write({"product_id": product.id})
        else:
            self.receipt_id.receipt_type = "barcode"
            self.env["inventory.receipt.line"].create(
                {
                    "receipt_id": self.receipt_id.id,
                    "product_id": product.id,
                    "quantity": 1,
                }
            )

        return {"type": "ir.actions.act_window_close"}
