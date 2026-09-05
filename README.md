# 🌐 VantageOps
**Engineered by gytdrop**  
*The autonomous B2B revenue and margin governance engine for Odoo.*

## Executive Summary
VantageOps provides enterprise sales teams with the strategic high ground—delivering **Total Panoramic Visibility** to eliminate margin bleed, automate complex multi-warehouse fulfillment, and govern B2B deal negotiation in real time without human bottlenecks.

## Core Capabilities
* **Dynamic Margin Governance:** Replaces static discount rules with a live Blended Risk Score. High-risk line items aggregate into an order-wide penalty, automatically halting confirmation and routing deals to the "Approvals" dashboard.
* **Agentic Portal Negotiation:** Replaces offline haggling with a governed Customer Portal. Buyers propose counter-offers line-by-line; VantageOps intercepts, recalculates risk, and strictly limits negotiation rounds via automated circuit breakers.
* **Multi-Warehouse Execution:** Scans line items against regional warehouse stock. Automatically splits lines and generates secondary fulfillment pickings for backordered inventory, manageable directly from the "Fulfillment" module.
* **Hybrid Subscription Billing:** Natively supports both consumable hardware and recurring subscriptions on a single quotation canvas, routing properly to standard and subscription billing schedules.

## Technical Architecture
Built as a native Odoo integration suite extending `sale_management`, `stock`, `sale_stock`, and `portal`. It leverages Odoo's native ORM and `mail.activity` chatter to ensure zero database bloat and instant deployment readiness.

## Module Structure (`custom_addons/`)
- `vantage_core`: Shared foundation extending `sale.order` and `sale.order.line` with blended risk scoring and hybrid tags.
- `vantage_governance`: Akthar's module for approval routing, chatter escalations, and portal negotiation.
- `vantage_fulfillment`: Ashrith's module for multi-warehouse auto-splitting and live upsell margin contributions.

## Repositories & Resources
- **Blueprint & Instructions (Mockdeal):** `https://github.com/gytdrop/mockdeal.git`
- **Official Hackathon Delivery (VantageOps):** `https://github.com/gytdrop/VantageOps.git`
- [Execution Blueprint](EXECUTION_PLAN.md)
- [Vision & Architecture](VISION.md)
- [Interface Contract](CONTRACT.md)
- [Agent Governance & Zero-Conflict Protocol](AGENTS.md)
