# VantageOps

**Enterprise Commercial Governance & Operational Fulfillment Engine for Odoo 17 & 18**

VantageOps is an integrated, modular Odoo application suite engineered to protect enterprise gross margins, automate multi-tiered approval workflows, optimize multi-warehouse order fulfillment, and streamline customer portal negotiations.

---

## 🏗️ Architecture & Module Suite

VantageOps extends native Odoo models (`sale.order`, `sale.order.line`, `stock.picking`, and `portal`) cleanly without altering core code:

```
custom_addons/
├── vantage_core/          # Shared foundation: Risk scoring, state machines & contract typing
├── vantage_governance/    # Margin governance, chatter escalations & portal negotiation
└── vantage_fulfillment/   # Multi-warehouse auto-split routing & live upsell engine
```

### 1. `vantage_core` (Base Foundation)
* **Blended Risk Scoring**: Real-time evaluation of quotation risk factors (discount depth, category margin variance).
* **Approval State Machine**: State transitions managing standard draft orders, required internal approvals, and authorized states.
* **Hybrid Contract Awareness**: Differentiates between one-off hardware/product sales and recurring service agreements.
* **Policy Accessor (`vantage.config`)**: Typed resolver for every commercial threshold, backed by `ir.config_parameter` with shipped defaults. No business rule is a Python literal.

### 2. `vantage_governance` (Commercial Control)
* **Configurable Tier Policy**: `vantage.discount.tier` lets administrators define any number of tiers (Bronze, Gold, Platinum, Distributor, Government…), each with its own discount ceiling, manager sign-off cap and negotiation budget.
* **Category-Specific Ceilings**: A Gold account may earn 15% on Hardware but only 8% on thin-margin Services. Resolution walks up the product category tree.
* **Margin Floor Enforcement**: Prohibits confirmation (`action_confirm`) of quotations breaching the ceiling in force, with configurable trigger and escalation thresholds.
* **Chatter Escalations**: Automatically dispatches `mail.activity` escalations with contextual metadata directly to finance/sales managers.
* **Portal Counter-Offer Interface**: Secure, tokenized customer negotiation interface enabling customers to submit counter-proposals within defined guardrails.
* **Circuit Breaker Logic**: Bounds counter-offer iterations. The budget resolves **sales team → customer tier → global setting**, and remains overridable per quotation.

### 3. `vantage_fulfillment` (Operational Execution)
* **N-Way Depot Allocation**: Ranks every eligible warehouse by landed leg cost (`base_shipping_cost × shipping_cost_weight`) and greedily fills them cheapest-first across **any number** of depots — not just a primary plus one secondary. A shared stock ledger prevents two lines of the same product from double-claiming units.
* **Leg Budget & Shortfall Reporting**: A configurable cap limits how many depots one order may ship from; demand no depot can cover is surfaced as an explicit shortfall rather than silently dropped.
* **Backorder Routing & Consolidation**: Forks one child line per additional depot, and merges every leg back into a single shipment when stock arrives.
* **Live Margin Delta Upsell**: Calculates and displays margin impacts for optional/accessory products directly within quotation views.
* **Cadence-Aware Billing**: Each subscription product bills at its own cadence (monthly, quarterly, semi-annual, annual) over a configurable contract length, with cycles placed using real calendar arithmetic (`relativedelta`).
* **Exact-Day Proration**: Calendar-aligned contracts prorate partial first/last cycles on exact day counts, and a mid-cycle wizard bills seat changes at the precise remaining-day fraction (negative deltas produce credits).

---

## 📊 Complete Data Schema & ERD

For detailed entity relationship diagrams, model specifications, field dictionaries, and security access matrices, please inspect:
👉 **[SCHEMA.md](SCHEMA.md)**

---

## 🚀 Installation & Setup

### Prerequisites
* Odoo 17.0 / 18.0 Community or Enterprise
* Standard Odoo dependencies: `sale_management`, `stock`, `portal`, `mail`, `sale_stock`

### Installation
1. Clone this repository into your Odoo project or add `custom_addons/` to your `odoo.conf`:
   ```ini
   addons_path = /path/to/odoo/addons,/path/to/VantageOps/custom_addons
   ```
2. Restart your Odoo server with app list update:
   ```bash
   ./odoo-bin -c odoo.conf -u vantage_core,vantage_governance,vantage_fulfillment -d <database_name>
   ```
3. Navigate to **Apps**, search for **VantageOps**, and activate the modules.

> **Verify the upgrade by its exit code, not its log output.** A data-file failure aborts the
> whole registry load and rolls the schema back, while the surrounding log lines still look
> ordinary. `echo $?` must be `0`.

---

## ⚙️ Configuration Surface

Every commercial threshold is administrator-editable — nothing is hardcoded.

| Rule | Where it is configured |
| :--- | :--- |
| Tier ceilings, category overrides, per-tier manager cap & negotiation budget | Sales ▸ Configuration ▸ **Customer Discount Tiers** |
| Fallback ceiling, blended-risk weights | Settings ▸ Sales ▸ **VantageOps — Discount Governance** |
| Approval trigger, Manager/Finance boundary, default negotiation rounds | Settings ▸ Sales ▸ **VantageOps — Approval Routing** |
| Stalled-after days, margin-bleed score, discount-anomaly % | Settings ▸ Sales ▸ **VantageOps — Deal Health** |
| Maximum depots per order | Settings ▸ Sales ▸ **VantageOps — Multi-Depot Fulfillment** |
| Default cadence, contract length, cycle anchor | Settings ▸ Sales ▸ **VantageOps — Subscription Billing** |
| Per-product cadence, contract months, price basis | Product ▸ Sales tab ▸ **VantageOps Recurring Billing** |
| Per-team negotiation rounds | Sales Team form |
| Depot cost weight, allocation priority, split participation | Warehouse ▸ **VantageOps Logistics** tab |

After changing any risk threshold, run **Settings ▸ Sales ▸ "Re-score Open Quotations"** —
system parameters cannot participate in Odoo's `@api.depends` chain, so stored scores on
existing quotations need an explicit recompute.

---

## 🔒 Security & Code Standards

* **Native Model Inheritance**: Built exclusively with `_inherit` on native models to guarantee standard upgrade paths and database compatibility.
* **Security Access Control**: Standard Odoo security access matrix mapped via `security/ir.model.access.csv` for custom schedule and upsell models.
* **Safe Portal Controllers**: Counter-offers validate signature tokens, record access rules, and enforce negotiation limits.
* **High-Performance Computes**: Zero redundant database queries; relies on cached computed fields and bulk write operations.

---

## 📄 License
This project is licensed under the [LGPL-3](https://www.gnu.org/licenses/lgpl-3.0.en.html) license.
