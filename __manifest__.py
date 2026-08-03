{
    "name": "Inventory Management POC",
    "version": "19.0.1.0.0",
    "summary": "Inventory Management System",
    "description": """
Inventory Management POC
""",
    "author": "Muneeba",
    "website": "",
    "category": "Inventory",
    "license": "LGPL-3",

    "depends": [
        "stock",
        "mail",
    ],

    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "security/record_rules.xml",

        "data/sequence.xml",

        "views/store_views.xml",
        "views/receipt_views.xml",
        "wizard/product_create_wizard_views.xml",
        "views/stock_by_location_views.xml",
        "views/store_request_views.xml",
        "wizard/store_request_reject_wizard_views.xml",
        "views/store_consumption_views.xml",
        "views/menu_views.xml",
    ],

    "assets": {
        "web.assets_backend": [
            "inventory_management_poc/static/src/scss/inventory_tab_strip.scss",
            "inventory_management_poc/static/src/js/tab_strip/inventory_tabs_config.js",
            "inventory_management_poc/static/src/js/tab_strip/inventory_tab_strip.js",
            "inventory_management_poc/static/src/js/tab_strip/inventory_tab_strip.xml",
            "inventory_management_poc/static/src/js/tab_strip/list_controller_patch.js",
            "inventory_management_poc/static/src/js/tab_strip/list_view_patch.xml",
            "inventory_management_poc/static/src/js/tab_strip/breadcrumb_name_patch.xml",
            "inventory_management_poc/static/src/js/placeholder/coming_soon_action.js",
            "inventory_management_poc/static/src/js/placeholder/coming_soon_action.xml",
        ],
    },

    "application": True,
    "installable": True,
    "auto_install": False,
}