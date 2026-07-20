# Decision Log
### Inventory Management System — Proof of Concept

This log records the confirmed business rules for the POC. All Functional,
Technical, Database, User-Flow, Security and Sprint documents are aligned to
these decisions. Status of every item below: **Confirmed**.

| # | Topic | Decision | Impact |
|---|-------|----------|--------|
| 1 | Store consumption / low stock | Store stock decreases through a **"Record Store Consumption"** action (products used or sold). This history feeds the 7-day rolling average for store-level low-stock alerts. | Adds `inventory.store.consumption`; drives store alerts. |
| 2 | Units of measure | Every product uses a **single base unit** (e.g. Pack, Bottle, Piece). No packaging conversions. An invoice "1 case of 12" must be entered/confirmed as the **base-unit quantity (12)** before update. | No conversion logic; editable qty on AI review line. |
| 3 | Duplicate invoices | Before processing, check whether **Supplier + Invoice Number** already exists. If duplicate, **block** the import and notify the user. | Unique DB constraint; early check in AI import. |
| 4 | Unit price | Extracted **Unit Price = supplier purchase price**, stored with receipt history. It does **not** update the product's standard cost. No taxes, discounts, or multi-currency. | `unit_price` on receipt line; `standard_price` untouched. |
| 5 | Insufficient warehouse stock | **No partial fulfillment.** If a store requests more than available, the warehouse user must **reject** the request. | Fulfillment blocked when short; reject with reason. |
| 6 | Alert resolution | Low-stock alerts **auto-resolve** once inventory is replenished above the threshold. No manual action to close. | Daily job resolves recovered alerts. |
| 7 | New products / no history | If a product lacks sufficient consumption history, show **"Not Enough Data"** instead of a projected days-remaining figure. | `not_enough_data` state; no divide-by-zero. |
| 8 | Threshold configuration | **Fixed** values (not configurable): Consumption Window = **7 days**; Low Stock Threshold = **10 days** of projected coverage. | Code constants `CONSUMPTION_WINDOW`, `THRESHOLD_DAYS`. |
| 9 | Barcode / QR code | Both Barcode and QR represent the **product UPC**. No custom QR payloads or multi-item codes. | Scan resolves UPC → product only. |
| 10 | Invoice quality | PDF and image supported; layouts may vary. Regardless of extraction confidence, the user must **always review and confirm** before inventory update. | Mandatory human-in-the-loop review. |
| 11 | Inventory corrections | Fix incorrect quantities via an **Inventory Adjustment**. Imported receipts remain **historical records** and are not deleted. | Native adjustment exposed; receipts read-only. |
| 12 | User roles | Each user has **one** role: **Warehouse Staff**, **Store Manager**, or **System Administrator**. Warehouse Staff cannot also be Store Manager. A Store Manager is assigned to **exactly one store**. Admin has full access. | Group category (single role); manager ↔ one store. |

---

## Change History

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-07-19 | Initial confirmed decision set (items 1–12). Supersedes two earlier proposals: configurable thresholds (now fixed — Decision 8) and a cancel/undo-receipt action (now Inventory Adjustment — Decision 11). |

---

## Still Open

None. All design questions required before implementation are closed. Next step:
**Sprint 0** (see `Sprint_Plan.md`).