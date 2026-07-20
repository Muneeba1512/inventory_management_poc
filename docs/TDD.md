# Technical Design Document (TDD)
### Inventory Management System — Proof of Concept

**Platform:** Odoo 19 · PostgreSQL · Google Gemini 2.5 Flash
**Version:** 1.0 (Confirmed Business Rules)

---

## 1. Approach

A custom Odoo 19 module (`inventory_poc`) that **sits on top of Odoo's native
`stock` module** and adds a small set of models, screens, one daily scheduled
job, and an AI service. It reuses Odoo's inventory engine so stock history and
valuation remain correct.

### 1.1 Architecture Approach (decision)

**Decision:** We build a **new Odoo application ("Inventory POC") that uses Odoo
Inventory (`stock`) as its backend engine** — we do **not** extend or modify the
native Inventory app's screens.

- The application has its **own top-level menu, its own models, and its own
  screens**, tailored to the three roles and five flows.
- Every real stock change still goes through the **native stock engine**: our
  code creates `stock.move` / `stock.picking` records and Odoo updates
  `stock.quant`. This gives correct stock levels, movement history and valuation
  for free, without reinventing inventory.
- In Odoo, an "application" is still packaged as a module that
  `depends on ['stock']`. The distinction is not the packaging — it is **where
  the user works and how much native UI we touch**. Our reuse of native pieces
  is deliberately surgical:

| Native reuse | How it is used |
|--------------|----------------|
| `stock.warehouse`, `stock.location`, `stock.quant`, `stock.move`, `stock.picking` | Backend only — created and read programmatically; invisible to the user. |
| `product.product.barcode` | Holds the product UPC. |
| Inventory Adjustment screen | Reused directly for corrections (Decision 11). |
| Everything else (stores, receipts, requests, consumption, alerts, dashboard, roles) | Custom models and views under the **Inventory POC** menu. |

**Why:** clean, role-specific UX and a clear demo story, while keeping native
inventory correctness and low risk of breaking standard flows. We add to Odoo
rather than rewiring it.

---

## 2. Technology Stack

- **Odoo 19** — application framework, ORM, OWL web client
- **PostgreSQL** — database
- **Python** — business logic and services
- **Google Gemini 2.5 Flash (Vision)** — invoice/receipt understanding
- **Module dependency:** `stock`

---

## 3. Reused Native Components

| Concern | Native model |
|---------|--------------|
| Warehouse & locations | `stock.warehouse`, `stock.location` |
| Stock levels | `stock.quant` |
| Movements & transfers | `stock.move`, `stock.picking` |
| Products (barcode = UPC, single base unit) | `product.product`, `product.template` |
| Suppliers | `res.partner` |
| Users | `res.users` |
| Scheduler | `ir.cron` |
| Number sequences | `ir.sequence` |

---

## 4. How Actions Touch Real Stock

- **Receiving (any method):** on confirm, create `stock.move`s from the
  supplier/vendor location into warehouse stock, then validate. Real moves keep
  history and valuation intact.
- **Fulfilling a request:** create an internal transfer picking
  (warehouse stock → store location).
- **Store consumption:** create outgoing moves from the store location to a
  customer/usage location.
- **Corrections:** use Odoo's native Inventory Adjustment on `stock.quant`.

---

## 5. Design Decisions Driven by Confirmed Rules

| Rule | Implementation |
|------|----------------|
| Duplicate guard (3) | DB unique constraint on `(supplier_id, invoice_number)`; AI import checks it early and stops with a clear message. |
| Base unit only (2) | One unit per product; **no** conversion code. Review line has an editable base-unit quantity. |
| Unit price (4) | Stored on the receipt line as `unit_price`; deliberately **not** written to `standard_price`. |
| Fixed thresholds (8) | `CONSUMPTION_WINDOW = 7` and `THRESHOLD_DAYS = 10` are code constants. |
| Auto-resolve (6) | The daily job raises new alerts and resolves those whose cover is back above 10 days. |
| Not enough data (7) | Zero average → `not_enough_data` state; never divides by zero. |
| Corrections (11) | Native Inventory Adjustment exposed; receipts read-only, no delete/reverse. |
| One role (12) | Odoo group **category** so only one role is selectable; Store Manager linked to exactly one store. |

---

## 6. Database Design (Custom Models)

> `→` indicates a relation to another model.

### `inventory.store`
| Field | Type | Notes |
|-------|------|-------|
| name | Char | store name |
| code | Char | short code |
| location_id | → `stock.location` | the store's own stock location |
| manager_id | → `res.users` | the one manager for this store |

*Rule:* one manager per store; one store per manager.

### `inventory.receipt` (permanent history)
| Field | Type | Notes |
|-------|------|-------|
| name | Char | auto sequence |
| receipt_type | Selection | `manual` / `barcode` / `ai` |
| warehouse_id | → `stock.warehouse` | |
| supplier_id | → `res.partner` | optional |
| invoice_number | Char | |
| source_file | Binary | uploaded PDF / image (AI) |
| ai_raw_response | Text | saved AI output for audit |
| state | Selection | `draft` / `review` / `done` |
| line_ids | → `inventory.receipt.line` | |

