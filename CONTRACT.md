# Interface Contract (Data & API Agreements) — VantageOps

> **CRITICAL RULE FOR AKTHAR & ASHRITH**:
> 1. `vantage_core` is **FROZEN** after initial baseline setup. Extends native `sale.order` and `sale.order.line`.
> 2. **Akthar** works EXCLUSIVELY inside `custom_addons/vantage_governance/`.
> 3. **Ashrith** works EXCLUSIVELY inside `custom_addons/vantage_fulfillment/`.
> 4. Do not rebuild native Odoo functionality: rely on `sale`, `mail.activity`, `portal`, and `sale_stock`.

---

## 1. Shared Foundation: `vantage_core` (Base Models: `sale.order` & `sale.order.line`)

| Model | Field Name | Type | Description |
| :--- | :--- | :--- | :--- |
| `sale.order` | `blended_risk_score` | `Float` | Order-wide aggregate risk metric based on discount deviations |
| `sale.order` | `risk_approval_state` | `Selection` | `['draft', 'pending_approval', 'approved', 'rejected']` |
| `sale.order` | `is_recurring_hybrid` | `Boolean` | True if quote contains both one-time products and recurring subscription lines |
| `sale.order.line` | `line_risk_score` | `Float` | Individual line penalty based on discount vs permissible margin |
| `sale.order.line` | `is_subscription_item` | `Boolean` | True if product is categorized as a recurring subscription |

---

## 2. Commercial Control: `vantage_governance` (Akthar)

| Target | Identifier | Type | Description |
| :--- | :--- | :--- | :--- |
| `sale.order` | `negotiation_rounds` | `Integer` | Count of customer counter-offers (circuit breaker limit: 3) |
| `sale.order` | `is_negotiation_locked` | `Boolean` | Set to True when negotiation rounds exceed maximum permitted |
| `sale.order` | `approval_activity_id` | `Many2one` | Native `mail.activity` link for manager approval task |
| `sale.order` | `action_confirm()` | Method Override | Blocks confirmation if risk is high and unapproved; raises `UserError` and schedules `mail.activity` |
| `sale.order` | `action_customer_counter_offer()` | Method | Intercepts portal counter, increments rounds, recalculates risk, logs to chatter |
| `sale.order` | `action_manager_approve()` | Method | Marks `risk_approval_state = 'approved'`, marks activity done |
| `portal` | `sale_order_portal_template` | QWeb XML XPath | Injects counter-offer input & submit button next to order lines |

---

## 3. Operational Execution: `vantage_fulfillment` (Ashrith)

| Target | Identifier | Type | Description |
| :--- | :--- | :--- | :--- |
| `sale.order.line` | `requires_split` | `Boolean` | Computed True when `product_id.free_qty < product_uom_qty` |
| `sale.order.line` | `deficit_qty` | `Float` | Deficit quantity exceeding primary warehouse available stock |
| `sale.order.line` | `fulfillment_warehouse_id` | `Many2one` | Regional `stock.warehouse` assigned for this specific line |
| `sale.order` | `action_split_fulfillments()` | Method | Splits lines with stock deficits: truncates primary line & forks secondary backorder line |
| `sale.order.line` | `margin_delta` | `Float` | Computed profitability impact for Optional Products UI |
| `sale.order` | `_compute_split_requirement()` | Method | Checks stock availability across warehouses for all quotation lines |
| `sale.view_order_form` | `page_ashrith_fulfillment` | XML Form Tab | Injects "Fulfillment & Warehouses" tab into `sale.view_order_form` |
