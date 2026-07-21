import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { INVENTORY_TAB_GROUPS } from "./inventory_tabs_config";

/** Underlined horizontal tab strip shown below the breadcrumb on list views
 * whose action context declares `inventory_tab_group`. See
 * inventory_tabs_config.js for the tab definitions. */
export class InventoryTabStrip extends Component {
    static template = "inventory_management_poc.InventoryTabStrip";
    static props = {
        group: String,
        activeKey: { type: String, optional: true },
    };

    setup() {
        this.actionService = useService("action");
    }

    get tabs() {
        return INVENTORY_TAB_GROUPS[this.props.group] || [];
    }

    onTabClick(tab) {
        if (tab.key === this.props.activeKey) {
            return;
        }
        this.actionService.doAction(tab.action, { clearBreadcrumbs: true });
    }
}
