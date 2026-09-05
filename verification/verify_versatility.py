"""End-to-end verification of the four externalised business rules.

Run with:  odoo-bin shell -d vantage_db ... < verify_versatility.py
Everything is rolled back at the end so the demo database stays untouched.
"""
from datetime import date
from dateutil.relativedelta import relativedelta

FAILURES = []


def check(label, condition, detail=''):
    status = 'PASS' if condition else 'FAIL'
    if not condition:
        FAILURES.append(label)
    print(f"  [{status}] {label}" + (f"  -> {detail}" if detail else ''))


cfg = env['vantage.config']
Param = env['ir.config_parameter'].sudo()

print("\n" + "=" * 78)
print("1. CONFIGURABLE TIER CEILINGS (incl. per-product-category overrides)")
print("=" * 78)

services_categ = env['product.category'].create({'name': 'ZZ Test Services'})
hardware_categ = env['product.category'].create({'name': 'ZZ Test Hardware'})

platinum = env['vantage.discount.tier'].create({
    'name': 'Platinum',
    'code': 'zz_platinum',
    'discount_ceiling': 25.0,
    'manager_risk_ceiling': 30.0,
    'max_negotiation_rounds': 7,
    'category_ceiling_ids': [(0, 0, {
        'product_category_id': services_categ.id, 'discount_ceiling': 8.0,
    })],
})
check("Arbitrary new tier can be created", platinum.discount_ceiling == 25.0,
      f"Platinum ceiling={platinum.discount_ceiling}")

hw = env['product.product'].create({
    'name': 'ZZ Test Server', 'type': 'product', 'categ_id': hardware_categ.id,
    'list_price': 1000.0, 'standard_price': 600.0,
})
svc = env['product.product'].create({
    'name': 'ZZ Test Consulting', 'type': 'service', 'categ_id': services_categ.id,
    'list_price': 1000.0, 'standard_price': 400.0,
})

check("Baseline ceiling applies to un-overridden category",
      platinum.get_ceiling_for_product(hw) == 25.0,
      f"hardware -> {platinum.get_ceiling_for_product(hw)}%")
check("Category override wins over tier baseline",
      platinum.get_ceiling_for_product(svc) == 8.0,
      f"services -> {platinum.get_ceiling_for_product(svc)}%")

child_categ = env['product.category'].create({
    'name': 'ZZ Premium Consulting', 'parent_id': services_categ.id,
})
svc_child = env['product.product'].create({
    'name': 'ZZ Test Premium Consulting', 'type': 'service',
    'categ_id': child_categ.id, 'list_price': 500.0,
})
check("Override is inherited by child categories",
      platinum.get_ceiling_for_product(svc_child) == 8.0,
      f"child category -> {platinum.get_ceiling_for_product(svc_child)}%")

partner = env['res.partner'].create({'name': 'ZZ Platinum Corp', 'customer_tier_id': platinum.id})
order = env['sale.order'].create({
    'partner_id': partner.id,
    'order_line': [
        (0, 0, {'product_id': hw.id, 'product_uom_qty': 10, 'price_unit': 1000.0, 'discount': 20.0}),
        (0, 0, {'product_id': svc.id, 'product_uom_qty': 1, 'price_unit': 1000.0, 'discount': 12.0}),
    ],
})
hw_line = order.order_line.filtered(lambda l: l.product_id == hw)
svc_line = order.order_line.filtered(lambda l: l.product_id == svc)

check("20% on Hardware is inside the 25% ceiling (no breach)",
      hw_line.discount_breach == 0.0, f"breach={hw_line.discount_breach}")
check("12% on Services breaches the 8% category ceiling by 4pts",
      abs(svc_line.discount_breach - 4.0) < 0.001, f"breach={svc_line.discount_breach}")

# Expected: worst_breach=4.0, excess value = 1000*0.04 = 40 on gross 11000 -> 0.3636%
expected = round(4.0 * 0.6 + (40.0 / 11000.0 * 100.0) * 0.4, 2)
check("Blended risk score uses the category ceiling",
      abs(order.blended_risk_score - expected) < 0.02,
      f"score={order.blended_risk_score} expected={expected}")

platinum.discount_ceiling = 15.0
order.invalidate_recordset(['blended_risk_score'])
order._compute_vantage_risk()
check("Editing the tier ceiling changes the score with no code change",
      order.blended_risk_score > expected,
      f"ceiling 25%->15% moved score {expected} -> {order.blended_risk_score}")
platinum.discount_ceiling = 25.0

