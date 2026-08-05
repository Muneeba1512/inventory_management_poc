/**
 * Static configuration for the Inventory Management app's custom tab strip.
 *
 * Each key is a "tab group" (set via the `inventory_tab_group` key on an
 * action's context); its value is the ordered list of sibling tabs shown
 * for any screen tagged with that group. Clicking a tab navigates to the
 * given action (by external id) via the action service.
 */
export const INVENTORY_TAB_GROUPS = {
    warehouse: [
        {
            key: "receipts",
            label: "Receipts",
            action: "inventory_management_poc.action_inventory_receipt",
        },
        {
            key: "stock_by_location",
            label: "Stock by Location",
            action: "inventory_management_poc.action_inventory_stock_by_location",
        },
    ],
    requests: [
        {
            key: "to_approve",
            label: "To Approve",
            action: "inventory_management_poc.action_inventory_store_request_to_approve",
        },
        {
            key: "to_fulfill",
            label: "To Fulfill",
            action: "inventory_management_poc.action_inventory_store_request_to_fulfill",
        },
        {
            key: "my_requests",
            label: "My Requests",
            action: "inventory_management_poc.action_inventory_store_request_my_requests",
        },
    ],
    stores: [
        {
            key: "manage_stores",
            label: "Manage Stores",
            action: "inventory_management_poc.action_inventory_store",
        },
        {
            key: "record_consumption",
            label: "Record Consumption",
            action: "inventory_management_poc.action_inventory_store_consumption",
        },
        {
            key: "my_store_stock",
            label: "My Store Stock",
            action: "inventory_management_poc.action_inventory_my_store_stock",
        },
    ],
    alerts: [
        {
            key: "warehouse_alerts",
            label: "Warehouse Alerts",
            action: "inventory_management_poc.action_inventory_low_stock_alert_warehouse",
        },
        {
            key: "store_alerts",
            label: "Store Alerts",
            action: "inventory_management_poc.action_inventory_low_stock_alert_store",
        },
    ],
};
