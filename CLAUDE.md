# Inventory Management POC

## Project

- Platform: Odoo 19 Community
- Module: Inventory Management POC
- Purpose: Build a clean, modular, production-style proof of concept.

## Development Rules

- Never modify Odoo core files.
- Use Odoo ORM only.
- Follow Odoo 19 best practices.
- Use XML inheritance whenever extending existing views.
- Write clean, reusable, well-commented code.
- Keep business logic in Python models/services.
- Keep views simple.
- Use proper security groups and access rights.

## Development Process

- Implement one sprint at a time.
- Before coding:
  1. Explain the implementation plan.
  2. List every file to be created.
  3. List every file to be modified.
  4. Explain why each file is needed.
  5. Wait for approval.

- Never implement future sprints unless explicitly requested.

## AI Receiving

- Use Google Gemini 2.5 Flash.
- AI extracts:
  - Supplier
  - Invoice Number
  - Product Name
  - UPC
  - Quantity
  - Unit Price
- Match by UPC.
- If not found, match by Product Name.
- If still not found, create a new product.
- Always show a review screen before updating inventory.

## Business Rules

- One user has exactly one role.
- A Store Manager manages exactly one store.
- No partial fulfillment of store requests.
- Duplicate invoices must be prevented.
- Products use a single base unit.
- Inventory corrections are handled through Inventory Adjustments.
- Low-stock alerts automatically resolve after replenishment.
- Fixed thresholds:
  - 7-day consumption window
  - 10-day stock coverage

## Coding Standards

- Follow PEP 8.
- Use meaningful variable names.
- Avoid duplicated code.
- Keep methods small and focused.
- Document complex logic with comments.