import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { formatCurrency } from "@web/core/currency";
import { loadBundle } from "@web/core/assets";

// Okabe-Ito colorblind-safe categorical palette, reused for the donut so
// slices stay distinguishable without relying on color alone (each slice
// also carries a text legend entry with its value).
const DONUT_COLORS = [
    "#0072B2",
    "#E69F00",
    "#009E73",
    "#CC79A7",
    "#56B4E9",
    "#D55E00",
    "#F0E442",
    "#999999",
];

const HEATMAP_META = {
    critical: { icon: "🔴", label: "Critical" },
    warning: { icon: "🟡", label: "Warning" },
    healthy: { icon: "🟢", label: "Healthy" },
};

// Presentation-only: icon + accent color per KPI card, keyed by the same
// `kpi.key` the server already returns. Purely cosmetic — does not affect
// what data is fetched or what a card navigates to.
const KPI_META = {
    on_hand_value: { icon: "fa-money", color: "primary" },
    open_requests: { icon: "fa-inbox", color: "info" },
    warehouse_alerts: { icon: "fa-exclamation-triangle", color: "danger" },
    store_alerts: { icon: "fa-exclamation-triangle", color: "danger" },
    receipts: { icon: "fa-truck", color: "success" },
    consumption: { icon: "fa-shopping-basket", color: "warning" },
    turnover: { icon: "fa-refresh", color: "primary" },
    low_stock_products: { icon: "fa-cubes", color: "danger" },
    received: { icon: "fa-truck", color: "success" },
};
const DEFAULT_KPI_META = { icon: "fa-bar-chart", color: "secondary" };

const ACTIVITY_META = {
    receipt: { icon: "fa-truck", color: "success" },
    request: { icon: "fa-inbox", color: "info" },
    consumption: { icon: "fa-shopping-basket", color: "warning" },
    alert: { icon: "fa-exclamation-triangle", color: "danger" },
};
const DEFAULT_ACTIVITY_META = { icon: "fa-circle", color: "secondary" };

/** ERP-style Dashboard (role-scoped server-side by get_dashboard_data —
 * this component never enforces security itself, it only reflects
 * whatever the server decided to return for the current user). */
export class InventoryDashboard extends Component {
    static template = "inventory_management_poc.Dashboard";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        this.trendCanvasRef = useRef("trendCanvas");
        this.donutCanvasRef = useRef("donutCanvas");
        this.trendChart = null;
        this.donutChart = null;

