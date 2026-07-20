from odoo import fields, models


class InventoryProductCreateWizard(models.TransientModel):
    """Creates a new product for a scanned barcode that matched nothing
    (F3 — "if not, the system offers to create the product")."""

    _name = "inventory.product.create.wizard"
    _description = "Create Product from Scanned Barcode"

    barcode = fields.Char(string="Barcode", required=True, readonly=True)
    name = fields.Char(string="Product Name", required=True)
    receipt_id = fields.Many2one("inventory.receipt", string="Receipt", required=True)

    def action_create_and_add(self):
        self.ensure_one()

        product = self.env["product.product"].create(
            {
                "name": self.name,
                "barcode": self.barcode,
                "type": "consu",
                "is_storable": True,
            }
        )

        self.receipt_id.receipt_type = "barcode"
        self.env["inventory.receipt.line"].create(
            {
                "receipt_id": self.receipt_id.id,
                "product_id": product.id,
                "quantity": 1,
            }
        )

        return {"type": "ir.actions.act_window_close"}