print("\n" + "=" * 78)
print("2. CONFIGURABLE ESCALATION THRESHOLDS")
print("=" * 78)

big_order = env['sale.order'].create({
    'partner_id': partner.id,
    'order_line': [(0, 0, {'product_id': hw.id, 'product_uom_qty': 10,
                           'price_unit': 1000.0, 'discount': 45.0})],
})
print(f"  (test order risk score = {big_order.blended_risk_score})")
check("High-discount deal is routed to the manager",
      big_order.risk_approval_state == 'pending_manager', big_order.risk_approval_state)

Param.set_param('vantage.manager_risk_ceiling', '5.0')
platinum.manager_risk_ceiling = 0.0  # fall back to the global setting
big_order.invalidate_recordset(['manager_risk_ceiling'])
check("Manager ceiling reads from Sales Settings",
      big_order._vantage_manager_risk_ceiling() == 5.0)
big_order.action_manager_approve()
check("Score above the 5.0 ceiling escalates to Finance",
      big_order.risk_approval_state == 'pending_finance', big_order.risk_approval_state)

Param.set_param('vantage.manager_risk_ceiling', '99.0')
big_order.write({'risk_approval_state': 'pending_manager'})
big_order.invalidate_recordset(['manager_risk_ceiling'])
big_order.action_manager_approve()
check("Raising the ceiling to 99 lets the manager approve alone",
      big_order.risk_approval_state == 'approved', big_order.risk_approval_state)

platinum.manager_risk_ceiling = 12.0
big_order.invalidate_recordset(['manager_risk_ceiling'])
check("Tier-level override beats the global setting",
      big_order._vantage_manager_risk_ceiling() == 12.0,
      f"tier override -> {big_order._vantage_manager_risk_ceiling()}")

Param.set_param('vantage.risk_trigger_threshold', '50.0')
clean = env['sale.order'].create({
    'partner_id': partner.id,
    'order_line': [(0, 0, {'product_id': hw.id, 'product_uom_qty': 1,
                           'price_unit': 1000.0, 'discount': 40.0})],
})
check("Raising the trigger threshold lets a discounted deal stay clean",
      clean.risk_approval_state == 'draft',
      f"score={clean.blended_risk_score} state={clean.risk_approval_state}")
Param.set_param('vantage.risk_trigger_threshold', '0.0')

print("  -- circuit breaker precedence --")
Param.set_param('vantage.default_max_negotiation_rounds', '3')
nego = env['sale.order'].create({'partner_id': partner.id})
check("Tier override drives the negotiation budget",
      nego.max_negotiation_rounds == 7, f"rounds={nego.max_negotiation_rounds}")
team = env['crm.team'].create({'name': 'ZZ Test Team', 'vantage_max_negotiation_rounds': 9})
nego.team_id = team
nego.invalidate_recordset(['max_negotiation_rounds'])
nego._compute_max_negotiation_rounds()
check("Sales team override outranks the tier",
      nego.max_negotiation_rounds == 9, f"rounds={nego.max_negotiation_rounds}")

print("\n" + "=" * 78)
print("3. DYNAMIC BILLING CADENCE + EXACT-DAY PRORATION")
print("=" * 78)

saas = env['product.product'].create({
    'name': 'ZZ Test SaaS Platform', 'type': 'service',
    'list_price': 12000.0, 'standard_price': 1000.0,
    'vantage_is_subscription': True,
    'vantage_billing_cadence': 'quarterly',
    'vantage_contract_months': 12,
    'vantage_price_basis': 'contract',
})
sub_order = env['sale.order'].create({
    'partner_id': partner.id,
    'subscription_anchor': 'calendar',
    'order_line': [(0, 0, {'product_id': saas.id, 'product_uom_qty': 1, 'price_unit': 12000.0})],
})
sub_line = sub_order.order_line[0]
sub_line.subscription_start_date = date(2026, 9, 20)

check("Cadence is inherited from the product", sub_line.billing_cadence == 'quarterly',
      sub_line.billing_cadence)
check("Contract length is inherited from the product", sub_line.contract_months == 12)
check("Calendar anchor snaps back to the quarter boundary",
      sub_line._vantage_cycle_anchor() == date(2026, 7, 1),
      str(sub_line._vantage_cycle_anchor()))
check("Full cycle amount = contract / 4 quarters",
      abs(sub_line._vantage_period_amount() - 3000.0) < 0.01,
      f"{sub_line._vantage_period_amount()}")

