# Sprint Plan
### Inventory Management System — Proof of Concept

**Cadence:** six short sprints, roughly one week each for a single developer
(adjust to your team). Every sprint ends with something **installable and
clickable**, so progress is visible throughout. The risky, self-contained work
comes first; the external AI service comes last.

---

## Sprint 0 — Foundation
**Goal:** an installable module skeleton with roles and setup screens.

- Module scaffold (`__manifest__.py`, folders), depends on `stock`
- Three user roles via a group **category** (one role per user)
- `inventory.store` model + Store Manager tied to exactly one store
- Products configured with a **single base unit**
- Menus, setup screens (warehouse, stores, products), demo data

**Done when:** the module installs, each role logs in, and an empty but working
store is visible.

---

## Sprint 1 — Receiving + Stock Visibility
**Goal:** get stock into the warehouse and see it by location.

- `inventory.receipt` (+ lines) as **permanent history**
- Manual receiving → creates `stock.move`s on confirm
- Barcode / QR receiving (UPC only) with scan-to-add
- Stock-by-location list / pivot view

**Done when:** receiving by hand and by scan increases warehouse stock correctly.

---

## Sprint 2 — Store Requests + Consumption
**Goal:** move stock to stores and record store usage.

- `inventory.store.request` workflow: `Draft → Submitted → Approved / Rejected → Fulfilled`
- Fulfillment creates an internal transfer (warehouse → store)
- **Reject-if-short** rule (no partial fulfillment)
- Live warehouse availability shown on request lines
- `inventory.store.consumption` action → feeds the 7-day store history

**Done when:** an approved request transfers stock, a short request is rejected,
and recording consumption lowers store stock.

---

## Sprint 3 — Low Stock Detection + Dashboard
**Goal:** alerts at both the warehouse and every store.

- Daily `ir.cron` running the per-location low-stock routine
- Warehouse **and** store alerts (`inventory.low.stock.alert`)
- Fixed thresholds: 7-day window, 10-day cover
- **Auto-resolve** on recovery; **"Not Enough Data"** for no history
- Dashboard cards: on-hand, open requests, warehouse alerts, store alerts (by store)

**Done when:** seeded activity produces correct, correctly-attributed alerts, and
alerts clear automatically when stock recovers.

---

## Sprint 4 — AI Smart Receiving
**Goal:** read invoices with Gemini and post reviewed stock.

- Gemini service (key in Settings, structured JSON output, raw response saved)
- Matching engine: UPC → name → new (multiple matches ⇒ ask user)
- Review screen with colored match badges
- **Duplicate (Supplier + Invoice Number) block**
- **Base-unit confirmation** on the review line
- **Always review** before update; unit price saved as history only (not product cost)

**Done when:** uploading a real invoice yields correct lines and badges, a
duplicate is blocked, and confirming updates stock.

---

## Sprint 5 — Polish, Test & Deploy
**Goal:** a ship-ready POC.

- UI/UX pass and dashboard refinement
- Inventory Adjustment path for corrections (receipts stay as history)
- Automated tests: matching, workflow states, low-stock math, duplicate block,
  role / record-rule checks
- Demo dataset + install guide
- End-to-end demo of all five flows

**Done when:** the POC can be demoed end-to-end and installed from the guide.

---

## Sequencing Rationale

Solid native-stock foundation and workflows are built first because they carry
the least external risk. The one part depending on an outside service (the
Gemini AI) is scheduled last, when everything it feeds into already works —
keeping risk low and delivering a working product early.