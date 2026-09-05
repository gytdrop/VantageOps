# VantageOps

**Enterprise Commercial Governance & Operational Fulfillment Engine for Odoo 18**

VantageOps is an integrated, modular Odoo 18 application suite engineered to protect enterprise gross margins, automate multi-tiered approval workflows, optimize multi-warehouse order fulfillment, and streamline customer portal negotiations.

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
* **Blended Risk Scoring**: Real-time evaluation of quotation risk factors (discount depth, credit limits, and margin variance).
* **Approval State Machine**: State transitions managing standard draft orders, required internal approvals, and authorized states.
* **Hybrid Contract Awareness**: Differentiates between one-off hardware/product sales and recurring service agreements.

### 2. `vantage_governance` (Commercial Control)
* **Margin Floor Enforcement**: Prohibits confirmation (`action_confirm`) of quotations falling below approved gross margin thresholds.
* **Chatter Escalations**: Automatically dispatches `mail.activity` escalations with contextual metadata directly to finance/sales managers.
* **Portal Counter-Offer Interface**: Secure, tokenized customer negotiation interface enabling customers to submit counter-proposals within defined guardrails.
* **Circuit Breaker Logic**: Bounds portal counter-offer iterations to prevent infinite negotiation loops.

### 3. `vantage_fulfillment` (Operational Execution)
* **Multi-Warehouse Stock Splitting**: Automatically detects warehouse inventory availability across locations and splits fulfillments into dedicated warehouse pickings (`stock.picking`).
* **Backorder Routing**: Segregates immediately fulfillable lines from backordered items to optimize delivery SLAs.
* **Live Margin Delta Upsell**: Calculates and displays margin impacts for optional/accessory products directly within quotation views.

---

## 🚀 Installation & Setup

### Prerequisites
* Odoo 18.0 Community or Enterprise
* Standard Odoo dependencies: `sale_management`, `stock`, `portal`, `mail`

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

---

## 🔒 Security & Code Standards

* **Native Model Inheritance**: Built exclusively with `_inherit` on native models to guarantee standard upgrade paths and database compatibility.
* **Safe Portal Controllers**: Counter-offers validate signature tokens, record access rules, and enforce negotiation limits.
* **High-Performance Computes**: Zero redundant database queries; relies on cached computed fields and bulk write operations.

---

## 📄 License
This project is licensed under the [LGPL-3](https://www.gnu.org/licenses/lgpl-3.0.en.html) license.