*Rule (Decision 3):* unique `(supplier_id, invoice_number)`.

### `inventory.receipt.line`
| Field | Type | Notes |
|-------|------|-------|
| receipt_id | → `inventory.receipt` | |
| product_id | → `product.product` | may be empty until matched |
| upc | Char | from invoice |
| raw_name | Char | name as read from invoice |
| quantity | Float | in base units (user confirms) |
| unit_price | Float | supplier purchase price, history only |
| match_status | Selection | `upc` / `name` / `new` |
| to_create | Boolean | create a new product on confirm |

### `inventory.store.request` & `inventory.store.request.line`
| Field | Type | Notes |
|-------|------|-------|
| name | Char | auto sequence |
| store_id | → `inventory.store` | |
| requested_by | → `res.users` | |
| approver_id | → `res.users` | |
| state | Selection | `draft` / `submitted` / `approved` / `rejected` / `fulfilled` |
| reject_reason | Text | required on reject |
| picking_id | → `stock.picking` | transfer created on fulfill |
| line: product_id | → `product.product` | |
| line: qty_requested | Float | base units |
| line: qty_available | Float | computed, shown live from warehouse stock |

### `inventory.store.consumption` & lines
| Field | Type | Notes |
|-------|------|-------|
| name | Char | auto sequence |
| store_id | → `inventory.store` | |
| date | Date | |
| line_ids | → consumption line | `product_id` + `quantity` |

### `inventory.low.stock.alert`
| Field | Type | Notes |
|-------|------|-------|
| product_id | → `product.product` | |
| location_id | → `stock.location` | the watched location |
| scope | Selection | `warehouse` / `store` |
| store_id | → `inventory.store` | set only for store alerts |
| current_qty | Float | stock at that location |
| avg_daily_consumption | Float | 7-day average |
| days_of_cover | Float | blank if no data |
| status | Selection | `active` / `resolved` / `not_enough_data` |

*Rule:* one active alert per `(product, location)`; auto-resolves at cover ≥ 10 days.

---

## 7. Low-Stock Computation (same routine per location)

```text
for each watched location (warehouse + each store):
    for each product at that location:
        outflow_7d   = finished outgoing moves in the last 7 days
        avg_per_day  = outflow_7d / 7
        if avg_per_day == 0:
            set alert = "Not Enough Data"
            continue
        days_of_cover = current_qty_here / avg_per_day
        if days_of_cover < THRESHOLD_DAYS (10):
            raise or update an active alert (scope + store tagged)
        else:
            resolve any existing alert for this product + location
```

Warehouse outflow includes fulfilled store requests; store outflow is that
store's recorded consumption. One piece of code covers both alert types, run by
a single daily `ir.cron`.

---

## 8. AI Service Design

- **Config:** Gemini API key and model name live in Settings
  (`ir.config_parameter`) — never in code.
- **Call:** the service sends the uploaded file (base64) plus a fixed instruction
  requesting **structured JSON**: `supplier`, `invoice_number`, and a list of
  lines `{product_name, upc, quantity, unit_price}`. JSON mode keeps parsing
  reliable.
- **Matching:** `barcode == upc` → single name match → (multiple matches ⇒ ask
  user) → else flag `new`.
- **Audit & safety:** raw response stored; any error keeps the receipt in
  `review`; nothing updates stock until a human confirms.

---

## 9. Security

- Three roles via an Odoo group **category** (only one selectable per user).
- `ir.model.access.csv` sets read/write/create/delete per model per role.
- Record rules filter Store Manager data to their own store; a Store Manager is
  linked to exactly one store (validated on save).
- Warehouse Staff can see all stores (needed to fulfill) but not admin config.
- Receipts are read-only once `done` (no delete) — Decision 11.

*(Full detail in `Security_Model` section of the design and the FDD.)*

---

## 10. Module Layout

```text
inventory_poc/
├── __manifest__.py            # depends: ['stock']; external dep: google-generativeai
├── models/                    # store, receipt(+line), store_request(+line),
│                              # store_consumption, low_stock_alert, res_config_settings
├── services/gemini_service.py # AI call + matching (isolated, testable)
├── views/                     # menus, forms, lists, kanban dashboard
├── security/                  # groups (category), ir.model.access.csv, record rules
├── data/                      # ir.sequence, ir.cron (daily low-stock)
├── demo/                      # sample warehouse, stores, products, a test invoice
└── tests/                     # matching, workflow states, low-stock math
```

---

## 11. Edge Cases Handled

Duplicate invoice upload (blocked), unreadable invoice (stays in review),
no match / multiple matches (ask the user), zero consumption history
("Not Enough Data"), request larger than stock (rejected, no partial fill),
and stock recovery (alert auto-resolves).

---

## 12. Deployment & Testing

- **Install:** place the module in the addons path, install the Gemini Python
  dependency, add the module, then set the Gemini API key in Settings. Ships with
  demo data for immediate trial.
- **Testing:** unit tests for the matching rules and low-stock math; workflow
  tests for request state transitions; a manual script walking all five flows
  with the demo data.