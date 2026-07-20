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

## 5. Out of Scope

Purchase orders / supplier management, auto-replenishment, multi-level approvals,
partial fulfillment, advanced forecasting, mobile app, and outbound
notifications (email / SMS / push).

---

## 6. Acceptance Criteria Summary

| Flow | Definition of Done |
|------|--------------------|
| Manual / Barcode | Confirming a receipt increases warehouse on-hand and is visible by location. |
| AI Smart | Sample invoice → correct lines & badges; confirm updates stock; a duplicate is blocked; an API failure leaves inventory untouched. |
| Store Request | Approved request transfers stock; a short request is rejected (no partial fill). |
| Consumption | Recording consumption lowers store stock and feeds the 7-day average. |
| Low Stock | Correct alerts appear at the right location; "Not Enough Data" for no history; alerts auto-clear on recovery. |
| Security | A Store Manager cannot see another store's data. |