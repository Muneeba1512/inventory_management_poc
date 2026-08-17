from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    inventory_gemini_api_key = fields.Char(
        string="Gemini API Key",
        config_parameter="inventory_management_poc.gemini_api_key",
        help="Used by AI Smart Receiving to read uploaded invoices. "
        "Stored server-side only, never sent to the browser.",
    )

    inventory_gemini_model = fields.Char(
        string="Gemini Model",
        config_parameter="inventory_management_poc.gemini_model",
        default="gemini-2.5-flash",
        help="Fixed to Gemini 2.5 Flash per the project's confirmed design; "
        "editable here only in case a future model name replaces it.",
    )
