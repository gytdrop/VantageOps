"""Smoke-test the interactive paths touched by the refactor: settings form, tier views,
bargain wizard, portal counter-offer, circuit-breaker reset and the re-score action.
"""
FAILURES = []


def check(label, condition, detail=''):
    status = 'PASS' if condition else 'FAIL'
    if not condition:
        FAILURES.append(label)
    print(f"  [{status}] {label}" + (f"  -> {detail}" if detail else ''))


print("\n" + "=" * 78)
print("UI / ACTION SMOKE TESTS")
print("=" * 78)

# --- Views render ---
for model, xmlid in [
    ('res.config.settings', 'sale.res_config_settings_view_form'),
    ('vantage.discount.tier', 'vantage_governance.view_vantage_discount_tier_form'),
    ('vantage.discount.tier', 'vantage_governance.view_vantage_discount_tier_tree'),
    ('vantage.proration.wizard', 'vantage_fulfillment.view_vantage_proration_wizard_form'),
    ('sale.order', 'sale.view_order_form'),
    ('sale.order', 'sale.view_quotation_tree'),
    ('res.partner', 'base.view_partner_form'),
    ('stock.warehouse', 'stock.view_warehouse'),
    ('crm.team', 'sales_team.crm_team_view_form'),
    ('product.template', 'product.product_template_form_view'),
]:
    try:
        env[model].get_view(env.ref(xmlid).id)
        check(f"View renders: {xmlid}", True)
    except Exception as exc:
        check(f"View renders: {xmlid}", False, str(exc)[:120])

# --- Settings round-trip ---
settings = env['res.config.settings'].create({
    'vantage_manager_risk_ceiling': 18.0,
    'vantage_stalled_days': 7,
    'vantage_max_split_legs': 4,
    'vantage_default_cadence': 'quarterly',
})
settings.execute()
cfg = env['vantage.config']
check("Settings persist to system parameters",
      cfg.get_float('manager_risk_ceiling', 0) == 18.0 and cfg.get_int('stalled_days', 0) == 7
      and cfg.get_int('max_split_legs', 0) == 4
      and cfg.get_selection('default_cadence', ('monthly', 'quarterly'), 'monthly') == 'quarterly',
      f"ceiling={cfg.get_float('manager_risk_ceiling', 0)} stalled={cfg.get_int('stalled_days', 0)} "
      f"legs={cfg.get_int('max_split_legs', 0)} cadence={cfg.get_str('default_cadence')}")

reloaded = env['res.config.settings'].create({})
check("Saved values are read back into the settings form",
      reloaded.vantage_manager_risk_ceiling == 18.0 and reloaded.vantage_stalled_days == 7,
      f"{reloaded.vantage_manager_risk_ceiling}, {reloaded.vantage_stalled_days}")

# --- Re-score action ---
try:
    result = settings.action_vantage_recompute_risk()
    check("Re-score action runs", result.get('tag') == 'display_notification',
          result['params']['message'])
except Exception as exc:
    check("Re-score action runs", False, str(exc)[:200])

try:
    action = settings.action_vantage_open_tiers()
    check("Configure Tiers button resolves its action",
          action.get('res_model') == 'vantage.discount.tier')
except Exception as exc:
    check("Configure Tiers button resolves its action", False, str(exc)[:160])

# --- Negotiation paths ---
bronze = env['vantage.discount.tier'].search([('code', '=', 'bronze')], limit=1)
partner = env['res.partner'].create({'name': 'ZZ Nego Client', 'customer_tier_id': bronze.id})
product = env['product.product'].create({'name': 'ZZ Nego Widget', 'type': 'service',
                                         'list_price': 1000.0, 'standard_price': 400.0})
order = env['sale.order'].create({
    'partner_id': partner.id,
    'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 4, 'price_unit': 1000.0})],
})
check("Bronze tier's 2-round budget flows onto the order",
      order.max_negotiation_rounds == 2, f"{order.max_negotiation_rounds} rounds")

wizard = env['vantage.bargain.wizard'].create({'order_id': order.id, 'counter_discount': 22.0})
check("Bargain wizard reads the live round budget", wizard.max_rounds == 2, f"{wizard.max_rounds}")
wizard.action_apply_pitch()
check("Pitch applies the counter discount", order.order_line[0].discount == 22.0)
check("Round counter advanced", order.negotiation_rounds == 1)
check("Risk re-routed to manager after the pitch",
      order.risk_approval_state == 'pending_manager' and order.blended_risk_score > 0,
      f"score={order.blended_risk_score} state={order.risk_approval_state}")

order.action_customer_counter_offer(counter_discount=25.0, notes='portal round 2')
check("Circuit breaker trips at the tier's 2-round limit",
      order.negotiation_rounds == 2 and order.is_negotiation_locked,
      f"rounds={order.negotiation_rounds} locked={order.is_negotiation_locked}")
try:
    order.action_customer_counter_offer(counter_discount=30.0)
    check("Third round is refused", False, "it was allowed!")
except Exception as exc:
    check("Third round is refused", 'Circuit Breaker' in str(exc))

try:
    order.action_reset_negotiation()
    check("Manager reset unlocks negotiation",
          order.negotiation_rounds == 0 and not order.is_negotiation_locked,
          f"rounds={order.negotiation_rounds} locked={order.is_negotiation_locked}")
except Exception as exc:
    check("Manager reset unlocks negotiation", False, str(exc)[:200])

# --- Bargain wizard default seeded from the tier ceiling ---
act = order.action_open_bargain_wizard()
check("Wizard opens pre-filled with the tier ceiling",
      act['context']['default_counter_discount'] == bronze.discount_ceiling,
      f"{act['context']['default_counter_discount']}%")

# --- Dashboard still computes ---
try:
    dash = env['vantage.sales.dashboard'].create({})
    dash._compute_metrics()
    check("Executive cockpit metrics compute", dash.total_deal_count >= 0,
          f"{dash.total_deal_count} deals, {dash.total_pending_approvals} pending approvals")
except Exception as exc:
    check("Executive cockpit metrics compute", False, str(exc)[:200])

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
