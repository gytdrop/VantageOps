"""Replay the documented turnkey demo against the refactored engines.

Verifies the one-click seed still provisions everything and that the README
walkthrough (Bronze 18% -> risk 13.0 -> manager -> finance -> confirm) still holds,
now on top of the configurable tier / N-way depot / cadence engines.
"""
FAILURES = []


def check(label, condition, detail=''):
    status = 'PASS' if condition else 'FAIL'
    if not condition:
        FAILURES.append(label)
    print(f"  [{status}] {label}" + (f"  -> {detail}" if detail else ''))


print("\n" + "=" * 78)
print("TURNKEY SEED + DOCUMENTED DEMO WALKTHROUGH")
print("=" * 78)

dashboard = env['vantage.sales.dashboard'].create({})
dashboard.action_load_turnkey_seed_data()
print("  seed executed")

Warehouse = env['stock.warehouse']
main_wh = Warehouse.search([('code', '=', 'MAIN')], limit=1)
east_wh = Warehouse.search([('code', '=', 'EAST')], limit=1)
west_wh = Warehouse.search([('code', '=', 'WEST')], limit=1)
check("Three regional depots provisioned", bool(main_wh and east_wh and west_wh),
      f"{main_wh.name}, {west_wh.name}, {east_wh.name}")
check("West Hub landed leg cost is $45 x 2.0 = $90",
      abs(west_wh.vantage_effective_ship_cost - 90.0) < 0.01,
      f"${west_wh.vantage_effective_ship_cost}")

server = env['product.product'].search([('name', '=', 'DealFlow Enterprise Server')], limit=1)
saas = env['product.product'].search([('name', '=', 'DealFlow360 SaaS Annual License')], limit=1)
setup = env['product.product'].search([('name', '=', 'Enterprise Setup & Deployment')], limit=1)
stock_by_wh = {
    wh.code: server.with_context(location=wh.lot_stock_id.id).free_qty
    for wh in (main_wh, west_wh, east_wh)
}
check("Server stock spread 5 / 3 / 6 across Main / West / East",
      stock_by_wh == {'MAIN': 5.0, 'WEST': 3.0, 'EAST': 6.0}, str(stock_by_wh))
check("SaaS product seeded as a quarterly subscription",
      saas.vantage_is_subscription and saas.vantage_billing_cadence == 'quarterly',
      f"is_sub={saas.vantage_is_subscription} cadence={saas.vantage_billing_cadence}")

gold = env['vantage.discount.tier'].search([('code', '=', 'gold')], limit=1)
check("Gold tier carries a Services category override at 8%",
      gold.get_ceiling_for_product(setup) == 8.0 and gold.get_ceiling_for_product(server) == 15.0,
      f"services={gold.get_ceiling_for_product(setup)}% hardware={gold.get_ceiling_for_product(server)}%")

bundle = env['sale.order.template'].search(
    [('name', '=', 'DealFlow360 Enterprise Hybrid Bundle')], limit=1)
check("Quotation template bundle present", bool(bundle))

acme = env['res.partner'].search([('name', '=', 'Acme Corp (Bronze Tier)')], limit=1)
check("Bronze demo account is linked to the configurable tier",
      acme.customer_tier_id.code == 'bronze' and acme.customer_tier_id.discount_ceiling == 5.0,
      f"{acme.customer_tier_id.name} @ {acme.customer_tier_id.discount_ceiling}%")

order = env['sale.order'].create({
    'partner_id': acme.id,
    'warehouse_id': main_wh.id,
    'order_line': [
        (0, 0, {'product_id': server.id, 'product_uom_qty': 10.0, 'price_unit': 2500.0}),
        (0, 0, {'product_id': setup.id, 'product_uom_qty': 1.0, 'price_unit': 1200.0}),
        (0, 0, {'product_id': saas.id, 'product_uom_qty': 1.0, 'price_unit': 600.0}),
    ],
})

print("\n  -- Step 4: fulfillment projection --")
print(f"    {order.fulfillment_split_summary}")
check("10 servers require a split", order.has_split_requirement)
check("Projection is a 3-depot shipment", order.estimated_shipment_count == 3,
      f"{order.estimated_shipment_count} shipments")
check("Projected freight = $25 (Main) + $90 (West) + $150 (East) = $265",
      abs(order.estimated_shipping_cost - 265.0) < 0.01, f"${order.estimated_shipping_cost}")

order.action_split_fulfillments()
legs = {l.fulfillment_warehouse_id.code: l.product_uom_qty
        for l in order.order_line if l.product_id == server}
check("Split lands 5 Main / 3 West / 2 East",
      legs == {'MAIN': 5.0, 'WEST': 3.0, 'EAST': 2.0}, str(legs))

print("\n  -- Step 6: 18% discount on a Bronze account --")
order.order_line.write({'discount': 18.0})
check("Blended risk score is 13.0 as documented",
      abs(order.blended_risk_score - 13.0) < 0.01, f"score={order.blended_risk_score}")
check("Deal is blocked pending manager approval",
      order.risk_approval_state == 'pending_manager', order.risk_approval_state)
try:
    order.action_confirm()
    check("Confirmation is blocked while unapproved", False, "confirm succeeded!")
except Exception as exc:
    check("Confirmation is blocked while unapproved", 'Blocked by VantageOps' in str(exc))

print("\n  -- Step 9: two-tier sign-off --")
print(f"    manager ceiling in force = {order._vantage_manager_risk_ceiling()}")
order.action_manager_approve()
check("Score 13.0 > 10.0 ceiling escalates to Finance",
      order.risk_approval_state == 'pending_finance', order.risk_approval_state)
order.action_finance_approve()
check("Finance sign-off unlocks the deal", order.risk_approval_state == 'approved')
order.action_confirm()
check("Order confirms after approval", order.state == 'sale', order.state)

print("\n  -- Step 8: hybrid billing at the product's own cadence --")
order.action_generate_billing_schedule()
one_time = order.billing_schedule_ids.filtered(lambda s: s.billing_type == 'one_time')
recurring = order.billing_schedule_ids.filtered(lambda s: s.billing_type == 'recurring')
for sched in order.billing_schedule_ids[:6]:
    print(f"    {sched.billing_date}  {sched.billing_type:10s} ${sched.amount:>10,.2f}  {sched.description[:64]}")
check("One-time hardware/setup charge separated", len(one_time) == 1,
      f"${one_time.amount:,.2f}" if one_time else 'missing')
check("SaaS line bills as 4 quarterly cycles, not 12 monthly",
      len(recurring) == 4, f"{len(recurring)} cycles")
check("Quarterly cycles carry the cadence tag",
      all(s.cadence == 'quarterly' for s in recurring))
check("Recurring total equals the SaaS contract value (600 x 0.82 after 18% discount)",
      abs(sum(recurring.mapped('amount')) - 492.0) < 0.05,
      f"${sum(recurring.mapped('amount')):,.2f}")

print("\n" + "=" * 78)
if FAILURES:
    print(f"RESULT: {len(FAILURES)} CHECK(S) FAILED")
    for f in FAILURES:
        print(f"  - {f}")
else:
    print("RESULT: ALL CHECKS PASSED")
print("=" * 78 + "\n")

env.cr.rollback()
print("(transaction rolled back - demo database untouched)\n")