periods = sub_line._vantage_build_periods()
print(f"  Generated {len(periods)} quarterly cycles:")
for p in periods:
    flag = 'PRORATED' if p['is_prorated'] else 'full    '
    print(f"    {p['period_start']} -> {p['period_end']}  {flag}  "
          f"factor={p['proration_factor']:.6f}  ${p['amount']:,.2f}")

check("Mid-quarter start produces 5 cycles (partial + 3 full + partial)",
      len(periods) == 5, f"{len(periods)} cycles")
check("First cycle is prorated over exact days (20 Sep -> 30 Sep = 11/92)",
      abs(periods[0]['proration_factor'] - 11 / 92) < 1e-6,
      f"{periods[0]['proration_factor']:.6f}")
check("Last cycle is prorated too", periods[-1]['is_prorated'],
      f"{periods[-1]['proration_factor']:.6f}")
total_factor = sum(p['proration_factor'] for p in periods)
check("Proration is exact: factors sum to exactly 4 quarters",
      abs(total_factor - 4.0) < 1e-6, f"sum={total_factor:.9f}")
total_billed = sum(p['amount'] for p in periods)
check("Total billed equals the committed contract value",
      abs(total_billed - 12000.0) < 0.05, f"${total_billed:,.2f}")

# Same product, annual cadence
saas.vantage_billing_cadence = 'annual'
sub_line.invalidate_recordset(['billing_cadence'])
sub_line._compute_subscription_terms()
sub_line.subscription_start_date = date(2026, 9, 20)
annual_periods = sub_line._vantage_build_periods()
check("Switching the product to annual regenerates 2 calendar cycles",
      len(annual_periods) == 2, f"{len(annual_periods)} cycles")
check("Annual cycles also sum to exactly one contract year",
      abs(sum(p['proration_factor'] for p in annual_periods) - 1.0) < 1e-6)

# Anniversary anchor => no proration at all
saas.vantage_billing_cadence = 'monthly'
sub_order.subscription_anchor = 'service_start'
sub_line.invalidate_recordset(['billing_cadence'])
sub_line._compute_subscription_terms()
sub_line.subscription_start_date = date(2026, 9, 20)
anniv = sub_line._vantage_build_periods()
check("Anniversary anchor yields 12 whole monthly cycles, none prorated",
      len(anniv) == 12 and not any(p['is_prorated'] for p in anniv),
      f"{len(anniv)} cycles, prorated={sum(1 for p in anniv if p['is_prorated'])}")

sub_order.action_generate_billing_schedule()
check("Billing schedule rows are persisted",
      len(sub_order.billing_schedule_ids) == 12,
      f"{len(sub_order.billing_schedule_ids)} rows")

print("  -- mid-cycle seat change --")
sub_line.product_uom_qty = 10
sub_order.subscription_anchor = 'calendar'
wizard = env['vantage.proration.wizard'].create({
    'order_id': sub_order.id,
    'line_id': sub_line.id,
    'change_date': date(2026, 10, 18),
    'qty_delta': 5.0,
    'apply_qty_change': False,
})
print(f"    cycle {wizard.period_start} -> {wizard.period_end} "
      f"({wizard.period_days} days, {wizard.remaining_days} remaining)")
print(f"    {wizard.proration_explanation}")
check("Mid-cycle window resolves to the October calendar month",
      wizard.period_start == date(2026, 10, 1) and wizard.period_days == 31)
check("Exact remaining days counted (18 Oct -> 31 Oct inclusive = 14)",
      wizard.remaining_days == 14, f"{wizard.remaining_days} days")
# line subtotal = 10 seats x $12,000 = $120,000 over 12 monthly cycles => $1,000/seat/month
expected_amount = round((120000.0 / 12 / 10) * 5 * (14 / 31), 2)
check("Prorated adjustment uses exact day fraction",
      abs(wizard.prorated_amount - expected_amount) < 0.02,
      f"${wizard.prorated_amount} expected ${expected_amount}")
wizard.action_apply_proration()
adj = sub_order.billing_schedule_ids.filtered(lambda s: s.billing_type == 'proration')
check("Proration adjustment is written to the billing schedule", len(adj) == 1,
      adj.description if adj else 'missing')

print("\n" + "=" * 78)
print("4. N-WAREHOUSE AUTO-SPLIT (3+ DEPOTS)")
print("=" * 78)

Warehouse = env['stock.warehouse']
depots = []
for code, name, base, weight in [
    ('ZZA', 'ZZ Main Hub', 25.0, 1.0),
    ('ZZB', 'ZZ East Depot', 40.0, 1.5),
    ('ZZC', 'ZZ West Depot', 50.0, 2.0),
    ('ZZD', 'ZZ North Depot', 60.0, 2.5),
]:
    depots.append(Warehouse.create({
        'name': name, 'code': code,
        'base_shipping_cost': base, 'shipping_cost_weight': weight,
    }))
