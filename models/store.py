from odoo import api, fields, models


class InventoryStore(models.Model):
    _name = "inventory.store"
    _description = "Inventory Store"
    _rec_name = "name"
    _order = "name"

    # ==========================================================
    # Basic Information
    # ==========================================================

    name = fields.Char(
        string="Store Name",
        required=True,
        help="Enter the name of the store.",
    )

    store_code = fields.Char(
        string="Store Code",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: "New",
        help="Automatically generated unique store code.",
    )

    # ==========================================================
    # Relationships
    # ==========================================================

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        required=True,
        readonly=True,
    )

    store_manager_id = fields.Many2one(
        "res.users",
        string="Store Manager",
        help="User responsible for managing this store.",
    )

    stock_location_id = fields.Many2one(
        "stock.location",
        string="Stock Location",
        domain="[('usage', '=', 'internal')]",
        required=True,
        help="Internal stock location assigned to this store.",
    )

    # ==========================================================
    # Additional Information
    # ==========================================================

    remarks = fields.Text(
        string="Remarks",
    )

    active = fields.Boolean(
        string="Active",
        default=True,
    )

    # ==========================================================
    # SQL Constraints
    # ==========================================================

    _sql_constraints = [
        (
            "unique_store_code",
            "unique(store_code)",
            "Store Code must be unique.",
        ),
    ]

    # ==========================================================
    # Create
    # ==========================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("store_code", "New") == "New":
                vals["store_code"] = (
                    self.env["ir.sequence"].next_by_code("inventory.store") or "New"
                )

        return super().create(vals_list)
