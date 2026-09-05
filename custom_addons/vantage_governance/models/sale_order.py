from odoo import models, fields, api, _
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    negotiation_rounds = fields.Integer(string='Negotiation Rounds', default=0, readonly=True)
    max_negotiation_rounds = fields.Integer(string='Max Negotiation Rounds', default=3)
    is_negotiation_locked = fields.Boolean(
        string='Negotiation Locked (Circuit Breaker)',
        compute='_compute_is_negotiation_locked',
        store=True
    )
    last_counter_offer = fields.Char(string='Last Counter-Offer Details', readonly=True)

    @api.depends('negotiation_rounds', 'max_negotiation_rounds')
    def _compute_is_negotiation_locked(self):
        for order in self:
            order.is_negotiation_locked = order.negotiation_rounds >= order.max_negotiation_rounds

    def action_confirm(self):
        """Task 1: Commercial Governance Block"""
        for order in self:
            if order.blended_risk_score > 0 and order.risk_approval_state != 'approved':
                order._schedule_manager_approval_activity()
                raise UserError(
                    _("⚠️ High-Risk Deal Blocked by VantageOps!\n\n"
                      "Blended Risk Score: %(score)s\n"
                      "This order cannot be confirmed without Commercial Director approval.\n"
                      "An approval request activity has been scheduled in Chatter.",
                      score=order.blended_risk_score)
                )
        return super().action_confirm()

    def _schedule_manager_approval_activity(self):
        self.ensure_one()
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        manager = self.team_id.user_id or self.user_id or self.env.ref('base.user_admin')

        existing = self.env['mail.activity'].search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('user_id', '=', manager.id),
            ('summary', '=', 'High-Risk Deal Approval Required')
        ], limit=1)

        if not existing and activity_type:
            self.activity_schedule(
                activity_type_id=activity_type.id,
                user_id=manager.id,
                summary='High-Risk Deal Approval Required',
                note=f"Quotation {self.name} has a Blended Risk Score of {self.blended_risk_score}. Review discounts and approve/reject."
            )

    def action_manager_approve(self):
        """Manager approves deal despite risk score"""
        self.ensure_one()
        self.write({'risk_approval_state': 'approved'})
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('summary', '=', 'High-Risk Deal Approval Required')
        ])
        activities.action_feedback(feedback=_("Commercial approval granted by %s.") % self.env.user.name)
        self.message_post(body=_("✅ <strong>Commercial Approval Granted</strong> by %s. Deal unlocked for confirmation.") % self.env.user.name)

    def action_manager_reject(self):
        """Manager rejects deal"""
        self.ensure_one()
        self.write({'risk_approval_state': 'rejected'})
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'sale.order'),
            ('res_id', '=', self.id),
            ('summary', '=', 'High-Risk Deal Approval Required')
        ])
        activities.action_feedback(feedback=_("Deal rejected by %s due to excessive risk.") % self.env.user.name)
        self.message_post(body=_("❌ <strong>Deal Rejected</strong> by %s due to margin/discount concerns.") % self.env.user.name)

    def action_customer_counter_offer(self, line_id=None, counter_discount=0.0, notes=""):
        """Task 3: Intercepts portal counter, recalculates risk, logs to chatter, enforces circuit-breaker"""
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

        # Recalculate risk
        self._compute_vantage_risk()
        if self.blended_risk_score > 0:
            self.risk_approval_state = 'pending_approval'
            self._schedule_manager_approval_activity()
