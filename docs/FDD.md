# Functional Design Document (FDD)
### Inventory Management System — Proof of Concept

**Platform:** Odoo 19 · PostgreSQL · Google Gemini 2.5 Flash
**Version:** 1.0 (Confirmed Business Rules)
**Status:** Ready for Sprint 0

---

## 1. Purpose

An Odoo 19 application to receive stock into a single warehouse in three ways
(manual, barcode/QR, and AI-assisted invoice reading), let multiple stores
request stock from the warehouse, and warn when either the warehouse or a store
is running low based on real consumption.

The design builds on Odoo's native Inventory (`stock`) module rather than
rebuilding inventory from scratch. This provides warehouses, locations, stock
levels, movements, transfers, products and barcodes out of the box — which is
what makes the POC genuinely deployable.

---

## 2. Users and Roles

Each user holds **exactly one** role (Decision 12).

| Role | What they can do |
|------|------------------|
| **Warehouse Staff** | Receive stock (all three ways), review AI results, approve / reject / fulfill store requests, perform inventory adjustments. |
| **Store Manager** | Tied to exactly one store. Sees only that store's stock, requests, consumption and alerts. Creates requests and records consumption. |
| **System Administrator** | Full access — warehouses, stores, users, settings, dashboards and reports. |

A Warehouse Staff user cannot also be a Store Manager. A Store Manager is
assigned to exactly one store.

---

## 3. Assumptions

- One warehouse, multiple stores. Each store is a `stock.location`.
- Low stock is monitored at **both** the warehouse and each store. Warehouse
  alerts use warehouse stock and warehouse outflow; store alerts use that
  store's own stock and consumption.
- Alerts are shown in-app only (no email / SMS / push — notifications are out of scope).
- UPC is stored in the product's native `barcode` field.
- Each product uses a single base unit; no packaging conversions.

---

## 4. Features

### F1 — Setup
The Administrator creates the warehouse, the stores (each linked to one location
and one manager), and products. Every product uses a single base unit — Pack,
Bottle or Piece (Decision 2).
**Done when:** a store manager can log in and see an empty but working store.

### F2 — Manual Receiving
Warehouse Staff open a new receipt, add products and quantities by hand, and
confirm. Stock rises on confirm.
**Done when:** the received amount shows in stock-by-location.

### F3 — Barcode / QR Receiving
Same as manual, but staff scan a code to add each line. Barcode and QR both carry
only the product UPC (Decision 9). If the code matches a product it is added
instantly; if not, the system offers to create the product. Works with a USB
scanner or by typing the code.
**Done when:** scanning a known code adds stock correctly.

### F4 — AI Smart Receiving
The primary feature. Steps:

1. Staff upload a supplier invoice or receipt (PDF or image).
2. Google Gemini 2.5 Flash reads it and extracts: supplier, invoice number, and
   for each line the product name, UPC, quantity, and unit price.
3. **Duplicate check first (Decision 3):** if the Supplier + Invoice Number
   combination already exists, the import is blocked and the user is notified —
   no stock changes.
4. If new, the system matches each line: **UPC first, then name.** If neither
   matches, the line is flagged "new product." Multiple name matches ask the
   user to choose.
5. A review screen shows every line with a clear label — *Matched by UPC*,
   *Matched by Name*, or *New*. Staff correct anything and set quantities in
   **base units** (e.g. "1 case of 12" entered as 12 — Decision 2).
6. **Always review (Decision 10):** regardless of AI confidence, the user must
   confirm before any inventory update.
7. On confirm, new products are created if needed and stock rises. The extracted
   **unit price is saved on the receipt as the supplier purchase price only** —
   it does not change the product's standard cost (Decision 4).

**Rules:** nothing touches inventory until a human confirms; any AI failure or
unreadable invoice keeps the receipt in "review" with no stock change.
**Done when:** a sample invoice produces correct lines, correct labels, and
correct stock after confirming.

### F5 — Store Request
A Store Manager creates a request (products + quantities) and submits it.
Warehouse Staff approve or reject. On approval and fulfillment, stock transfers
from the warehouse to that store.
**No partial fulfillment (Decision 5):** if the warehouse cannot fully cover the
request, it must be **rejected**. Rejections capture a reason.
States: `Draft → Submitted → Approved / Rejected → Fulfilled`.
**Done when:** an approved request lowers warehouse stock and raises store stock.

