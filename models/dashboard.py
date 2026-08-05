from datetime import datetime, time, timedelta

from odoo import api, fields, models


class InventoryDashboard(models.AbstractModel):
    """Backend data for the ERP-style Dashboard.

    Holds no data of its own. Security is enforced HERE, not just in the
    UI: role and store are resolved from self.env.user with an explicit
    precedence (Admin/Warehouse Staff > Store Manager > no recognized
    role), and a Store Manager's store is always looked up server-side
    from inventory.store.store_manager_id — any store_id the client
    sends is only honored for Admin/Warehouse Staff. Every underlying
    query additionally runs through the normal ORM as the current user,
    so the existing record rules apply as a second, independent layer.
    """

    _name = "inventory.dashboard"
    _description = "Inventory Dashboard Data"

    # Heatmap sub-threshold: half of the fixed 10-day cover threshold.
    CRITICAL_COVER_DAYS = 5

    # ==========================================================
    # Role / store / period resolution
    # ==========================================================

    def _resolve_role_and_store(self, store_id):
        """Returns (role, store). role is 'admin_wh' or 'store_manager'.
        store is the inventory.store recordset to filter by — empty for
        admin_wh means "no filter, all stores"; empty for store_manager
        means "this user has no store assigned", which every helper
        below treats as "return nothing" rather than "return everything".
        """
        user = self.env.user
        is_admin_or_warehouse = user.has_group(
            "inventory_management_poc.group_inventory_admin"
        ) or user.has_group("inventory_management_poc.group_inventory_warehouse")

        if is_admin_or_warehouse:
            store = self.env["inventory.store"].browse(store_id).exists() if store_id else self.env["inventory.store"]
            return "admin_wh", store

        if user.has_group("inventory_management_poc.group_inventory_store"):
            store = self.env["inventory.store"].search([("store_manager_id", "=", user.id)], limit=1)
            return "store_manager", store

        # No recognized role at all: safest default scopes everything to
        # an empty store, so every store-filtered query below returns
        # nothing rather than silently falling back to "all data".
        return "store_manager", self.env["inventory.store"]

    def _resolve_period(self, date_range, date_from, date_to):
        today = fields.Date.context_today(self)
        if date_range == "today":
            start, end = today, today
        elif date_range == "7days":
            start, end = today - timedelta(days=6), today
        elif date_range == "custom" and date_from and date_to:
            start = fields.Date.from_string(date_from)
            end = fields.Date.from_string(date_to)
        else:
            date_range = "30days"
            start, end = today - timedelta(days=29), today

        length = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=length - 1)
        return date_range, start, end, prev_start, prev_end

    # ==========================================================
    # Entry point
    # ==========================================================

    @api.model
    def get_dashboard_data(self, date_range="30days", store_id=None, date_from=None, date_to=None):
        role, store = self._resolve_role_and_store(store_id)
        date_range, start, end, prev_start, prev_end = self._resolve_period(date_range, date_from, date_to)

        kpis = (
            self._kpis_store_manager(store, date_range, start, end, prev_start, prev_end)
            if role == "store_manager"
            else self._kpis_admin(store, date_range, start, end, prev_start, prev_end)
        )

        return {
            "role": role,
            "store_id": store.id if store else None,
            "store_name": store.name if store else None,
            "currency_id": self.env.company.currency_id.id,
            "date_range": date_range,
            "period_start": fields.Date.to_string(start),
            "period_end": fields.Date.to_string(end),
            "kpis": kpis,
            "trend": self._get_trend(role, store, start, end),
            "donut": [] if role == "store_manager" else self._get_donut(store),
            "heatmap": self._get_heatmap(role, store),
            "requests_panel": self._get_requests_panel(role, store),
            "alerts_panel": self._get_alerts_panel(role, store),
            "activity": self._get_activity(role, store),
            "stores": [] if role == "store_manager" else self._get_store_options(),
        }

    # ==========================================================
    # Small helpers shared by both KPI sets
    # ==========================================================

    def _kpi(self, key, label, sublabel, value, value_format, delta=None, health=None, action=None):
        return {
            "key": key,
            "label": label,
            "sublabel": sublabel,
            "value": value,
            "format": value_format,
            "delta": delta,
            "health": health,
            "action": action,
        }

    def _delta(self, current, previous):
        """None when there is nothing honest to compare against yet —
        never fabricated (matches the "no backfill/approximation"
        decision applied consistently to every metric, not just the
        trend chart)."""
        if previous in (None, 0):
            return None
        change = (current - previous) / previous * 100.0
        return {"pct": round(change, 1), "direction": "up" if change >= 0 else "down"}

    def _action(self, xmlid):
        """A KPI's click-through target — always a reference to an action
        that already exists (backing one of the app's own menus/tabs),
        never a fabricated inline act_window. The client resolves this
        the same way clicking that menu/tab would: through the action's
        own view_mode, search view, domain and context, so role-based
        record rules and tab-strip context apply exactly as they do
        when reached by hand."""
        return {"xmlid": xmlid}

    def _period_label(self, date_range):
        return {
            "today": "Today",
            "7days": "Last 7 days",
            "30days": "Last 30 days",
            "custom": "Selected range",
        }.get(date_range, "Last 30 days")

    def _datetime_bounds(self, start, end):
        return (
            fields.Datetime.to_string(datetime.combine(start, time.min)),
            fields.Datetime.to_string(datetime.combine(end, time.max)),
        )

    def _on_hand_value(self, store):
        domain = [("store_id", "=", store.id)] if store else []
        rows = self.env["inventory.stock.by.location"].search(domain)
        return sum(row.quantity * row.product_id.standard_price for row in rows)

    def _value_as_of(self, store, as_of_date):
        """Latest snapshot on/before as_of_date, per watched location,
        summed. None when no snapshot exists yet at all (fresh system —
        the delta is simply not shown, per the "no backfill" decision)."""
        domain = [("date", "<=", as_of_date)]
        if store:
            domain.append(("store_id", "=", store.id))
        rows = self.env["inventory.value.snapshot"].search(domain, order="date desc")
        seen = set()
        total = 0.0
        for row in rows:
            if row.location_id.id in seen:
                continue
            seen.add(row.location_id.id)
            total += row.value
        return total if seen else None

    def _receipt_count(self, start, end):
        dt_start, dt_end = self._datetime_bounds(start, end)
        return self.env["inventory.receipt"].search_count(
            [("state", "=", "done"), ("create_date", ">=", dt_start), ("create_date", "<=", dt_end)]
        )

    def _consumption_lines(self, store, start, end):
        domain = [
            ("consumption_id.state", "=", "done"),
            ("consumption_id.date", ">=", start),
            ("consumption_id.date", "<=", end),
        ]
        if store:
            domain.append(("consumption_id.store_id", "=", store.id))
        return self.env["inventory.store.consumption.line"].search(domain)

    def _consumption_qty(self, store, start, end):
        return sum(self._consumption_lines(store, start, end).mapped("quantity"))

    def _consumption_value(self, store, start, end):
        return sum(
            line.quantity * line.product_id.standard_price
            for line in self._consumption_lines(store, start, end)
        )

    def _avg_on_hand_value(self, store, start, end, fallback):
        domain = [("date", ">=", start), ("date", "<=", end)]
        if store:
            domain.append(("store_id", "=", store.id))
        rows = self.env["inventory.value.snapshot"].search(domain)
        if not rows:
            return fallback
        by_date = {}
        for row in rows:
            by_date.setdefault(row.date, 0.0)
            by_date[row.date] += row.value
        return sum(by_date.values()) / len(by_date)

    # ==========================================================
    # Admin / Warehouse Staff — 8 KPI cards
    # ==========================================================

    def _kpis_admin(self, store, date_range, start, end, prev_start, prev_end):
        Alert = self.env["inventory.low.stock.alert"]
        StoreRequest = self.env["inventory.store.request"]
        period_label = self._period_label(date_range)

        on_hand_value = self._on_hand_value(store)
        value_delta = self._delta(
            self._value_as_of(store, end) or on_hand_value,
            self._value_as_of(store, prev_end),
        )

        open_requests_domain = [("state", "in", ("submitted", "approved"))]
        if store:
            open_requests_domain.append(("store_id", "=", store.id))
        open_requests = StoreRequest.search_count(open_requests_domain)

        warehouse_alerts = Alert.search_count([("scope", "=", "warehouse"), ("status", "=", "active")])

        store_alerts_domain = [("scope", "=", "store"), ("status", "=", "active")]
        if store:
            store_alerts_domain.append(("store_id", "=", store.id))
        store_alerts = Alert.search_count(store_alerts_domain)

        receipts_count = self._receipt_count(start, end)
        receipts_prev = self._receipt_count(prev_start, prev_end)

        consumption_qty = self._consumption_qty(store, start, end)
        consumption_prev = self._consumption_qty(store, prev_start, prev_end)

        consumption_value = self._consumption_value(store, start, end)
        avg_on_hand = self._avg_on_hand_value(store, start, end, fallback=on_hand_value)
        turnover = (consumption_value / avg_on_hand) if avg_on_hand else 0.0
        consumption_value_prev = self._consumption_value(store, prev_start, prev_end)
        avg_on_hand_prev = self._avg_on_hand_value(store, prev_start, prev_end, fallback=None)
        turnover_prev = (
            (consumption_value_prev / avg_on_hand_prev) if avg_on_hand_prev else None
        )

        low_stock_domain = [("status", "=", "active")]
        if store:
            low_stock_domain.append(("store_id", "=", store.id))
        low_stock_products = len(Alert.search(low_stock_domain).product_id)

        return [
            self._kpi(
                "on_hand_value",
                "On-Hand Inventory Value",
                "Warehouse + all stores" if not store else store.name,
                on_hand_value,
                "currency",
                delta=value_delta,
                action=self._action("inventory_management_poc.action_inventory_stock_by_location"),
            ),
            self._kpi(
                "open_requests",
                "Open Store Requests",
                "Submitted or approved",
                open_requests,
                "number",
                action=self._action("inventory_management_poc.action_inventory_store_request_to_approve"),
            ),
            self._kpi(
                "warehouse_alerts",
                "Warehouse Alerts",
                "Active, warehouse scope",
                warehouse_alerts,
                "number",
                action=self._action("inventory_management_poc.action_inventory_low_stock_alert_warehouse"),
            ),
            self._kpi(
                "store_alerts",
                "Store Alerts",
                "Active, store scope" if not store else store.name,
                store_alerts,
                "number",
                action=self._action("inventory_management_poc.action_inventory_low_stock_alert_store"),
            ),
            self._kpi(
                "receipts",
                "Receipts",
                period_label,
                receipts_count,
                "number",
                delta=self._delta(receipts_count, receipts_prev),
                action=self._action("inventory_management_poc.action_inventory_receipt"),
            ),
            self._kpi(
                "consumption",
                "Consumption",
                period_label,
                consumption_qty,
                "qty",
                delta=self._delta(consumption_qty, consumption_prev),
                action=self._action("inventory_management_poc.action_inventory_store_consumption"),
            ),
            self._kpi(
                "turnover",
                "Inventory Turnover",
                period_label,
                round(turnover, 2),
                "ratio",
                delta=self._delta(turnover, turnover_prev),
                action=self._action("inventory_management_poc.action_inventory_stock_by_location"),
            ),
            self._kpi(
                "low_stock_products",
                "Low Stock Products",
                "Distinct products, active alert",
                low_stock_products,
                "number",
                action=self._action("inventory_management_poc.action_inventory_low_stock_alert_warehouse"),
            ),
        ]

    # ==========================================================
    # Store Manager — 5 KPI cards (own store only, server-enforced)
    # ==========================================================

    def _kpis_store_manager(self, store, date_range, start, end, prev_start, prev_end):
        Alert = self.env["inventory.low.stock.alert"]
        period_label = self._period_label(date_range)

        on_hand_value = self._on_hand_value(store) if store else 0.0
        value_delta = (
            self._delta(self._value_as_of(store, end) or on_hand_value, self._value_as_of(store, prev_end))
            if store
            else None
        )

        open_requests = 0
        if store:
            open_requests = self.env["inventory.store.request"].search_count(
                [("store_id", "=", store.id), ("state", "in", ("submitted", "approved"))]
            )

        store_alerts = 0
        if store:
            store_alerts = Alert.search_count(
                [("scope", "=", "store"), ("status", "=", "active"), ("store_id", "=", store.id)]
            )

        received_count = 0
        if store:
            dt_start, dt_end = self._datetime_bounds(start, end)
            received_count = self.env["inventory.store.request"].search_count(
                [
                    ("store_id", "=", store.id),
                    ("state", "=", "fulfilled"),
                    ("write_date", ">=", dt_start),
                    ("write_date", "<=", dt_end),
                ]
            )

        consumption_qty = self._consumption_qty(store, start, end) if store else 0.0
        consumption_prev = self._consumption_qty(store, prev_start, prev_end) if store else 0.0

        return [
            self._kpi(
                "on_hand_value",
                "On-Hand Value",
                store.name if store else "No store assigned",
                on_hand_value,
                "currency",
                delta=value_delta,
                action=self._action("inventory_management_poc.action_inventory_my_store_stock"),
            ),
            self._kpi(
                "open_requests",
                "Open Requests",
                "Submitted or approved",
                open_requests,
                "number",
                action=self._action("inventory_management_poc.action_inventory_store_request_my_requests"),
            ),
            self._kpi(
                "store_alerts",
                "Store Alerts",
                "Active",
                store_alerts,
                "number",
                action=self._action("inventory_management_poc.action_inventory_low_stock_alert_store"),
            ),
            self._kpi(
                "received",
                "Received Stock",
                period_label,
                received_count,
                "number",
                action=self._action("inventory_management_poc.action_inventory_store_request_my_requests"),
            ),
            self._kpi(
                "consumption",
                "Consumption",
                period_label,
                consumption_qty,
                "qty",
                delta=self._delta(consumption_qty, consumption_prev),
                action=self._action("inventory_management_poc.action_inventory_store_consumption"),
            ),
        ]

    # ==========================================================
    # Trend / donut / heatmap / panels / activity
    # ==========================================================

    def _get_trend(self, role, store, start, end):
        if role == "store_manager" and not store:
            return []
        domain = [("date", ">=", start), ("date", "<=", end)]
        if store:
            domain.append(("store_id", "=", store.id))
        rows = self.env["inventory.value.snapshot"].search(domain, order="date")
        by_date = {}
        for row in rows:
            by_date.setdefault(row.date, 0.0)
            by_date[row.date] += row.value
        return [{"date": fields.Date.to_string(d), "value": v} for d, v in sorted(by_date.items())]

    def _get_donut(self, store):
        domain = [("store_id", "=", store.id)] if store else []
        rows = self.env["inventory.stock.by.location"].search(domain)
        by_location = {}
        for row in rows:
            label = row.location_id.display_name
            by_location.setdefault(label, 0.0)
            by_location[label] += row.quantity * row.product_id.standard_price
        return [
            {"label": label, "value": value}
            for label, value in sorted(by_location.items(), key=lambda item: -item[1])
        ]

    def _get_heatmap(self, role, store):
        if role == "store_manager" and not store:
            return []
        watched = self.env["inventory.low.stock.alert"]._get_watched_locations()
        if store:
            watched = [w for w in watched if w[2] and w[2].id == store.id]

        Alert = self.env["inventory.low.stock.alert"]
        result = []
        for location, scope, watched_store, warehouse in watched:
            alerts = Alert.search([("location_id", "=", location.id)])
            level = "healthy"
            min_cover = None
            for alert in alerts:
                if alert.status == "active":
                    if alert.days_of_cover < self.CRITICAL_COVER_DAYS:
                        level = "critical"
                    elif level != "critical":
                        level = "warning"
                    if min_cover is None or alert.days_of_cover < min_cover:
                        min_cover = alert.days_of_cover
            result.append(
                {
                    "location": location.display_name,
                    "scope": scope,
                    "level": level,
                    "days_of_cover": min_cover,
                }
            )
        return result

    def _get_requests_panel(self, role, store):
        if role == "store_manager" and not store:
            return {"pending_approval": [], "pending_fulfillment": [], "recently_rejected": []}

        base = [("store_id", "=", store.id)] if store else []

        def rows(extra, limit=10):
            recs = self.env["inventory.store.request"].search(base + extra, order="write_date desc", limit=limit)
            return [
                {
                    "id": rec.id,
                    "name": rec.name,
                    "store": rec.store_id.name,
                    "state": rec.state,
                    "date": fields.Datetime.to_string(rec.write_date),
                }
                for rec in recs
            ]

        return {
            "pending_approval": rows([("state", "=", "submitted")]),
            "pending_fulfillment": rows([("state", "=", "approved")]),
            "recently_rejected": rows([("state", "=", "rejected")]),
        }

    def _get_alerts_panel(self, role, store, limit=10):
        if role == "store_manager" and not store:
            return []
        domain = [("status", "=", "active")]
        if store:
            domain.append(("store_id", "=", store.id))
        # Sorted most-urgent-first; status='active' already excludes
        # not_enough_data entirely (it is never counted active).
        alerts = self.env["inventory.low.stock.alert"].search(domain, order="days_of_cover", limit=limit)
        return [
            {
                "id": alert.id,
                "product": alert.product_id.display_name,
                "location": alert.location_id.display_name,
                "days_of_cover": alert.days_of_cover,
                "status": alert.status,
                "scope": alert.scope,
            }
            for alert in alerts
        ]

    def _get_activity(self, role, store, limit=15):
        if role == "store_manager" and not store:
            return []

        events = []

        # Receiving is warehouse-only (Store Manager has no access to
        # inventory.receipt at all — reading it here for that role would
        # raise an AccessError, not just leak data), so only include it
        # in the admin/warehouse-staff feed.
        if role != "store_manager":
            for receipt in self.env["inventory.receipt"].search([("state", "=", "done")], order="write_date desc", limit=limit):
                events.append(
                    {"type": "receipt", "text": "Receipt %s confirmed" % receipt.name, "date": fields.Datetime.to_string(receipt.write_date)}
                )

        req_domain = ([("store_id", "=", store.id)] if store else []) + [("state", "in", ("approved", "fulfilled", "rejected"))]
        for req in self.env["inventory.store.request"].search(req_domain, order="write_date desc", limit=limit):
            events.append(
                {"type": "request", "text": "Request %s %s" % (req.name, req.state), "date": fields.Datetime.to_string(req.write_date)}
            )

        cons_domain = ([("store_id", "=", store.id)] if store else []) + [("state", "=", "done")]
        for consumption in self.env["inventory.store.consumption"].search(cons_domain, order="write_date desc", limit=limit):
            events.append(
                {
                    "type": "consumption",
                    "text": "Consumption %s recorded at %s" % (consumption.name, consumption.store_id.name),
                    "date": fields.Datetime.to_string(consumption.write_date),
                }
            )

        alert_domain = ([("store_id", "=", store.id)] if store else []) + [("status", "=", "active")]
        for alert in self.env["inventory.low.stock.alert"].search(alert_domain, order="last_computed desc", limit=limit):
            if not alert.last_computed:
                continue
            events.append(
                {
                    "type": "alert",
                    "text": "Alert: %s low at %s" % (alert.product_id.display_name, alert.location_id.display_name),
                    "date": fields.Datetime.to_string(alert.last_computed),
                }
            )

        events.sort(key=lambda event: event["date"], reverse=True)
        return events[:limit]

    def _get_store_options(self):
        return [{"id": store.id, "name": store.name} for store in self.env["inventory.store"].search([])]
