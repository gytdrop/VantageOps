# DealFlow360: An Intelligent, Self Governing Sales Operations Platform

## 1. Project Overview
Most simple sales tools handle the basics well: create a quote, confirm an order, invoice it. Real B2B sales teams operate in messier conditions such as multi-level discount approvals, partial stock spread across warehouses, bundled subscriptions mixed with one-time hardware, customers who want to negotiate inside a portal instead of over email, and managers who only find out a deal is stuck after it has already lost momentum.

The goal of this project is to build a sales platform that goes beyond a quote-to-invoice form and becomes a **self-governing deal engine**—one that enforces pricing discipline, reacts to inventory reality in real time, keeps subscriptions and one-time sales reconciled on a single order, and gives both sales reps and customers a living, negotiable document instead of a static PDF.

**Excalidraw Mockup**: [https://app.excalidraw.com/l/65VNwvy7c4X/7Fb5SR3WKu2](https://app.excalidraw.com/l/65VNwvy7c4X/7Fb5SR3WKu2)

---

## 2. Goals & Scope

### Main Goal
Build a complete sales flow including backend configuration and a frontend quotation-to-cash experience.

### Key Outcomes
- **Multi-tier Discount Governance**: Sales reps build quotations with automated approval routing based on discount thresholds, customer tiers, and product categories.
- **Live Margin & Recommendations**: Reps receive live upsell and cross-sell suggestions with real-time margin impact while building quotes.
- **Multi-Warehouse Fulfillment**: Automatic splitting across warehouses based on real-time stock availability, with manual override and backorder consolidation.
- **Hybrid Billing**: Orders combine one-time items and recurring subscription lines with proration and billing schedules.
- **Real-Time Deal Health Dashboard**: Monitors deal health, stalled quotes, delivery promise slippage, and discount anomalies.
- **Interactive Customer Negotiation Portal**: Customers view, negotiate line-items, and counter-offer in a dedicated customer-facing portal.

---

## 3. User Roles

1. **Sales Rep**:
   - Builds quotations, applies discounts, reviews upsell recommendations.
   - Tracks approval status and fulfillment progress.
   - Responds to customer negotiation requests.
2. **Sales Manager / Approver**:
   - Reviews and approves/rejects quotations exceeding discount thresholds.
   - Configures discount tiers and approval chains.
   - Monitors deal health dashboard for at-risk deals.
3. **Finance / Operations User**:
   - Handles second-level approvals for high-risk discounts.
   - Manages warehouse fulfillment splits and backorder decisions.
   - Reconciles recurring billing schedules and credit notes.
4. **Customer (Portal User)**:
   - Views quotation online in a restricted portal.
   - Requests changes, asks line-level questions, or counters discounts.
   - Confirms final terms with one click.
5. **Admin**:
   - Manages setup: products, price lists, discount tiers, warehouses, subscription plans.
   - Views platform-wide analytics and reporting.

---

## 4. Modules & Features Breakdown

### A) Sales Backend (Configuration Area)
- **A1) Authentication (Login / Signup)**: Internal users sign up/login with role-based access; customers use portal login (magic link/credentials).
- **A2) Product & Price List Management**: Product info, categories (Hardware, Services, Subscriptions), variants, price lists (customer tier pricing, currencies).
- **A3) Discount Tier & Approval Chain Setup**:
  - Discount ceilings per customer tier (Bronze: 5%, Silver: 10%, Gold: 15%).
  - Category-specific discount ceilings (e.g., Services stricter than Hardware).
  - Multi-level approval chains (Manager only vs. Manager + Finance).
  - Audit log for all approvals, rejections, and edits with user, timestamp, and reason.
- **A4) Warehouse & Fulfillment Setup**:
  - Manage multiple warehouses (Main Warehouse, East Depot, etc.).
  - Stock levels and replenishment rules per warehouse.
  - Shipping cost weighting for auto-split optimization.
- **A5) Subscription / Recurring Plan Setup**:
  - Recurring plans (monthly, quarterly, yearly).
  - Proration rules for mid-cycle changes.
  - Cancellation and refund/credit note rules.
- **A6) Upsell / Cross-Sell Rule Setup**:
  - Pairings based on co-purchase history and promoted tags.
  - Minimum margin thresholds.
- **A7) Reporting & Dashboard Configuration**:
  - Filter by Period, Sales Rep/Team, Approval Status, Product/Category.
  - Export to PDF / XLS.

### B) Sales Frontend (Rep Workspace Experience)
- **B1) Sales Workspace & Top Navigation**: Quick navigation between Quotations and Kanban Pipeline.
- **B2) Quotation List / Pipeline View**: Kanban and list cards displaying customer, amount, stage, and quick status.
- **B3) Quotation Builder Screen (Products + Cart)**: Dynamic product picker, quantity adjustments, line & order discounts, live margin indicator.
- **B4) Discount Approval Screen**: Shows blended risk score, required approval steps (Manager, Finance), approval/rejection audit trail.
- **B5) Upsell & Cross-Sell Panel**: Ranked suggestions with margin delta indicators, instant cart integration.
- **B6) Fulfillment & Warehouse Split Screen**: Stock-based split suggestions, estimated shipment count/cost, manual overrides, backorder consolidation.
- **B7) Subscription & Billing Screen**: Clean separation of one-time and recurring lines, upcoming billing schedules, mid-cycle proration handlers.
- **B8) Customer Portal Negotiation Screen**: Dedicated buyer interface for line comments, counter-offers; automatically routes back to approvals if thresholds are breached.
- **B9) Deal Health & Anomaly Dashboard**: Stalled deals (>X days inactive), discount anomalies vs. rep average, delivery promise slippage indicators, and escalation triggers.

---

## 5. Understanding the Blended Discount Risk Score

The score determines whether a quotation requires Sales Manager approval, and if severe, Finance approval:
- **Line-Level Violations**: Checks individual product category limits against customer tier limits (e.g., Gold allows 15% on Hardware, but Services limit is 10%; an 18% discount on Services triggers approval).
- **Cumulative Margin Erosion (Blended)**: Prevents reps from giving small discounts across many lines that cumulatively destroy order profitability. The blended score evaluates aggregate margin loss across the entire cart.

---

## 6. Quick Test Flow (8-Step End-to-End Validation)
1. **Setup**: Sign up/login, configure discount tier, warehouse, and subscription plan.
2. **Exceed Discount**: Create quote with a discount higher than permitted.
3. **Auto-Routing**: Confirm the quote automatically routes to Manager approval.
4. **Live Upsell**: Accept an upsell suggestion and verify order total & margin update immediately.
5. **Approval & Split**: Approve quote and verify stock is split across warehouses based on availability.
6. **Hybrid Billing**: Verify one-time items and recurring subscription lines generate correct billing schedules.
7. **Portal Negotiation**: Submit a counter discount from the customer portal and verify it re-enters approval.
8. **Finalize**: Confirm order, record payment, and confirm invoice status updates correctly.
