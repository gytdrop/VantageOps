from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    customer_tier = fields.Selection([
        ('bronze', 'Bronze Tier (5% Baseline Ceiling)'),
        ('silver', 'Silver Tier (10% Baseline Ceiling)'),
        ('gold', 'Gold Tier (15% Baseline Ceiling)')
    ], string='Vantage Customer Tier', default='silver', tracking=True,
       help="Determines the permissible baseline discount ceiling before triggering approval workflows.")


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
    max_negotiation_rounds = fields.Integer(string='Max Negotiation Rounds', default=3)
    is_negotiation_locked = fields.Boolean(
        string='Negotiation Locked (Circuit Breaker)',
        compute='_compute_is_negotiation_locked',
        store=True
    )
    last_counter_offer = fields.Char(string='Last Counter-Offer Details', readonly=True)

    # --- Deal Health & Anomaly Engine ---
    deal_health = fields.Selection([
        ('healthy', 'Healthy'),
        ('stalled', 'Stalled (>3 Days)'),
        ('margin_bleed', 'Critical Margin Bleed')
    ], string='Deal Health Status', compute='_compute_deal_health', store=True, tracking=True)

    days_inactive = fields.Integer(string='Days Inactive', compute='_compute_deal_health', store=True)
    discount_anomaly = fields.Boolean(
        string='Discount Anomaly',
        compute='_compute_deal_health',
        store=True,
        help="Flagged if average quotation discount exceeds rep's safe threshold (>=20%)."
    )

    @api.depends('order_line.discount', 'order_line.price_subtotal', 'order_line.product_uom_qty', 'partner_id.customer_tier')
    def _compute_vantage_risk(self):
        """Dynamic Blended Risk Matrix factoring Customer Tiers (Bronze: 5%, Silver: 10%, Gold: 15%)"""
        tier_ceilings = {'bronze': 5.0, 'silver': 10.0, 'gold': 15.0}
        for order in self:
            ceiling = tier_ceilings.get(order.partner_id.customer_tier, 10.0) if order.partner_id else 10.0
            worst_breach = 0.0
            total_discount_val = 0.0
            total_gross_val = 0.0

            for line in order.order_line:
                gross = line.price_unit * line.product_uom_qty
                discount_amt = gross * (line.discount / 100.0)
                total_gross_val += gross
                total_discount_val += discount_amt

                if line.discount > ceiling:
                    worst_breach = max(worst_breach, line.discount - ceiling)

            margin_loss_pct = (total_discount_val / total_gross_val * 100.0) if total_gross_val > 0 else 0.0
            score = round((worst_breach * 0.6) + (margin_loss_pct * 0.4), 2)
            order.blended_risk_score = score

            if order.risk_approval_state not in ('approved', 'rejected', 'pending_finance'):
                if score > 0.0:
                    order.risk_approval_state = 'pending_manager'
                else:
                    order.risk_approval_state = 'draft'

    @api.depends('write_date', 'date_order', 'blended_risk_score', 'order_line.discount', 'state')
    def _compute_deal_health(self):
        now = fields.Datetime.now()
        for order in self:
            last_dt = order.write_date or order.date_order or now
            delta_days = (now - last_dt).days
            order.days_inactive = delta_days

            discounts = order.order_line.mapped('discount')
            avg_disc = (sum(discounts) / len(discounts)) if discounts else 0.0
            order.discount_anomaly = avg_disc >= 20.0

            if order.blended_risk_score > 15.0 or order.discount_anomaly:
                order.deal_health = 'margin_bleed'
            elif delta_days >= 3 and order.state in ('draft', 'sent'):
                order.deal_health = 'stalled'
            else:
                order.deal_health = 'healthy'

    @api.depends('negotiation_rounds', 'max_negotiation_rounds')
    def _compute_is_negotiation_locked(self):
        for order in self:
            order.is_negotiation_locked = order.negotiation_rounds >= order.max_negotiation_rounds

    def action_confirm(self):
        """Commercial Confirmation Interceptor"""
        for order in self:
            if order.blended_risk_score > 0 and order.risk_approval_state != 'approved':
                if order.risk_approval_state == 'pending_finance':
                    order._schedule_finance_approval_activity()
                    msg = _("⚠️ High-Risk Deal Blocked by VantageOps!\n\n"
                            "Blended Risk Score: %(score)s (> 10.0 Severe Risk)\n"
                            "This order requires 2nd-tier Finance Director sign-off before confirmation.",
                            score=order.blended_risk_score)
                else:
                    order._schedule_manager_approval_activity()
                    msg = _("⚠️ High-Risk Deal Blocked by VantageOps!\n\n"
                            "Blended Risk Score: %(score)s\n"
                            "This order requires Sales Manager approval before confirmation.\n"
                            "Review activity has been scheduled in Chatter.",
                            score=order.blended_risk_score)
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
            self.activity_schedule(
                activity_type_id=activity_type.id,
                user_id=manager.id,
                summary='Sales Manager Approval Required',
                note=f"Quotation {self.name} has a Blended Risk Score of {self.blended_risk_score} (Customer Tier: {self.partner_id.customer_tier.upper() if self.partner_id.customer_tier else 'STANDARD'})."
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
                note=f"Quotation {self.name} requires final Finance Director authorization. Blended Risk Score: {self.blended_risk_score} (> 10.0 threshold)."
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
        """Tier 1: Sales Manager Approval (Escalates to Finance if Score > 10)"""
        self.ensure_one()
        if self.blended_risk_score > 10.0:
            self.write({'risk_approval_state': 'pending_finance'})
            self._resolve_approval_activities(_("Manager approval granted. Escalated to Finance."))
            self._schedule_finance_approval_activity()
            self.message_post(body=_(
                "👔 <strong>Sales Manager Approval Granted</strong> by %s.<br/>"
                "⚠️ Blended Risk Score (%s) exceeds Tier-1 threshold (10.0). "
                "Escalated to <strong>Finance Director</strong> for final sign-off."
            ) % (self.env.user.name, self.blended_risk_score))
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

    def action_customer_counter_offer(self, line_id=None, counter_discount=0.0, notes=""):
        self.ensure_one()
        if self.is_negotiation_locked:
            raise UserError(_("Negotiation Circuit Breaker Triggered: Maximum rounds (%s) reached. Counter-offers locked.") % self.max_negotiation_rounds)

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

        # Recalculate risk & transition to appropriate approval tier
        self._compute_vantage_risk()
        if self.blended_risk_score > 0:
            if self.blended_risk_score > 10.0:
                self.risk_approval_state = 'pending_manager'
                self._schedule_manager_approval_activity()
            else:
                self.risk_approval_state = 'pending_manager'
                self._schedule_manager_approval_activity()
