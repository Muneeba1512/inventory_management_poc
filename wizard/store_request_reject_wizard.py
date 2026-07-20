from odoo import fields, models


class InventoryStoreRequestRejectWizard(models.TransientModel):
    """Captures the mandatory rejection reason (Decision 5) before an
    inventory.store.request moves to the 'rejected' state."""

    _name = "inventory.store.request.reject.wizard"
    _description = "Reject Store Request"

    request_id = fields.Many2one(
        "inventory.store.request", string="Request", required=True
    )
    reason = fields.Text(string="Rejection Reason", required=True)

    def action_confirm_reject(self):
        self.ensure_one()
        self.request_id.action_reject(self.reason)
        return {"type": "ir.actions.act_window_close"}
