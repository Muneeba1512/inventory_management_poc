import { patch } from "@web/core/utils/patch";
import { ListController } from "@web/views/list/list_controller";
import { InventoryTabStrip } from "./inventory_tab_strip";

patch(ListController, {
    components: { ...ListController.components, InventoryTabStrip },
});

patch(ListController.prototype, {
    get inventoryTabGroup() {
        return this.props.context && this.props.context.inventory_tab_group;
    },
    get inventoryTabKey() {
        return this.props.context && this.props.context.inventory_tab_key;
    },
    get inventoryInfoBanner() {
        return this.props.context && this.props.context.inventory_info_banner;
    },
});
