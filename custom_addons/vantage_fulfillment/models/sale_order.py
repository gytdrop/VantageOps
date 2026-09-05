from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from odoo.addons.vantage_core.models.vantage_config import CADENCE_SELECTION, CADENCE_MONTHS


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    has_split_requirement = fields.Boolean(
        string='Requires Fulfillment Split',
        compute='_compute_split_requirement',
        store=True,
        help="Flagged if any line quantity exceeds primary warehouse free stock."
    )
    secondary_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Preferred Secondary Depot',
        help="Optional override forcing this depot to the front of the allocation ranking. "
             "Leave empty to let the engine pick the cheapest depots automatically."
    )

    # --- Multi-Warehouse Cost-Weighted Fulfillment Engine ---
    estimated_shipment_count = fields.Integer(
        string='Estimated Shipments',
        compute='_compute_shipping_metrics',
        store=True,
        help="Number of discrete warehouse shipments required to fulfill this quotation."
    )
    estimated_shipping_cost = fields.Float(
        string='Estimated Shipping Cost ($)',
        compute='_compute_shipping_metrics',
        store=True,
        help="Total shipping cost computed from warehouse base costs and weight factors."
    )
    fulfillment_split_summary = fields.Text(
        string='Fulfillment Split Summary',
        compute='_compute_shipping_metrics',
        store=True,
        help="Live recommendation explaining warehouse breakdown and shipment costs."
    )
    fulfillment_shortfall_qty = fields.Float(
        string='Unfulfillable Quantity',
        compute='_compute_shipping_metrics',
        store=True,
        help="Units that no configured depot can cover; these fall back to procurement."
    )
    fulfillment_plan_html = fields.Html(
        string='Depot Allocation Plan',
        compute='_compute_fulfillment_plan_html',
        sanitize=False,
        help="Leg-by-leg breakdown of the N-way allocation across regional depots."
    )
    has_split_children = fields.Boolean(
        string='Has Split Lines',
        compute='_compute_has_split_children',
        help="True if backorder split child lines currently exist on this quotation."
    )

    # --- Hybrid Billing Schedule Engine ---
    billing_schedule_ids = fields.One2many(
        'vantage.billing.schedule',
        'order_id',
        string='Billing Schedules'
    )
    billing_schedule_count = fields.Integer(
        string='Billing Schedule Count',
        compute='_compute_billing_schedule_count'
    )
    subscription_anchor = fields.Selection([
        ('service_start', 'Anniversary — cycles run from the service start date'),
        ('calendar', 'Calendar-Aligned — cycles snap to month/quarter/year boundaries'),
    ], string='Billing Cycle Anchor',
        default=lambda self: self.env['vantage.config'].get_selection(
            'subscription_anchor', ('service_start', 'calendar'), 'service_start'),
        help="Calendar alignment is what makes a mid-cycle start prorated: the first invoice "
             "only covers the days between the service start and the end of the calendar period."
    )

    # --- Smart Upsell Recommendations ---
    available_upsell_ids = fields.Many2many(
        'vantage.upsell.rule',
        string='Recommended Upsells',
        compute='_compute_available_upsells'
    )

    @api.depends('order_line.is_split_child')
    def _compute_has_split_children(self):
        for order in self:
            order.has_split_children = any(l.is_split_child for l in order.order_line)

    # ------------------------------------------------------------------
    # N-Warehouse allocation engine
    # ------------------------------------------------------------------
    def _vantage_ranked_warehouses(self):
        """Candidate depots ordered by landed shipping cost.

        The order's own warehouse always leads (its stock ships without an extra leg),
        followed by an explicit secondary override if one is set, then every remaining
        depot ranked by `base_shipping_cost x shipping_cost_weight`.
        """
        self.ensure_one()
        Warehouse = self.env['stock.warehouse']
        primary = self.warehouse_id or Warehouse.search([], limit=1)

        ranked = []
        if primary:
            ranked.append(primary)
        if self.secondary_warehouse_id and self.secondary_warehouse_id not in ranked:
            ranked.append(self.secondary_warehouse_id)

        others = Warehouse.search([
            ('vantage_allow_split_source', '=', True),
            ('id', 'not in', [w.id for w in ranked]),
        ])
        ranked.extend(others.sorted(
            key=lambda w: (w.vantage_effective_ship_cost, w.vantage_split_priority, w.id)
        ))
        return ranked

    @api.model
    def _vantage_leg_cost(self, warehouse):
        if not warehouse:
            return 25.0
        return (warehouse.base_shipping_cost or 25.0) * (warehouse.shipping_cost_weight or 1.0)

    def _vantage_free_qty(self, product, warehouse):
        """Free (unreserved) stock of a product at a specific warehouse."""
        location = warehouse.lot_stock_id if warehouse else False
        if not location or not product:
            return 0.0
        return product.with_context(location=location.id).free_qty

    def _vantage_build_fulfillment_plan(self, lines=None):
        """Greedily spread demand across every depot that can contribute.

        Unlike the old primary+secondary fork this walks the whole ranked depot list, so
        an order needing 30 units can land as 10 (Main) + 12 (East) + 8 (West). A shared
        ledger keeps two lines of the same product from claiming the same physical stock.

        Returns a dict with per-line allocations, per-warehouse legs, the total freight
        and any quantity no depot can cover.
        """
        self.ensure_one()
        if lines is None:
            lines = self.order_line.filtered(
                lambda l: l.product_id.type == 'product' and not l.is_split_child
            )

        max_legs = self.env['vantage.config'].get_int('max_split_legs', 0)
        ranked = self._vantage_ranked_warehouses()
        primary = ranked[0] if ranked else False

        ledger = {}
        allocations = {}
        shortfalls = {}
        used_warehouses = []

        for line in lines:
            needed = line.product_uom_qty
            line_allocations = []

            for warehouse in ranked:
                if needed <= 0.0:
                    break
                is_new_leg = warehouse not in used_warehouses
                if is_new_leg and max_legs and len(used_warehouses) >= max_legs:
                    # Leg budget exhausted: only already-open shipments may still contribute.
                    continue

                key = (warehouse.id, line.product_id.id)
                if key not in ledger:
                    ledger[key] = self._vantage_free_qty(line.product_id, warehouse)

                take = min(ledger[key], needed)
                if take <= 0.0:
                    continue

                ledger[key] -= take
                needed -= take
                line_allocations.append((warehouse, take))
                if is_new_leg:
                    used_warehouses.append(warehouse)

            if needed > 0.0:
                # Nothing on hand anywhere: the remainder stays on the primary leg and
                # becomes a procurement backorder once the order is confirmed.
                shortfalls[line.id] = needed
                if primary:
                    if primary not in used_warehouses:
                        used_warehouses.append(primary)
                    line_allocations.append((primary, needed))

            allocations[line.id] = line_allocations

        legs = {}
        for line_id, line_allocations in allocations.items():
            for warehouse, qty in line_allocations:
                leg = legs.setdefault(warehouse, {'warehouse': warehouse, 'qty': 0.0, 'lines': 0})
                leg['qty'] += qty
                leg['lines'] += 1

        ordered_legs = [legs[w] for w in used_warehouses if w in legs]
        total_cost = sum(self._vantage_leg_cost(leg['warehouse']) for leg in ordered_legs)

        return {
            'allocations': allocations,
            'shortfalls': shortfalls,
            'legs': ordered_legs,
            'total_cost': round(total_cost, 2),
            'shipment_count': len(ordered_legs),
            'primary': primary,
        }

    def _vantage_active_legs(self):
        """Legs implied by lines that have already been split across depots."""
        self.ensure_one()
        primary = self.warehouse_id or self.env['stock.warehouse'].search([], limit=1)
        legs = {}
        for line in self.order_line.filtered(lambda l: l.product_id.type == 'product'):
            warehouse = line.fulfillment_warehouse_id or primary
            if not warehouse:
                continue
            leg = legs.setdefault(warehouse, {'warehouse': warehouse, 'qty': 0.0, 'lines': 0})
            leg['qty'] += line.product_uom_qty
            leg['lines'] += 1
        ordered = sorted(legs.values(), key=lambda l: (
            l['warehouse'] != primary, l['warehouse'].vantage_effective_ship_cost, l['warehouse'].id
        ))
        return ordered

    @api.depends(
        'order_line.product_uom_qty', 'order_line.product_id', 'order_line.fulfillment_warehouse_id',
        'order_line.is_split_child', 'order_line.requires_split', 'warehouse_id', 'secondary_warehouse_id'
    )
    def _compute_shipping_metrics(self):
        for order in self:
            physical_lines = order.order_line.filtered(lambda l: l.product_id.type == 'product')
            if not physical_lines:
                order.estimated_shipment_count = 0
                order.estimated_shipping_cost = 0.0
                order.fulfillment_shortfall_qty = 0.0
                order.fulfillment_split_summary = "No physical shippable items in order."
                continue

            if any(l.is_split_child for l in physical_lines):
                legs = order._vantage_active_legs()
                total_cost = sum(order._vantage_leg_cost(leg['warehouse']) for leg in legs)
                breakdown = " + ".join(
                    f"{leg['warehouse'].name} {leg['qty']:g}u (${order._vantage_leg_cost(leg['warehouse']):,.2f})"
                    for leg in legs
                )
                order.estimated_shipment_count = len(legs)
                order.estimated_shipping_cost = round(total_cost, 2)
                order.fulfillment_shortfall_qty = 0.0
                order.fulfillment_split_summary = (
                    f"📦 Active Split across {len(legs)} depot(s): {breakdown} "
                    f"| Total Shipping: ${total_cost:,.2f}"
                )
                continue

            plan = order._vantage_build_fulfillment_plan(
                physical_lines.filtered(lambda l: not l.is_split_child)
            )
            shortfall = sum(plan['shortfalls'].values())
            order.estimated_shipment_count = plan['shipment_count']
            order.estimated_shipping_cost = plan['total_cost']
            order.fulfillment_shortfall_qty = shortfall

            breakdown = " + ".join(
                f"{leg['warehouse'].name} {leg['qty']:g}u (${order._vantage_leg_cost(leg['warehouse']):,.2f})"
                for leg in plan['legs']
            )
            if order.has_split_requirement and plan['shipment_count'] > 1:
                summary = (
                    f"⚠️ Recommended Split: {plan['shipment_count']} shipments — {breakdown} "
                    f"| Total Projected Shipping: ${plan['total_cost']:,.2f}"
                )
            elif plan['legs']:
                leg = plan['legs'][0]
                warehouse = leg['warehouse']
                summary = (
                    f"✅ Unified Fulfillment: 1 shipment from {warehouse.name} "
                    f"(Base: ${warehouse.base_shipping_cost:.2f} × Weight: {warehouse.shipping_cost_weight:.1f} "
                    f"= ${order._vantage_leg_cost(warehouse):,.2f})"
                )
            else:
                summary = "No depot currently holds stock for these lines."

            if shortfall > 0:
                summary += f" | ⛔ {shortfall:g} unit(s) unavailable network-wide → procurement backorder."
            order.fulfillment_split_summary = summary

    @api.depends('estimated_shipment_count', 'estimated_shipping_cost', 'order_line.product_uom_qty',
                 'order_line.fulfillment_warehouse_id', 'order_line.is_split_child')
    def _compute_fulfillment_plan_html(self):
        for order in self:
            physical_lines = order.order_line.filtered(lambda l: l.product_id.type == 'product')
            if not physical_lines:
                order.fulfillment_plan_html = '<p class="text-muted">No physical shippable items in this quotation.</p>'
                continue

            if any(l.is_split_child for l in physical_lines):
                legs = order._vantage_active_legs()
                caption = 'Active allocation'
            else:
                legs = order._vantage_build_fulfillment_plan(
                    physical_lines.filtered(lambda l: not l.is_split_child)
                )['legs']
                caption = 'Projected allocation'

            rows = []
            total = 0.0
            for index, leg in enumerate(legs, start=1):
                warehouse = leg['warehouse']
                cost = order._vantage_leg_cost(warehouse)
                total += cost
                rows.append(
                    f'<tr><td>Leg {index}</td><td><strong>{warehouse.name}</strong></td>'
                    f'<td class="text-end">{leg["qty"]:g}</td>'
                    f'<td class="text-end">{leg["lines"]}</td>'
                    f'<td class="text-end">${warehouse.base_shipping_cost:,.2f}</td>'
                    f'<td class="text-end">×{warehouse.shipping_cost_weight:g}</td>'
                    f'<td class="text-end"><strong>${cost:,.2f}</strong></td></tr>'
                )

            if not rows:
                order.fulfillment_plan_html = '<p class="text-muted">No depot currently holds stock for these lines.</p>'
                continue

            order.fulfillment_plan_html = (
                f'<table class="table table-sm">'
                f'<thead><tr><th>{caption}</th><th>Depot</th><th class="text-end">Units</th>'
                f'<th class="text-end">Lines</th><th class="text-end">Base</th>'
                f'<th class="text-end">Weight</th><th class="text-end">Leg Cost</th></tr></thead>'
                f'<tbody>{"".join(rows)}</tbody>'
                f'<tfoot><tr><th colspan="6" class="text-end">Total Freight</th>'
                f'<th class="text-end">${total:,.2f}</th></tr></tfoot></table>'
            )

    def _get_optimal_secondary_warehouse(self, physical_lines=None):
        """Cheapest depot other than the order's own warehouse.

        Retained for backwards compatibility; the allocation engine now walks the whole
        ranked list via `_vantage_ranked_warehouses`.
        """
        self.ensure_one()
        ranked = [w for w in self._vantage_ranked_warehouses() if w != self.warehouse_id]
        return ranked[0] if ranked else False

    @api.depends('order_line.product_uom_qty', 'order_line.product_id', 'warehouse_id')
    def _compute_split_requirement(self):
        """Check available free stock vs requested qty"""
        for order in self:
            order.has_split_requirement = any(line.requires_split for line in order.order_line)

    @api.depends('billing_schedule_ids')
    def _compute_billing_schedule_count(self):
        for order in self:
            order.billing_schedule_count = len(order.billing_schedule_ids)

    @api.depends('order_line.product_id')
    def _compute_available_upsells(self):
        rule_obj = self.env['vantage.upsell.rule']
        for order in self:
            prod_ids = order.order_line.mapped('product_id').ids
            matching_rules = rule_obj.search([
                ('source_product_id', 'in', prod_ids),
                ('recommended_product_id', 'not in', prod_ids)
            ])
            order.available_upsell_ids = matching_rules

    def action_split_fulfillments(self):
        """Spread stock deficits across every depot that can contribute, cheapest first."""
        for order in self:
            lines_to_split = order.order_line.filtered(
                lambda l: l.requires_split and not l.is_split_child and l.product_id.type == 'product'
            )
            if not lines_to_split:
                raise UserError(_("No stock deficit detected across line items for split."))

            plan = order._vantage_build_fulfillment_plan(lines_to_split)
            if not plan['legs']:
                raise UserError(_("No warehouse is available to source these lines. "
                                  "Check that at least one depot is flagged 'Available for Auto-Split'."))

            split_count = 0
            for line in lines_to_split:
                line_allocations = plan['allocations'].get(line.id) or []
                if not line_allocations:
                    continue

                # First allocation keeps the original line; every further depot forks a child.
                first_warehouse, first_qty = line_allocations[0]
                line.write({
                    'product_uom_qty': first_qty,
                    'fulfillment_warehouse_id': first_warehouse.id,
                    'is_split_parent': len(line_allocations) > 1,
                })

                for warehouse, qty in line_allocations[1:]:
                    order.order_line.create({
                        'order_id': order.id,
                        'product_id': line.product_id.id,
                        'product_uom_qty': qty,
                        'price_unit': line.price_unit,
                        'discount': line.discount,
                        'is_split_child': True,
                        'split_source_line_id': line.id,
                        'fulfillment_warehouse_id': warehouse.id,
                        'name': f"{line.name} (Split Leg - {warehouse.name})",
                    })
                if len(line_allocations) > 1:
                    split_count += 1

            # Keep the legacy field pointing at the first non-primary depot actually used.
            secondary = next((leg['warehouse'] for leg in plan['legs']
                              if leg['warehouse'] != plan['primary']), False)
            order.secondary_warehouse_id = secondary.id if secondary else False

            breakdown = ", ".join(
                f"{leg['warehouse'].name} ({leg['qty']:g}u @ ${order._vantage_leg_cost(leg['warehouse']):,.2f})"
                for leg in plan['legs']
            )
            shortfall = sum(plan['shortfalls'].values())
            body = (
                f"⚙️ <strong>VantageOps N-Way Fulfillment Auto-Split</strong>: {split_count} line(s) forked across "
                f"<strong>{plan['shipment_count']} depot(s)</strong> — {breakdown}. "
                f"Total freight: ${plan['total_cost']:,.2f}."
            )
            if shortfall > 0:
                body += (f"<br/>⛔ {shortfall:g} unit(s) exceed network-wide availability and remain on the "
                         f"primary leg for procurement.")
            order.message_post(body=body)

    def action_consolidate_backorders(self):
        """Consolidates backorder split child lines back into parent lines when stock arrives"""
        for order in self:
            child_lines = order.order_line.filtered(lambda l: l.is_split_child)
            if not child_lines:
                raise UserError(_("No split backorder lines to consolidate."))

            consolidated_count = 0
            for child in child_lines:
                parent = child.split_source_line_id
                if parent and parent.exists():
                    parent.product_uom_qty += child.product_uom_qty
                    parent.is_split_parent = False
                    parent.fulfillment_warehouse_id = False
                    child.unlink()
                    consolidated_count += 1
                else:
                    child.is_split_child = False

            order.secondary_warehouse_id = False
            order.message_post(
                body=f"📦 <strong>Fulfillment Backorders Consolidated</strong>: {consolidated_count} backorder line(s) merged back into primary warehouse shipment."
            )

    # ------------------------------------------------------------------
    # Hybrid billing schedule engine
    # ------------------------------------------------------------------
    def action_generate_billing_schedule(self):
        """Separate one-time charges from recurring cycles at each line's own cadence.

        Cycles are placed with real calendar arithmetic (relativedelta), so a quarterly
        plan lands on true quarter boundaries instead of 90-day approximations. When the
        order is calendar-anchored, partial first/last cycles are prorated on exact days.
        """
        self.ensure_one()
        # Remove un-invoiced schedules
        self.billing_schedule_ids.filtered(lambda s: s.state == 'scheduled').unlink()

        one_time_lines = self.order_line.filtered(lambda l: not l.is_subscription_item)
        sub_lines = self.order_line.filtered(lambda l: l.is_subscription_item)
        one_time_total = sum(one_time_lines.mapped('price_subtotal'))

        today = fields.Date.context_today(self)
        schedules = []
        seq = 1

        # 1. One-Time Hardware / Implementation Invoice
        if one_time_total > 0 or not sub_lines:
            schedules.append({
                'order_id': self.id,
                'sequence': seq,
                'billing_date': today,
                'description': 'Initial Delivery & Hardware / Setup Charges',
                'amount': one_time_total if one_time_total > 0 else self.amount_untaxed,
                'billing_type': 'one_time',
                'state': 'scheduled',
            })
            seq += 1

        # 2. Recurring cycles, per line, at the line's own cadence
        prorated_count = 0
        for line in sub_lines:
            for period in line._vantage_build_periods():
                schedules.append({
                    'order_id': self.id,
                    'sequence': seq,
                    'billing_date': period['billing_date'],
                    'description': period['description'],
                    'amount': period['amount'],
                    'billing_type': 'recurring',
                    'state': 'scheduled',
                    'source_line_id': line.id,
                    'cadence': period['cadence'],
                    'period_start': period['period_start'],
                    'period_end': period['period_end'],
                    'proration_factor': period['proration_factor'],
                    'is_prorated': period['is_prorated'],
                })
                if period['is_prorated']:
                    prorated_count += 1
                seq += 1

        if not schedules:
            raise UserError(_("Nothing to schedule: this quotation has no billable lines."))

        self.env['vantage.billing.schedule'].create(schedules)

        recurring_total = sum(s['amount'] for s in schedules if s['billing_type'] == 'recurring')
        cadences = sorted({s.get('cadence') for s in schedules if s.get('cadence')})
        cadence_labels = dict(CADENCE_SELECTION)
        cadence_txt = ", ".join(cadence_labels.get(c, c) for c in cadences) or 'n/a'
        body = (
            f"📅 <strong>Hybrid Billing Schedule Generated:</strong> {len(schedules)} milestone(s) "
            f"(One-time: ${one_time_total:,.2f}, Recurring: ${recurring_total:,.2f}). "
            f"Cadence(s): {cadence_txt}."
        )
        if prorated_count:
            body += f" {prorated_count} cycle(s) prorated on exact calendar days."
        self.message_post(body=body)

    def action_open_proration_wizard(self):
        """Open the mid-cycle seat change proration wizard."""
        self.ensure_one()
        if not self.order_line.filtered(lambda l: l.is_subscription_item):
            raise UserError(_("This quotation has no subscription lines to prorate."))
        return {
            'name': _('📐 Mid-Cycle Subscription Change'),
            'type': 'ir.actions.act_window',
            'res_model': 'vantage.proration.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    free_qty_today = fields.Float(
        string='Available Free Stock',
        compute='_compute_free_qty_today'
    )
    network_free_qty = fields.Float(
        string='Network-Wide Free Stock',
        compute='_compute_free_qty_today',
        help="Free stock summed across every depot flagged as available for auto-split."
    )
    requires_split = fields.Boolean(
        string='Stock Deficit',
        compute='_compute_requires_split',
        store=True
    )
    is_split_parent = fields.Boolean(string='Is Split Parent', default=False)
    is_split_child = fields.Boolean(string='Is Backorder Split Line', default=False)
    split_source_line_id = fields.Many2one('sale.order.line', string='Source Split Line')
    fulfillment_warehouse_id = fields.Many2one('stock.warehouse', string='Fulfillment Warehouse')
    deficit_qty = fields.Float(
        string='Deficit Quantity',
        compute='_compute_deficit_qty',
        store=True,
        help="Deficit quantity exceeding primary warehouse available stock."
    )

    margin_delta = fields.Float(
        string='Margin Delta ($)',
        compute='_compute_margin_delta',
        store=True,
        help="Net profit contribution of this line item."
    )

    # --- Subscription cadence (defaults inherited from the product, overridable per line) ---
    billing_cadence = fields.Selection(
        CADENCE_SELECTION,
        string='Billing Cadence',
        compute='_compute_subscription_terms',
        store=True,
        readonly=False,
    )
    contract_months = fields.Integer(
        string='Contract Months',
        compute='_compute_subscription_terms',
        store=True,
        readonly=False,
        help="Committed contract length. Falls back to the product setting, then to the "
             "company default in Sales Settings."
    )
    subscription_price_basis = fields.Selection([
        ('contract', 'Total Contract Value'),
        ('period', 'Amount per Billing Period'),
    ], string='Price Basis',
        compute='_compute_subscription_terms',
        store=True,
        readonly=False,
    )
    subscription_start_date = fields.Date(
        string='Service Start Date',
        compute='_compute_subscription_terms',
        store=True,
        readonly=False,
        help="First day of service. Combined with the order's cycle anchor this drives "
             "the exact-day proration of the first invoice."
    )

    @api.depends('product_id', 'product_id.vantage_billing_cadence', 'product_id.vantage_contract_months',
                 'product_id.vantage_price_basis', 'is_subscription_item',
                 'order_id.commitment_date', 'order_id.date_order')
    def _compute_subscription_terms(self):
        cfg = self.env['vantage.config']
        default_months = cfg.get_int('default_contract_months', 12)
        default_cadence = cfg.get_selection('default_cadence', dict(CADENCE_SELECTION), 'monthly')

        for line in self:
            product = line.product_id
            line.billing_cadence = (product.vantage_billing_cadence if product else False) or default_cadence
            line.contract_months = (product.vantage_contract_months if product else 0) or default_months
            line.subscription_price_basis = (product.vantage_price_basis if product else False) or 'contract'

            if not line.subscription_start_date:
                order = line.order_id
                start = order.commitment_date.date() if order.commitment_date else False
                if not start:
                    start = order.date_order.date() if order.date_order else fields.Date.context_today(line)
                line.subscription_start_date = start

    # --- Proration helpers -------------------------------------------------
    def _vantage_cadence_months(self):
        self.ensure_one()
        return CADENCE_MONTHS.get(self.billing_cadence or 'monthly', 1)

    def _vantage_service_window(self):
        """(start, end_exclusive) of the committed service period."""
        self.ensure_one()
        start = self.subscription_start_date or fields.Date.context_today(self)
        months = max(self.contract_months or 0, self._vantage_cadence_months())
        return start, start + relativedelta(months=months)

    def _vantage_cycle_anchor(self):
        """First cycle boundary at or before the service start date."""
        self.ensure_one()
        start, _end = self._vantage_service_window()
        if self.order_id.subscription_anchor != 'calendar':
            return start
        cadence_months = self._vantage_cadence_months()
        # Snap back to the start of the calendar block this date falls in.
        block_index = (start.month - 1) // cadence_months
        return start.replace(month=block_index * cadence_months + 1, day=1)

    def _vantage_period_amount(self):
        """Full (un-prorated) charge for one billing cycle."""
        self.ensure_one()
        if self.subscription_price_basis == 'period':
            return self.price_subtotal
        cadence_months = self._vantage_cadence_months()
        months = max(self.contract_months or 0, cadence_months)
        cycles = max(1, round(months / cadence_months))
        return self.price_subtotal / cycles

    def _vantage_period_bounds(self, target_date):
        """(period_start, period_end_exclusive) of the cycle containing `target_date`."""
        self.ensure_one()
        anchor = self._vantage_cycle_anchor()
        cadence_months = self._vantage_cadence_months()
        period_start = anchor
        # Stepping keeps the boundaries calendar-exact. The guard only matters when a date far
        # outside the contract is typed into the wizard, where the preview is meaningless anyway.
        guard = 0
        while period_start + relativedelta(months=cadence_months) <= target_date and guard < 600:
            period_start += relativedelta(months=cadence_months)
            guard += 1
        return period_start, period_start + relativedelta(months=cadence_months)

    @api.model
    def _vantage_proration_factor(self, period_start, period_end, service_start, service_end):
        """Exact calendar-day overlap between a billing cycle and the service window."""
        covered_start = max(period_start, service_start)
        covered_end = min(period_end, service_end)
        covered_days = (covered_end - covered_start).days
        period_days = (period_end - period_start).days
        if period_days <= 0 or covered_days <= 0:
            return 0.0, 0, max(period_days, 0)
        return covered_days / period_days, covered_days, period_days

    def _vantage_build_periods(self):
        """Every billing cycle for this subscription line, prorated on exact days."""
        self.ensure_one()
        if not self.is_subscription_item:
            return []

        service_start, service_end = self._vantage_service_window()
        cadence_months = self._vantage_cadence_months()
        cadence_label = dict(CADENCE_SELECTION).get(self.billing_cadence or 'monthly')
        full_amount = self._vantage_period_amount()

        periods = []
        period_start = self._vantage_cycle_anchor()
        guard = 0
        while period_start < service_end and guard < 600:
            guard += 1
            period_end = period_start + relativedelta(months=cadence_months)
            factor, covered_days, period_days = self._vantage_proration_factor(
                period_start, period_end, service_start, service_end
            )
            if factor <= 0.0:
                period_start = period_end
                continue

            is_prorated = factor < 1.0
            label = f"{cadence_label} — {self.product_id.display_name or self.name}"
            detail = f"{period_start.strftime('%d %b %Y')} → {(period_end - relativedelta(days=1)).strftime('%d %b %Y')}"
            if is_prorated:
                detail += f" · prorated {covered_days}/{period_days} days"

            periods.append({
                'cadence': self.billing_cadence or 'monthly',
                'period_start': period_start,
                'period_end': period_end - relativedelta(days=1),
                'billing_date': max(period_start, service_start),
                'amount': round(full_amount * factor, 2),
                'proration_factor': round(factor, 6),
                'is_prorated': is_prorated,
                'description': f"{label} ({detail})",
            })
            period_start = period_end

        for index, period in enumerate(periods, start=1):
            period['description'] = period['description'].replace(
                ' (', f" [Cycle {index}/{len(periods)}] (", 1
            )
        return periods

    @api.depends('product_id', 'order_id.warehouse_id')
    def _compute_free_qty_today(self):
        warehouses = self.env['stock.warehouse'].search([('vantage_allow_split_source', '=', True)])
        for line in self:
            if line.product_id and line.product_id.type == 'product':
                wh = line.order_id.warehouse_id
                stock_loc = wh.lot_stock_id.id if wh else False
                line.free_qty_today = line.product_id.with_context(location=stock_loc).free_qty if stock_loc else line.product_id.free_qty
                network = warehouses | wh
                line.network_free_qty = sum(
                    line.order_id._vantage_free_qty(line.product_id, w) for w in network
                )
            else:
                line.free_qty_today = line.product_uom_qty
                line.network_free_qty = line.product_uom_qty

    @api.depends('free_qty_today', 'product_uom_qty', 'is_split_child')
    def _compute_requires_split(self):
        for line in self:
            if not line.is_split_child and line.product_id.type == 'product':
                line.requires_split = line.product_uom_qty > line.free_qty_today
            else:
                line.requires_split = False

    @api.depends('free_qty_today', 'product_uom_qty', 'is_split_child')
    def _compute_deficit_qty(self):
        for line in self:
            if not line.is_split_child and line.product_id.type == 'product' and line.product_uom_qty > line.free_qty_today:
                line.deficit_qty = line.product_uom_qty - line.free_qty_today
            else:
                line.deficit_qty = 0.0

    @api.depends('price_subtotal', 'product_id', 'product_uom_qty')
    def _compute_margin_delta(self):
        for line in self:
            cost = line.product_id.standard_price * line.product_uom_qty if line.product_id else 0.0
            line.margin_delta = round(line.price_subtotal - cost, 2)


class SaleOrderOption(models.Model):
    _inherit = 'sale.order.option'

    margin_delta = fields.Float(
        string='Margin Delta ($)',
        compute='_compute_margin_delta',
        store=True,
        help="Net profit contribution of this optional product."
    )

    @api.depends('price_unit', 'product_id', 'quantity', 'discount')
    def _compute_margin_delta(self):
        for option in self:
            cost = option.product_id.standard_price * option.quantity if option.product_id else 0.0
            price_subtotal = option.price_unit * option.quantity * (1 - (option.discount or 0.0) / 100.0)
            option.margin_delta = round(price_subtotal - cost, 2)
