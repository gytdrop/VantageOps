from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    risk_approval_state = fields.Selection(
        selection_add=[
            ('pending_manager', 'Pending Sales Manager'),
            ('pending_finance', 'Pending Finance Director')
        ],
        ondelete={
            'pending_manager': 'set default',
            'pending_finance': 'set default',
        }
    )

    negotiation_rounds = fields.Integer(string='Negotiation Rounds', default=0, readonly=True)
    max_negotiation_rounds = fields.Integer(
        string='Max Negotiation Rounds',
        compute='_compute_max_negotiation_rounds',
        store=True,
        readonly=False,
        help="Circuit breaker budget for this deal. Defaults to the sales team override, then "
             "the customer tier override, then the global value in Sales Settings — and can "
             "still be overridden by hand on this quotation."
    )
    is_negotiation_locked = fields.Boolean(
        string='Negotiation Locked (Circuit Breaker)',
        compute='_compute_is_negotiation_locked',
        store=True
    )
    last_counter_offer = fields.Char(string='Last Counter-Offer Details', readonly=True)
    partner_customer_tier_id = fields.Many2one(
        'vantage.discount.tier',
        related='partner_id.customer_tier_id',
        readonly=False,
        string='Customer Tier',
        help="Determines the permissible discount ceiling before triggering approval workflows."
    )

    # --- Live policy resolution (tier overrides > Sales Settings defaults) ---
    tier_discount_ceiling = fields.Float(
        string='Baseline Discount Ceiling (%)',
        compute='_compute_governance_policy',
        help="Discount ceiling for this customer's tier. Individual product categories may "
             "carry a narrower ceiling."
    )
    manager_risk_ceiling = fields.Float(
        string='Manager Approval Ceiling',
        compute='_compute_governance_policy',
        help="Highest blended risk score the Sales Manager may sign off before the deal "
             "escalates to the Finance Director."
    )
    governance_policy_summary = fields.Char(
        string='Applied Governance Policy',
        compute='_compute_governance_policy'
    )

    # --- Deal Health & Anomaly Engine ---
    deal_health = fields.Selection([
        ('healthy', 'Healthy'),
        ('stalled', 'Stalled'),
        ('margin_bleed', 'Critical Margin Bleed')
    ], string='Deal Health Status', compute='_compute_deal_health', store=True, tracking=True)

    days_inactive = fields.Integer(string='Days Inactive', compute='_compute_deal_health', store=True)
    discount_anomaly = fields.Boolean(
        string='Discount Anomaly',
        compute='_compute_deal_health',
        store=True,
        help="Flagged when the average quotation discount exceeds the anomaly threshold "
             "configured in Sales Settings."
    )

    # ------------------------------------------------------------------
    # Policy resolution
    # ------------------------------------------------------------------
    def _vantage_manager_risk_ceiling(self):
        """Escalation boundary between Sales Manager and Finance Director."""
        self.ensure_one()
        tier_override = self.partner_id.customer_tier_id.manager_risk_ceiling
        if tier_override > 0.0:
            return tier_override
        return self.env['vantage.config'].get_float('manager_risk_ceiling', 10.0)

    def _vantage_risk_trigger(self):
        """Score above which a deal needs commercial sign-off."""
        return self.env['vantage.config'].get_float('risk_trigger_threshold', 0.0)

    @api.depends('partner_id.customer_tier_id',
                 'partner_id.customer_tier_id.discount_ceiling',
                 'partner_id.customer_tier_id.manager_risk_ceiling')
    def _compute_governance_policy(self):
        cfg = self.env['vantage.config']
        fallback_ceiling = cfg.get_float('default_discount_ceiling', 10.0)
        fallback_manager = cfg.get_float('manager_risk_ceiling', 10.0)
        for order in self:
            tier = order.partner_id.customer_tier_id
            order.tier_discount_ceiling = tier.discount_ceiling if tier else fallback_ceiling
            order.manager_risk_ceiling = tier.manager_risk_ceiling or fallback_manager
            overrides = len(tier.category_ceiling_ids) if tier else 0
            order.governance_policy_summary = _(
                "%(tier)s — baseline ceiling %(ceiling)g%%, %(overrides)s category override(s). "
                "Manager may approve up to %(manager)g points; above that the Finance Director signs off.",
                tier=tier.name if tier else _('No tier (fallback policy)'),
                ceiling=order.tier_discount_ceiling,
                overrides=overrides,
                manager=order.manager_risk_ceiling,
            )

    @api.depends('partner_id.customer_tier_id',
                 'partner_id.customer_tier_id.max_negotiation_rounds',
                 'team_id', 'team_id.vantage_max_negotiation_rounds')
    def _compute_max_negotiation_rounds(self):
        default_rounds = self.env['vantage.config'].get_int('default_max_negotiation_rounds', 3)
        for order in self:
            team_override = order.team_id.vantage_max_negotiation_rounds or 0
            tier_override = order.partner_id.customer_tier_id.max_negotiation_rounds or 0
            order.max_negotiation_rounds = team_override or tier_override or default_rounds

    # ------------------------------------------------------------------
    # Risk engine
    # ------------------------------------------------------------------
    @api.depends('order_line.discount', 'order_line.price_unit', 'order_line.product_uom_qty',
                 'order_line.product_id', 'order_line.product_id.categ_id',
                 'partner_id.customer_tier_id',
                 'partner_id.customer_tier_id.discount_ceiling',
                 'partner_id.customer_tier_id.category_ceiling_ids.discount_ceiling',
                 'partner_id.customer_tier_id.category_ceiling_ids.product_category_id')
    def _compute_vantage_risk(self):
        """Blended Risk Matrix driven by the configurable tier policy.

        Each line is measured against the ceiling of its own product category (falling back
        to the tier baseline, then to the global fallback ceiling). Discounts inside the
        ceiling are free of charge; only the excess is penalised.
        """
        cfg = self.env['vantage.config']
        fallback_ceiling = cfg.get_float('default_discount_ceiling', 10.0)
        breach_weight = cfg.get_float('breach_weight', 0.6)
        margin_loss_weight = cfg.get_float('margin_loss_weight', 0.4)
        trigger = cfg.get_float('risk_trigger_threshold', 0.0)

        for order in self:
            tier = order.partner_id.customer_tier_id
            worst_breach = 0.0
            total_excess_discount_val = 0.0
            total_gross_val = 0.0

            for line in order.order_line:
                gross = line.price_unit * line.product_uom_qty
                total_gross_val += gross

                ceiling = tier.get_ceiling_for_product(line.product_id) if tier else fallback_ceiling
                if line.discount > ceiling:
                    breach = line.discount - ceiling
                    worst_breach = max(worst_breach, breach)
                    total_excess_discount_val += gross * (breach / 100.0)

            if worst_breach > 0.0 and total_gross_val > 0.0:
                excess_margin_loss_pct = (total_excess_discount_val / total_gross_val * 100.0)
                score = round((worst_breach * breach_weight) + (excess_margin_loss_pct * margin_loss_weight), 2)
            else:
                score = 0.0

            order.blended_risk_score = score

            if order.risk_approval_state not in ('approved', 'rejected'):
                order.risk_approval_state = 'pending_manager' if score > trigger else 'draft'

    @api.depends('write_date', 'date_order', 'blended_risk_score', 'order_line.discount', 'state')
    def _compute_deal_health(self):
        cfg = self.env['vantage.config']
        stalled_days = cfg.get_int('stalled_days', 3)
        bleed_threshold = cfg.get_float('margin_bleed_threshold', 15.0)
        anomaly_threshold = cfg.get_float('discount_anomaly_threshold', 20.0)

        now = fields.Datetime.now()
        for order in self:
            last_dt = order.write_date or order.date_order or now
            delta_days = (now - last_dt).days
            order.days_inactive = delta_days

            discounts = order.order_line.mapped('discount')
            avg_disc = (sum(discounts) / len(discounts)) if discounts else 0.0
            order.discount_anomaly = avg_disc >= anomaly_threshold

            if order.blended_risk_score > bleed_threshold or order.discount_anomaly:
                order.deal_health = 'margin_bleed'
            elif delta_days >= stalled_days and order.state in ('draft', 'sent'):
                order.deal_health = 'stalled'
            else:
                order.deal_health = 'healthy'

    @api.depends('negotiation_rounds', 'max_negotiation_rounds')
    def _compute_is_negotiation_locked(self):
        for order in self:
            order.is_negotiation_locked = order.negotiation_rounds >= order.max_negotiation_rounds

    # ------------------------------------------------------------------
    # Approval workflow
    # ------------------------------------------------------------------
    def action_confirm(self):
        """Commercial Confirmation Interceptor"""
        for order in self:
            if order.blended_risk_score > order._vantage_risk_trigger() and order.risk_approval_state != 'approved':
                if order.risk_approval_state == 'pending_finance':
                    order._schedule_finance_approval_activity()
                    msg = _("⚠️ High-Risk Deal Blocked by VantageOps!\n\n"
                            "Blended Risk Score: %(score)s (above the %(ceiling)g point Manager ceiling)\n"
                            "This order requires 2nd-tier Finance Director sign-off before confirmation.",
                            score=order.blended_risk_score,
                            ceiling=order._vantage_manager_risk_ceiling())
                else:
                    order._schedule_manager_approval_activity()
                    msg = _("⚠️ High-Risk Deal Blocked by VantageOps!\n\n"
                            "Blended Risk Score: %(score)s (tier ceiling: %(ceiling)g%%)\n"
                            "This order requires Sales Manager approval before confirmation.\n"
                            "Review activity has been scheduled in Chatter.",
                            score=order.blended_risk_score,
                            ceiling=order.tier_discount_ceiling)
                raise UserError(msg)
        return super().action_confirm()

    def _schedule_manager_approval_activity(self):
        self.ensure_one()
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        manager = self.team_id.user_id or self.user_id or self.env.ref('base.user_admin')

        existing = self.env['mail.activity'].search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('summary', 'like', 'Manager Approval Required')
        ], limit=1)

        if not existing and activity_type:
            tier_name = self.partner_id.customer_tier_id.name or 'Unclassified'
            self.activity_schedule(
                activity_type_id=activity_type.id,
                user_id=manager.id,
                summary='Sales Manager Approval Required',
                note=(f"Quotation {self.name} has a Blended Risk Score of {self.blended_risk_score} "
                      f"(Customer Tier: {tier_name}, baseline ceiling {self.tier_discount_ceiling:g}%).")
            )

    def _schedule_finance_approval_activity(self):
        self.ensure_one()
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        finance_user = self.env.ref('base.user_admin')

        existing = self.env['mail.activity'].search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('summary', 'like', 'Finance Director Approval Required')
        ], limit=1)

        if not existing and activity_type:
            self.activity_schedule(
                activity_type_id=activity_type.id,
                user_id=finance_user.id,
                summary='Finance Director Approval Required (Tier-2)',
                note=(f"Quotation {self.name} requires final Finance Director authorization. "
                      f"Blended Risk Score: {self.blended_risk_score} "
                      f"(above the {self._vantage_manager_risk_ceiling():g} point Manager ceiling).")
            )

    def _resolve_approval_activities(self, feedback_msg):
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('summary', 'in', ['Sales Manager Approval Required', 'Finance Director Approval Required (Tier-2)', 'High-Risk Deal Approval Required'])
        ])
        if activities:
            activities.action_feedback(feedback=feedback_msg)

    def action_manager_approve(self):
        """Tier 1: Sales Manager Approval (escalates when the score exceeds the manager ceiling)"""
        self.ensure_one()
        ceiling = self._vantage_manager_risk_ceiling()
        if self.blended_risk_score > ceiling:
            self.write({'risk_approval_state': 'pending_finance'})
            self._resolve_approval_activities(_("Manager approval granted. Escalated to Finance."))
            self._schedule_finance_approval_activity()
            self.message_post(body=_(
                "👔 <strong>Sales Manager Approval Granted</strong> by %s.<br/>"
                "⚠️ Blended Risk Score (%s) exceeds the Tier-1 threshold (%g). "
                "Escalated to <strong>Finance Director</strong> for final sign-off."
            ) % (self.env.user.name, self.blended_risk_score, ceiling))
        else:
            self.write({'risk_approval_state': 'approved'})
            self._resolve_approval_activities(_("Sales Manager approval granted by %s.") % self.env.user.name)
            self.message_post(body=_("✅ <strong>Commercial Approval Granted</strong> by Sales Manager %s. Deal unlocked for confirmation.") % self.env.user.name)

    def action_finance_approve(self):
        """Tier 2: Finance Director Final Approval"""
        self.ensure_one()
        self.write({'risk_approval_state': 'approved'})
        self._resolve_approval_activities(_("Finance Director approval granted by %s.") % self.env.user.name)
        self.message_post(body=_("🏛️ <strong>Finance Director Approval Granted</strong> by %s. Deal unlocked for confirmation.") % self.env.user.name)

    def action_manager_reject(self):
        """Rejects deal at any tier"""
        self.ensure_one()
        self.write({'risk_approval_state': 'rejected'})
        self._resolve_approval_activities(_("Deal rejected by %s.") % self.env.user.name)
        self.message_post(body=_("❌ <strong>Deal Rejected</strong> by %s due to margin/risk constraints.") % self.env.user.name)

    def action_nudge_rep(self):
        """Automated Rep Escalation for Stalled Quotes"""
        self.ensure_one()
        rep = self.user_id or self.env.user
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if activity_type:
            self.activity_schedule(
                activity_type_id=activity_type.id,
                user_id=rep.id,
                summary='⚠️ Stalled Deal Follow-Up Required',
                note=f"Quotation {self.name} has been stalled for {self.days_inactive} days. Please follow up with client {self.partner_id.name} immediately."
            )
        self.message_post(body=f"⚡ <strong>Rep Nudge Dispatched:</strong> Automated reminder sent to {rep.name} for inactive quote ({self.days_inactive} days stalled).")

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            if order.partner_id:
                order.message_subscribe(partner_ids=[order.partner_id.id])
        return orders

    def write(self, vals):
        res = super().write(vals)
        if 'partner_id' in vals:
            for order in self:
                if order.partner_id:
                    order.message_subscribe(partner_ids=[order.partner_id.id])
        return res

    # ------------------------------------------------------------------
    # Negotiation / circuit breaker
    # ------------------------------------------------------------------
    def action_open_bargain_wizard(self):
        """Open the Deal Negotiation & Bargain Pitch Wizard"""
        self.ensure_one()
        if self.is_negotiation_locked:
            raise UserError(_("Negotiation Circuit Breaker Triggered: Maximum rounds (%s) reached. Counter-offers locked.") % self.max_negotiation_rounds)
        if not self.order_line:
            raise UserError(_("Please add at least one product line to the quotation before pitching a discount or bargaining."))
        return {
            'name': _('🤝 Deal Negotiation & Bargain Pitch'),
            'type': 'ir.actions.act_window',
            'res_model': 'vantage.bargain.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_counter_discount': self.tier_discount_ceiling,
            }
        }

    def action_view_customer_portal(self):
        """Open customer portal view in new browser tab for live customer negotiation / preview"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.get_portal_url(),
            'target': 'new',
        }

    def action_reset_negotiation(self):
        """Manager override to reset negotiation circuit breaker"""
        self.ensure_one()
        self.negotiation_rounds = 0
        self.is_negotiation_locked = False
        self.message_post(body=_("🔓 <strong>Negotiation Reset:</strong> Circuit breaker reset by manager. New negotiation rounds permitted."))

    def _vantage_route_approval(self):
        """Send the deal back through the approval workflow after terms changed."""
        self.ensure_one()
        if self.blended_risk_score <= self._vantage_risk_trigger():
            return
        if self.risk_approval_state == 'pending_finance':
            self._schedule_finance_approval_activity()
        else:
            self.risk_approval_state = 'pending_manager'
            self._schedule_manager_approval_activity()

    def action_customer_counter_offer(self, line_id=None, counter_discount=0.0, notes=""):
        self.ensure_one()
        if self.is_negotiation_locked:
            raise UserError(_("Negotiation Circuit Breaker Triggered: Maximum rounds (%s) reached. Counter-offers locked.") % self.max_negotiation_rounds)

        if not self.order_line:
            raise UserError(_("Cannot submit a counter-offer on a quotation without product lines. Please add items to the quotation first."))

        self.negotiation_rounds += 1

        if line_id:
            line = self.order_line.filtered(lambda l: l.id == int(line_id))
            if line:
                old_disc = line.discount
                line.discount = counter_discount
                msg = f"Customer proposed counter-discount on {line.product_id.name}: {old_disc}% ➔ {counter_discount}%. Notes: {notes}"
        else:
            for l in self.order_line:
                l.discount = counter_discount
            msg = f"Customer proposed order-wide counter-discount of {counter_discount}%. Notes: {notes}"

        self.last_counter_offer = msg
        self.message_post(body=f"🤝 <strong>Portal Counter-Offer (Round {self.negotiation_rounds}/{self.max_negotiation_rounds})</strong>: {msg}")

        # Recalculate risk & re-enter the approval workflow at the right tier
        self._compute_vantage_risk()
        self._vantage_route_approval()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    tier_discount_ceiling = fields.Float(
        string='Allowed Discount (%)',
        compute='_compute_tier_discount_ceiling',
        help="Ceiling that applies to this line: the customer tier's product-category override "
             "if one exists, otherwise the tier baseline."
    )
    discount_breach = fields.Float(
        string='Discount Breach (%)',
        compute='_compute_tier_discount_ceiling',
        help="Percentage points granted beyond the allowed ceiling for this line."
    )

    @api.depends('discount', 'product_id', 'product_id.categ_id',
                 'order_id.partner_id.customer_tier_id',
                 'order_id.partner_id.customer_tier_id.discount_ceiling',
                 'order_id.partner_id.customer_tier_id.category_ceiling_ids.discount_ceiling')
    def _compute_tier_discount_ceiling(self):
        fallback = self.env['vantage.config'].get_float('default_discount_ceiling', 10.0)
        for line in self:
            tier = line.order_id.partner_id.customer_tier_id
            ceiling = tier.get_ceiling_for_product(line.product_id) if tier else fallback
            line.tier_discount_ceiling = ceiling
            line.discount_breach = max(0.0, line.discount - ceiling)