### F6 — Record Store Consumption
A Store Manager logs products used or sold. This lowers store stock and builds
the 7-day consumption history used for store-level low-stock alerts (Decision 1).
**Done when:** recording consumption lowers store stock and feeds the alert math.

### F7 — Low Stock Alerts (warehouse and store)
Runs once a day. For each watched location (the warehouse and each store) and
each product, the system looks at the last **7 days** of outflow, calculates the
average per day, and estimates days of cover. If below **10 days**, it raises an
alert tagged to that exact location (Decision 8 — fixed values).

- **No history → "Not Enough Data" (Decision 7):** displayed instead of a projection.
- **Auto-resolve (Decision 6):** when stock recovers above the threshold, the
  alert clears itself; no manual action required.

**Done when:** a low product at a store raises a store alert and a low product at
the warehouse raises a warehouse alert, each correctly labeled.

### F8 — Stock Visibility & Dashboard
Users see stock per location within their permissions (a Store Manager sees only
their store). A dashboard shows on-hand, open store requests, warehouse alerts
and store alerts (grouped by store), each clickable through to the full list.
**Done when:** the dashboard numbers match the underlying lists.

### F9 — Inventory Corrections
Wrong quantities are fixed with an **Inventory Adjustment** transaction
(Decision 11). Receipts remain permanent history and are never edited or deleted.
**Done when:** an adjustment corrects on-hand stock while the original receipt
stays intact.

---

## 5. Navigation & UI Specification (Build Spec)

This section is the **build specification** for the menus and screens. It matches
the approved UI mockup exactly; implement views to these details so the result is
identical. Each screen lists its view type, the fields/columns shown, badge
colours, buttons, and any workflow bar. Model and field names refer to the
Technical Design.

### 5.1 Application shell

- **App name (top bar):** `Inventory Management`
- **Top bar colour:** Odoo primary (violet/purple), white text — the standard app
  header. A small **role pill** ("Role: …") may show on the right for the demo.
- **Top-level menus, in this order:**
  `Dashboard · Warehouse · Requests · Stores · Low Stock Alerts · Configuration`
- **No single-child dropdowns:** a menu with one action opens that action
  directly; a menu with multiple actions shows them as sub-items (Odoo submenus).

### 5.2 Menu tree and role visibility

| Top menu | Sub-items (menu actions) | Warehouse Staff | Store Manager | Admin |
|----------|--------------------------|:---:|:---:|:---:|
| **Dashboard** | (opens the dashboard directly) | ✓ | ✓ (own store) | ✓ |
| **Warehouse** | Receipts · Stock by Location | ✓ | — | ✓ |
| **Requests** | To Approve · To Fulfill · My Requests | ✓ | ✓ (own store) | ✓ |
| **Stores** | Manage Stores · Record Consumption · My Store Stock | — | ✓ (own store) | ✓ |
| **Low Stock Alerts** | Warehouse Alerts · Store Alerts | ✓ | ✓ (own store) | ✓ |
| **Configuration** | Products · Settings (Gemini API key) | — | — | ✓ |

*(✓ = visible; — = hidden via `groups=`. "Own store" = record rules limit rows to
the manager's one assigned store. Admin sees everything. The Requests sub-items
are **saved filters/actions** on the same list, not separate models.)*

### 5.3 Global UI conventions

**Badge colour legend** (use `widget="badge"` on the field, or list
`decoration-*` attributes to colour rows/cells):

| Meaning | Colour | Used for |
|---------|--------|----------|
| Success / done / OK / matched by UPC / fulfilled | **green** | `state=done`, `match_status=upc`, availability OK |
| In progress / submitted / matched by name | **blue** | `state=submitted`, `match_status=name`, "to approve" |
| Attention / new product / warning cover | **amber** | `match_status=new`, cover 7–10 days |
| Error / rejected / short / active alert | **red** | `state=rejected`, "short", `status=active` |
| Ready / approved | **teal** | `state=approved`, "to fulfill" |
| Neutral / no data / manual/barcode type | **grey** | `not_enough_data`, `receipt_type in (manual,barcode)` |

**Workflow bar:** every workflow form shows an Odoo **statusbar** (`widget=
"statusbar"` on the `state` field) with the states in order, current state
highlighted.