        this.state = useState({
            data: null,
            dateRange: "30days",
            customFrom: "",
            customTo: "",
            storeId: null,
        });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.fetchData();
        });

        useEffect(
            () => {
                this.renderTrendChart();
                this.renderDonutChart();
            },
            () => [this.state.data, this.trendCanvasRef.el, this.donutCanvasRef.el]
        );
    }

    async fetchData() {
        this.state.data = await this.orm.call("inventory.dashboard", "get_dashboard_data", [], {
            date_range: this.state.dateRange,
            store_id: this.state.storeId || null,
            date_from: this.state.dateRange === "custom" ? this.state.customFrom || null : null,
            date_to: this.state.dateRange === "custom" ? this.state.customTo || null : null,
        });
    }

    async onDateRangeChange(ev) {
        this.state.dateRange = ev.target.value;
        if (this.state.dateRange !== "custom") {
            await this.fetchData();
        }
    }

    async onCustomDateChange() {
        if (this.state.customFrom && this.state.customTo) {
            await this.fetchData();
        }
    }

    async onStoreChange(ev) {
        this.state.storeId = ev.target.value ? parseInt(ev.target.value, 10) : null;
        await this.fetchData();
    }

    // ==========================================================
    // Formatting
    // ==========================================================

    formatKpiValue(kpi) {
        const value = kpi.value || 0;
        if (kpi.format === "currency") {
            return formatCurrency(value, this.state.data && this.state.data.currency_id);
        }
        if (kpi.format === "ratio") {
            return `${value}x`;
        }
        if (kpi.format === "qty") {
            return new Intl.NumberFormat().format(value);
        }
        return new Intl.NumberFormat().format(value);
    }

    healthMeta(level) {
        return HEATMAP_META[level] || HEATMAP_META.healthy;
    }

    kpiMeta(kpi) {
        return KPI_META[kpi.key] || DEFAULT_KPI_META;
    }

    activityMeta(event) {
        return ACTIVITY_META[event.type] || DEFAULT_ACTIVITY_META;
    }

    formatEventDate(dateStr) {
        if (!dateStr) {
            return "";
        }
        // Server sends "YYYY-MM-DD HH:MM:SS" (UTC-naive Datetime string);
        // a light, dependency-free relative/short format for the feed.
        const date = new Date(dateStr.replace(" ", "T") + "Z");
        if (Number.isNaN(date.getTime())) {
            return dateStr;
        }
        return date.toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    // ==========================================================
    // Click-through
    // ==========================================================

    openKpi(kpi) {
        if (!kpi.action || !kpi.action.xmlid) {
            return;
        }
        // Navigate to the actual existing action behind the corresponding
        // menu/tab (same view_mode, search view, domain, context — record
        // rules and tab-strip context apply exactly as they do from the
        // menu) instead of fabricating a one-off act_window here.
        this.actionService.doAction(kpi.action.xmlid, { clearBreadcrumbs: true });
    }

    openAction(resModel, domain, name) {
        this.actionService.doAction(
            {
                type: "ir.actions.act_window",
                res_model: resModel,
                name,
                domain: domain || [],
                views: [
                    [false, "list"],
                    [false, "form"],
                ],
                target: "current",
            },
            { clearBreadcrumbs: true }
        );
    }

    openRequest(requestId) {
        this.actionService.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "inventory.store.request",
                res_id: requestId,
                views: [[false, "form"]],
                target: "current",
            },
            { clearBreadcrumbs: true }
        );
    }

    openAlertsForScope(scope) {
        this.openAction(
            "inventory.low.stock.alert",
            scope === "warehouse" ? [["scope", "=", "warehouse"]] : [["scope", "=", "store"]],
            scope === "warehouse" ? "Warehouse Alerts" : "Store Alerts"
        );
    }

    // ==========================================================
    // Charts
    // ==========================================================

    renderTrendChart() {
        if (this.trendChart) {
            this.trendChart.destroy();
            this.trendChart = null;
        }
        const canvas = this.trendCanvasRef.el;
        if (!canvas || !this.state.data) {
            return;
        }
        const trend = this.state.data.trend || [];
        // Reuse Odoo's own theme primary color (same one the "New" button
        // and active nav use) instead of a hardcoded hex.
        const primary = (getComputedStyle(canvas).getPropertyValue("--bs-primary") || "#0072B2").trim();
        // eslint-disable-next-line no-undef
        this.trendChart = new Chart(canvas.getContext("2d"), {
            type: "line",
            data: {
                labels: trend.map((point) => point.date),
                datasets: [
                    {
                        label: "On-Hand Value",
                        data: trend.map((point) => point.value),
                        borderColor: primary,
                        backgroundColor: primary + "1a",
                        borderWidth: 2,
                        pointRadius: trend.length > 1 ? 2 : 4,
                        pointBackgroundColor: primary,
                        fill: true,
                        tension: 0.3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, grid: { color: "rgba(0,0,0,0.06)" } },
                    x: { grid: { display: false } },
                },
            },
        });
    }

    renderDonutChart() {
        if (this.donutChart) {
            this.donutChart.destroy();
            this.donutChart = null;
        }
        const canvas = this.donutCanvasRef.el;
        if (!canvas || !this.state.data || this.state.data.role === "store_manager") {
            return;
        }
        const donut = this.state.data.donut || [];
        // eslint-disable-next-line no-undef
        this.donutChart = new Chart(canvas.getContext("2d"), {
            type: "doughnut",
            data: {
                labels: donut.map((slice) => slice.label),
                datasets: [
                    {
                        data: donut.map((slice) => slice.value),
                        backgroundColor: donut.map((slice, index) => DONUT_COLORS[index % DONUT_COLORS.length]),
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "right" } },
            },
        });
    }
}

registry.category("actions").add("inventory_management_poc.dashboard", InventoryDashboard);
