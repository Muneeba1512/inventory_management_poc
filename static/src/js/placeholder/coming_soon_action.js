import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

/** Minimal placeholder screen for menus whose feature ships in a later
 * sprint (Dashboard, Low Stock Alerts). Registered as a client action so
 * the menu carries a real action and is not silently hidden by Odoo's
 * menu-visibility rules — see ir.ui.menu._visible_menu_ids(), which never
 * shows an actionless, childless menu. Reused for both screens via the
 * action's own `params` (title/message), no duplicate component needed. */
export class InventoryComingSoon extends Component {
    static template = "inventory_management_poc.ComingSoon";
    // The action container / ControllerComponent always passes the full
    // standard action-service prop set (className, updateActionState,
    // state, globalState, resId, ...), not just action/actionId — OWL's
    // prop validator rejects anything undeclared, so all of them must be
    // listed here even though this component only reads `action`.
    static props = { ...standardActionServiceProps };

    get title() {
        return (this.props.action.params && this.props.action.params.title) || this.props.action.name;
    }

    get message() {
        return (
            (this.props.action.params && this.props.action.params.message) ||
            "This screen is planned for a future sprint."
        );
    }
}

registry.category("actions").add("inventory_management_poc.coming_soon", InventoryComingSoon);