main_wh, east, west, north = depots

quant = env['stock.quant'].with_context(inventory_mode=True)
for wh, qty in [(main_wh, 5.0), (east, 5.0), (west, 5.0), (north, 5.0)]:
    q = quant.create({'product_id': hw.id, 'location_id': wh.lot_stock_id.id,
                      'inventory_quantity': qty})
    q.action_apply_inventory()

# Keep the other pre-existing warehouses out of the way for a deterministic assertion.
other_whs = Warehouse.search([('id', 'not in', [w.id for w in depots])])
other_whs.vantage_allow_split_source = False

Param.set_param('vantage.max_split_legs', '0')
split_order = env['sale.order'].create({
    'partner_id': partner.id,
    'warehouse_id': main_wh.id,
    'order_line': [(0, 0, {'product_id': hw.id, 'product_uom_qty': 18.0, 'price_unit': 1000.0})],
})
plan = split_order._vantage_build_fulfillment_plan()
print(f"  Demand 18 units across depots holding 5/5/5/5:")
for leg in plan['legs']:
    print(f"    {leg['warehouse'].name:18s} {leg['qty']:5.1f}u  "
          f"leg cost ${split_order._vantage_leg_cost(leg['warehouse']):,.2f}")
print(f"    shortfall={sum(plan['shortfalls'].values())}  total freight=${plan['total_cost']:,.2f}")

check("Allocation spans 4 depots, not just primary + one secondary",
      plan['shipment_count'] == 4, f"{plan['shipment_count']} legs")
check("Depots are consumed cheapest-first after the primary",
      [l['warehouse'].name for l in plan['legs']] ==
      ['ZZ Main Hub', 'ZZ East Depot', 'ZZ West Depot', 'ZZ North Depot'],
      str([l['warehouse'].name for l in plan['legs']]))
check("Quantities are allocated 5/5/5/3 against real free stock",
      [l['qty'] for l in plan['legs']] == [5.0, 5.0, 5.0, 3.0],
      str([l['qty'] for l in plan['legs']]))
check("Freight sums every leg (25 + 60 + 100 + 150)",
      abs(plan['total_cost'] - 335.0) < 0.01, f"${plan['total_cost']}")

split_order.action_split_fulfillments()
child_whs = split_order.order_line.filtered(lambda l: l.is_split_child).mapped('fulfillment_warehouse_id')
check("action_split_fulfillments creates one child line per extra depot",
      len(split_order.order_line) == 4 and len(child_whs) == 3,
      f"{len(split_order.order_line)} lines across {len(child_whs)} extra depots")
check("Split quantities are preserved end to end",
      sum(split_order.order_line.mapped('product_uom_qty')) == 18.0)

split_order.action_consolidate_backorders()
check("Consolidation merges every leg back into one line",
      len(split_order.order_line) == 1 and split_order.order_line.product_uom_qty == 18.0,
      f"{len(split_order.order_line)} line(s) x {split_order.order_line.product_uom_qty}u")

Param.set_param('vantage.max_split_legs', '2')
capped = env['sale.order'].create({
    'partner_id': partner.id,
    'warehouse_id': main_wh.id,
    'order_line': [(0, 0, {'product_id': hw.id, 'product_uom_qty': 18.0, 'price_unit': 1000.0})],
})
capped_plan = capped._vantage_build_fulfillment_plan()
check("Leg cap of 2 limits the split to 2 depots",
      capped_plan['shipment_count'] == 2, f"{capped_plan['shipment_count']} legs")
check("Uncovered demand is reported as a shortfall, not silently dropped",
      sum(capped_plan['shortfalls'].values()) == 8.0,
      f"shortfall={sum(capped_plan['shortfalls'].values())}")
Param.set_param('vantage.max_split_legs', '0')

excluded = env['sale.order'].create({
    'partner_id': partner.id,
    'warehouse_id': main_wh.id,
    'order_line': [(0, 0, {'product_id': hw.id, 'product_uom_qty': 18.0, 'price_unit': 1000.0})],
})
west.vantage_allow_split_source = False
excl_plan = excluded._vantage_build_fulfillment_plan()
check("A depot flagged out of the pool is skipped",
      west not in [l['warehouse'] for l in excl_plan['legs']],
      str([l['warehouse'].name for l in excl_plan['legs']]))

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