**List conventions:** checkbox column, hover highlight, clicking a row opens the
form. Control panel has a **New** button (where creation is allowed), a title/
breadcrumb, and a search box.

---

### 5.4 Screen — Dashboard
- **Menu:** `Dashboard` (opens directly). **View:** custom dashboard / kanban.
- **KPI cards (row of 4):**
  1. **On-hand value** — total stock value (Warehouse + all stores).
  2. **Open store requests** — count, with inline badges: *N to approve* (blue),
     *N to fulfill* (teal).
  3. **Warehouse alerts** — count of active warehouse alerts (value in red).
  4. **Store alerts** — count of active store alerts (value in red).
- **Two list panels below:**
  - **Requests awaiting action** — columns: Reference, Store, Status (badge).
  - **Latest low-stock alerts** — columns: Product, Location, Cover (badge; red
    if < 10 days, amber if near, grey "Not Enough Data").
- **Role scope:** a Store Manager's cards/lists show only their own store.

### 5.5 Screen — Warehouse ▸ Receipts (list)
- **Menu:** `Warehouse > Receipts`. **Model:** `inventory.receipt`. **View:** list.
- **Columns:** ☐ · Reference (`name`) · Type (`receipt_type` badge: AI Smart =
  amber, Manual/Barcode = grey) · Supplier (`supplier_id`) · Invoice # (`invoice_
  number`) · Date · Status (`state` badge: Review = blue, Done = green).
- **New button** opens the receipt form; the user selects the **method** via
  `receipt_type` (Manual / Barcode·QR / AI Smart). One list, one model.
- Clicking a row opens the receipt form (5.6).

### 5.6 Screen — Receipt Form (incl. AI Smart Receiving review)
- **Model:** `inventory.receipt` (+ `inventory.receipt.line`). **View:** form.
- **Statusbar:** `Draft → Review → Done`.
- **Header buttons:** **Confirm & Update Stock** (primary); Back.
- **Header fields (two columns):** Supplier, Invoice Number, Warehouse, Source
  File (uploaded PDF/image for AI). Title shows `name` + a type badge
  ("AI Smart Receiving" amber).
- **Lines table** (`line_ids`): **Match** (`match_status` badge — UPC=green,
  Name=blue, New=amber) · Product (`product_id`; "(will be created)" hint when
  new) · UPC (`upc`) · **Qty (base)** (`quantity`, editable) · Unit Price
  (`unit_price`).
- **Callouts / rules shown on screen:**
  - Amber hint when a line needs base-unit entry: *"'1 case of 12' → enter 12
    base units before confirming"* (Decision 2).
  - Blue callout: *"Unit price stored as supplier purchase price only — does not
    change product standard cost"* (Decision 4).
  - Note: duplicate check on **Supplier + Invoice Number** runs before processing;
    a repeat import is blocked (Decision 3). Nothing updates stock until Confirm
    (Decision 10).

### 5.7 Screen — Warehouse ▸ Stock by Location (list/pivot)
- **Menu:** `Warehouse > Stock by Location`. **Source:** `stock.quant` (native),
  filtered to warehouse locations. **View:** list (optionally pivot).
- **Columns:** Product · Location · On Hand · Unit (base unit) · Days of Cover
  (badge; red < 10, green ≥ 10, grey "Not Enough Data").

### 5.8 Screen — Requests (list with tabs)
- **Menu:** `Requests`. **Model:** `inventory.store.request`. **View:** list.
- **Tabs = saved filters** (not separate screens):
  - **To Approve** — `state = submitted` (Warehouse Staff/Admin).
  - **To Fulfill** — `state = approved` (Warehouse Staff/Admin).
  - **My Requests** — created by current user (Store Manager).
- **Columns:** ☐ · Reference (`name`) · Store (`store_id`) · Requested By
  (`requested_by`) · Items (line count) · Status (`state` badge).
- Clicking a row opens the request form (5.9).

### 5.9 Screen — Store Request Form
- **Model:** `inventory.store.request` (+ lines). **View:** form.
- **Statusbar:** `Draft → Submitted → Approved / Rejected → Fulfilled`.
- **Header buttons (by state & role):** Submit (manager, draft); **Approve** /
  **Reject** (staff, submitted); **Fulfill** (staff, approved).
- **Header fields:** Store, Requested By, Date, Approver.
- **Lines table** (`line_ids`): Product · Qty Requested (`qty_requested`) ·
  **Available at WH** (`qty_available`, computed live) · status cell (**OK** green
  if available ≥ requested, **Short** red otherwise).
- **Rule shown:** if any line is short, an amber hint states the request must be
  **rejected** (no partial fulfillment — Decision 5). Reject requires a reason
  (`reject_reason`).

### 5.10 Screen — Stores ▸ Manage Stores (list/form)
- **Menu:** `Stores > Manage Stores`. **Model:** `inventory.store`.
- **List columns:** Store (`name`) · Code (`code`) · Location (`location_id`) ·
  Manager (`manager_id`).
- **Form:** name, code, location, manager. Constraint: exactly one manager per
  store; a manager belongs to exactly one store.

### 5.11 Screen — Stores ▸ Record Consumption (form)
- **Menu:** `Stores > Record Consumption`. **Model:**
  `inventory.store.consumption` (+ lines). **View:** form.
- **Header:** Store, Date. **Blue callout:** *"Recording consumption lowers store
  stock and builds the 7-day average for store alerts."*
- **Lines:** Product · Qty Used/Sold · Unit. Confirm creates outgoing moves from
  the store location (Decision 1).

### 5.12 Screen — Stores ▸ My Store Stock (list)
- **Menu:** `Stores > My Store Stock`. **Source:** `stock.quant` filtered to the
  manager's store (record-rule scoped). **Columns:** Product · Store · On Hand ·
  Days of Cover (badge).

### 5.13 Screen — Low Stock Alerts (shared, tabbed)
- **Menu:** `Low Stock Alerts` (single shared top-level menu). **Model:**
  `inventory.low.stock.alert`. **View:** list.
- **Tabs = filters:** **Warehouse Alerts** (`scope = warehouse`) · **Store
  Alerts** (`scope = store`). Store Managers see only their store's alerts.
- **Columns:** Product · Location/Store · On Hand (`current_qty`) · Avg/Day
  (`avg_daily_consumption`) · Days of Cover (`days_of_cover`; red < 10, amber near,
  grey when none) · Status (`status` badge: Active=red, Not Enough Data=grey).
- **Top callout:** *"Alerts auto-resolve above 10 days cover; 'Not Enough Data'
  when no history. Window = 7 days, threshold = 10 days (fixed)."*

### 5.14 Screen — Configuration (Admin only)
- **Menu:** `Configuration` (Admin only, `groups=`).
- **Products** — `product.product`: Name · UPC (`barcode`) · Base Unit.
- **Settings** (`res.config.settings`): Gemini API Key (masked) · Gemini Model
  (`gemini-2.5-flash`) · Consumption Window (7 days, fixed) · Low Stock Threshold
  (10 days, fixed).

### 5.15 Implementation checklist (to match the mockup)

- [ ] Six top menus in the exact order of 5.1, with role `groups=` per 5.2.
- [ ] Receipts is one list; method chosen by `receipt_type` on New (no separate
      receiving menus).
- [ ] Requests tabs are saved filters on one list (To Approve / To Fulfill / My
      Requests), not separate models.
- [ ] Low Stock Alerts is a single shared menu with Warehouse/Store filter tabs.
- [ ] Statusbars on receipt and request forms per 5.6 / 5.9.
- [ ] Badge colours follow the legend in 5.3 everywhere.
- [ ] Dashboard has the 4 KPI cards + 2 list panels of 5.4.
- [ ] All list/stock views expose a "Days of Cover" badge with the 10-day rule.

---

## 6. Out of Scope

Purchase orders / supplier management, auto-replenishment, multi-level approvals,
partial fulfillment, advanced forecasting, mobile app, and outbound
notifications (email / SMS / push).

---

## 7. Acceptance Criteria Summary

| Flow | Definition of Done |
|------|--------------------|
| Manual / Barcode | Confirming a receipt increases warehouse on-hand and is visible by location. |
| AI Smart | Sample invoice → correct lines & badges; confirm updates stock; a duplicate is blocked; an API failure leaves inventory untouched. |
| Store Request | Approved request transfers stock; a short request is rejected (no partial fill). |
| Consumption | Recording consumption lowers store stock and feeds the 7-day average. |
| Low Stock | Correct alerts appear at the right location; "Not Enough Data" for no history; alerts auto-clear on recovery. |
| Security | A Store Manager cannot see another store's data. |