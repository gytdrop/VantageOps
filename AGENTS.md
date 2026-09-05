# VantageOps Agent Guidelines & Team Governance

This repository enforces an **isolated modular Odoo architecture** extending native Odoo models (`sale.order`, `sale.order.line`, `product.template`, `portal`) for a 2-person engineering team (**Akthar** and **Ashrith**).
Every developer and AI coding agent operating in this codebase MUST strictly follow these rules to ensure zero code conflicts and seamless delivery.

---

## 1. Team Directory & Ownership Structure

Custom modules are located strictly under `custom_addons/`:

```
custom_addons/
├── vantage_core/          # FROZEN BASE: Shared data model extensions on sale.order & sale.order.line.
├── vantage_governance/    # AKTHAR'S MODULE: Margin Governance, Approvals, Chatter Escalations & Portal Negotiation.
└── vantage_fulfillment/   # ASHRITH'S MODULE: Multi-Warehouse Auto-Split, Backorder Forking & Live Upsell Engine.
```

### Module Assignment
| Teammate | Assigned Addon Module | Technical Focus |
| :--- | :--- | :--- |
| **Akthar** | `custom_addons/vantage_governance/` | Margin Governance, `action_confirm` block, `mail.activity` escalations, QWeb Portal counter-offer UI, circuit-breaker negotiation logic. |
| **Ashrith** | `custom_addons/vantage_fulfillment/` | `_compute_split_requirement()`, `action_split_fulfillments()` multi-warehouse stock routing, Optional Products `margin_delta` live upsell. |

---

## 2. Ironclad Rules (Zero-Conflict Protocol)

1. **`vantage_core` is 100% FROZEN after initial setup**:
   - `vantage_core` defines shared fields on `sale.order` (`blended_risk_score`, `risk_approval_state`, `is_recurring_hybrid`) and `sale.order.line`.
   - **DO NOT MODIFY `vantage_core`** once established. Any feature-specific logic or UI belongs in your assigned module.

2. **Strict File Isolation**:
   - **If working as Akthar**: You are STRICTLY FORBIDDEN from editing any file under `custom_addons/vantage_fulfillment/` or `custom_addons/vantage_core/`.
   - **If working as Ashrith**: You are STRICTLY FORBIDDEN from editing any file under `custom_addons/vantage_governance/` or `custom_addons/vantage_core/`.

3. **Data Model Inheritance (`_inherit`)**:
   - Always extend existing Odoo native models (`sale.order`, `sale.order.line`) using `_inherit`:
     ```python
     class SaleOrderGovernance(models.Model):
         _inherit = 'sale.order'
     ```

4. **XML View Extension via Unique XPath**:
   - Never override base views entirely. Always inherit using `inherit_id="sale.view_order_form"` and `<xpath>`.
   - Use distinct tab page names inside `<notebook>`:
     - Akthar adds `<page name="page_akthar_approvals" string="Risk &amp; Approvals">`
     - Ashrith adds `<page name="page_ashrith_fulfillment" string="Fulfillment &amp; Splitting">`

5. **Interface Contract Synchronization**:
   - Consult [CONTRACT.md](CONTRACT.md) before declaring any fields or methods.
   - Do not use field names or method names reserved for the other teammate.

6. **Git Branching Strategy**:
   - Akthar commits on branch `feature/akthar-governance` (or directly inside `vantage_governance`).
   - Ashrith commits on branch `feature/ashrith-fulfillment` (or directly inside `vantage_fulfillment`).

---

## 3. Persona Dispatcher Protocol

When a user or prompt indicates **"I am Akthar"** or **"I am Ashrith"**, the AI agent MUST execute this exact protocol:

### Trigger: "I am Akthar"
1. **Identify**: Acknowledge role as Akthar (Lead on Commercial Control: `vantage_governance`).
2. **Restrict Scope**: Confine all file changes exclusively to `custom_addons/vantage_governance/`.
3. **Inspect Progress**: Check `CONTRACT.md` and `EXECUTION_PLAN.md` for current milestone status.
4. **Present Work Package**: Display the specific sub-tasks queued for Akthar.
5. **Execute Immediately**: Begin implementing the next pending sub-task without delay.

### Trigger: "I am Ashrith"
1. **Identify**: Acknowledge role as Ashrith (Lead on Operational Execution: `vantage_fulfillment`).
2. **Restrict Scope**: Confine all file changes exclusively to `custom_addons/vantage_fulfillment/`.
3. **Inspect Progress**: Check `CONTRACT.md` and `EXECUTION_PLAN.md` for current milestone status.
4. **Present Work Package**: Display the specific sub-tasks queued for Ashrith.
5. **Execute Immediately**: Begin implementing the next pending sub-task without delay.
