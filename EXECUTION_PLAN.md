# ⚡ VantageOps Hackathon Execution Blueprint

## 1. The Strategy: "Native Odoo Gigs"
Do not rebuild native Odoo functionality. We are exploiting core Odoo patterns to deliver the massive scope outlined in the wireframes in under 400 lines of Python.

| VantageOps Feature | We Write (The Delta) | Odoo Native Engine Handing the Rest |
| :--- | :--- | :--- |
| **Approval Routing** | Risk Score Math + `action_confirm` block | `mail.activity` (Chatter tasks & logging) |
| **Portal Negotiation** | `<xpath>` input field + RPC method | `portal` + `mail.thread` (Customer UI & security) |
| **Upsell Engine** | `margin_contribution` field | `sale_management` (Optional Products UI) |
| **WH Stock Split** | Auto-split line computation | `sale_stock` (Auto-generates pickings per WH) |

---

## 2. Resources & Repositories
*   **Target Environment:** Local Odoo DB for testing $\rightarrow$ GitHub $\rightarrow$ Assigned Online DB for judging.
*   **Reference Repo 1:** `https://github.com/odoo/odoo` (Core reference for `sale.order` and `sale_portal_templates.xml`).
*   **Reference Repo 2:** `https://github.com/OCA/sale-workflow` (Inspect `sale_exception` for approval blocking mechanics).

---

## 3. Division of Labor & UI Mapping

### 🧠 Shared Foundation (`vantage_core`)
*Both members pull this first.*
*   **Models:** Extends `sale.order` and `sale.order.line`.
*   **Logic:** Calculates `blended_risk_score`, defines `risk_approval_state`, and sets `is_recurring_hybrid`.
*   **UI Target:** Powers the central Sales Dashboard metrics.

### 👤 Member 1: Commercial Control (`vantage_governance`) - Akthar
*   **Focus Areas:** "Approvals" tab and Customer Negotiation logic.
*   **Task 1 (Backend):** Override `action_confirm()`. If risk is high and unapproved, raise `UserError` and schedule a `mail.activity` for the manager.
*   **Task 2 (Frontend/QWeb):** Inherit `sale_order_portal_template` using QWeb XML to add a counter-offer input next to order lines in the portal view.
*   **Task 3 (Logic):** Write `action_customer_counter_offer()` to intercept portal input, recalculate risk, log to chatter, and lock negotiation if rounds exceed the limit.

### 👤 Member 2: Operational Execution (`vantage_fulfillment`) - Ashrith
*   **Focus Areas:** "Fulfillment" tab, Warehouse routing, and Upsell margins.
*   **Task 1 (Backend):** Write `_compute_split_requirement()` to check `product_id.free_qty` against `order_line.product_uom_qty`.
*   **Task 2 (Logic):** Write `action_split_fulfillments()` to split a line item into two if stock is short, pointing the deficit line to a secondary warehouse.
*   **Task 3 (Frontend/XML):** Add a computed `margin_delta` field to the native Optional Products view to show live profitability impact during the Quotation Detail phase.

---

## 4. The Development Loop (Zero Conflict Rule)
1.  **Code & Test Locally:** Start local Odoo with `--dev=reload` and `-d <local_db>`.
2.  **Commit Isolation:** Member 1 (Akthar) only commits inside `vantage_governance`. Member 2 (Ashrith) only commits inside `vantage_fulfillment`.
3.  **Sync:** Push to GitHub `main` branch.
4.  **Deploy:** Pull to the production server and upgrade modules via UI (Apps $\rightarrow$ Update Apps List) or CLI.
