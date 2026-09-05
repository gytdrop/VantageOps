import uuid
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class DealflowDiscountTier(models.Model):
    _name = 'dealflow.discount.tier'
    _description = 'Customer Tier & Category Discount Ceilings'

    name = fields.Char(string='Rule Name', compute='_compute_name', store=True)
    customer_tier = fields.Selection([
        ('bronze', 'Bronze'),
        ('silver', 'Silver'),
        ('gold', 'Gold')
    ], string='Customer Tier', required=True, default='bronze')
    category_type = fields.Selection([
        ('hardware', 'Hardware'),
        ('service', 'Service'),
        ('subscription', 'Subscription')
    ], string='Category Type', required=True, default='hardware')
    max_discount_allowed = fields.Float(string='Max Allowed Discount (%)', required=True, default=5.0)
    manager_approval_threshold = fields.Float(string='Manager Approval Max (%)', default=15.0)
    finance_approval_threshold = fields.Float(string='Requires Finance Above (%)', default=15.0)

    _sql_constraints = [
        ('tier_category_uniq', 'unique(customer_tier, category_type)', 
         'A discount ceiling rule already exists for this Customer Tier and Category!')
    ]

    @api.depends('customer_tier', 'category_type', 'max_discount_allowed')
    def _compute_name(self):
        for record in self:
            record.name = f"{record.customer_tier.title()} - {record.category_type.title()} (Max {record.max_discount_allowed}%)"


class DealflowApprovalLog(models.Model):
    _name = 'dealflow.approval.log'
    _description = 'Immutable Approval Audit Log'
    _order = 'create_date desc'

    quote_id = fields.Many2one('dealflow.quote', string='Quotation', required=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', string='Action By', default=lambda self: self.env.user, required=True)
    action = fields.Selection([
        ('requested', 'Approval Requested'),
        ('manager_approved', 'Sales Manager Approved'),
        ('finance_approved', 'Finance Approved'),
        ('rejected', 'Discount Rejected'),
        ('counter_proposed', 'Customer Counter Proposed')
    ], string='Action Taken', required=True)
    reason = fields.Text(string='Remarks / Reason', default='Standard workflow action')
    risk_score = fields.Float(string='Blended Risk Score at Action')
    create_date = fields.Datetime(string='Timestamp', readonly=True)


class DealflowDealHealth(models.Model):
    _name = 'dealflow.deal.health'
    _description = 'Deal Health and Anomaly Settings'

    name = fields.Char(string='Policy Name', default='Standard Deal Health Policy')
    stalled_days_threshold = fields.Integer(string='Stalled Inactivity Threshold (Days)', default=3)
    discount_anomaly_threshold = fields.Float(string='Anomaly Deviation vs Rep Avg (%)', default=5.0)


class DealflowQuoteFeatureA(models.Model):
    _inherit = 'dealflow.quote'

    blended_risk_score = fields.Float(string='Blended Risk Score', default=0.0, readonly=True)
    risk_level = fields.Selection([
        ('low', 'Low (Auto-Approved)'),
        ('medium', 'Medium (Sales Manager Only)'),
        ('high', 'High (Sales Manager + Finance)')
    ], string='Risk Level', default='low', readonly=True)
    requires_manager_approval = fields.Boolean(string='Requires Manager Approval', default=False, readonly=True)
    requires_finance_approval = fields.Boolean(string='Requires Finance Approval', default=False, readonly=True)
    approval_state = fields.Selection([
        ('none', 'Not Submitted'),
        ('pending_manager', 'Pending Sales Manager'),
        ('pending_finance', 'Pending Finance'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], string='Approval State', default='none', readonly=True)

    approval_log_ids = fields.One2many('dealflow.approval.log', 'quote_id', string='Approval Audit Logs')

    portal_token = fields.Char(string='Portal Negotiation Token', copy=False)
    portal_counter_discount = fields.Float(string='Customer Proposed Counter (%)', readonly=True)
    portal_counter_notes = fields.Text(string='Customer Counter Remarks', readonly=True)

    is_stalled = fields.Boolean(string='Stalled Deal', compute='_compute_deal_health', store=True)
    days_inactive = fields.Integer(string='Days Inactive', compute='_compute_deal_health', store=True)
    discount_anomaly = fields.Boolean(string='Discount Anomaly Detected', compute='_compute_deal_health', store=True)

    @api.depends('date_order', 'write_date', 'line_ids.discount', 'user_id')
    def _compute_deal_health(self):
        now = fields.Datetime.now()
        for quote in self:
            last_date = quote.write_date or quote.date_order or now
            diff_days = (now - last_date).days
            quote.days_inactive = diff_days
            quote.is_stalled = diff_days >= 3 and quote.state in ('draft', 'under_negotiation', 'pending_manager', 'pending_finance')

            # Anomaly detection: compare avg discount with rep's historical deals
            avg_quote_discount = (sum(line.discount for line in quote.line_ids) / len(quote.line_ids)) if quote.line_ids else 0.0
            historical_quotes = self.search([
                ('user_id', '=', quote.user_id.id),
                ('id', '!=', quote.id if quote.id else 0),
                ('state', 'in', ('approved', 'confirmed', 'done'))
            ], limit=20)
            
            if historical_quotes:
                hist_discounts = [
                    l.discount for q in historical_quotes for l in q.line_ids
                ]
                hist_avg = (sum(hist_discounts) / len(hist_discounts)) if hist_discounts else 5.0
                quote.discount_anomaly = (avg_quote_discount - hist_avg) > 5.0
            else:
                quote.discount_anomaly = avg_quote_discount > 15.0

    def action_compute_blended_risk(self):
        """
        Computes the Blended Discount Risk Score:
        1. Checks each line against its Customer Tier + Category Ceiling.
        2. Measures single worst-line breach.
        3. Measures cumulative order margin loss across all lines.
        4. Blended Score = (Worst Line Breach * 0.6) + (Cumulative Margin Loss % * 0.4)
        """
        TierModel = self.env['dealflow.discount.tier']
        # Default fallback ceilings if not configured
        default_ceilings = {
            ('bronze', 'hardware'): 5.0, ('bronze', 'service'): 3.0, ('bronze', 'subscription'): 5.0,
            ('silver', 'hardware'): 10.0, ('silver', 'service'): 7.0, ('silver', 'subscription'): 8.0,
            ('gold', 'hardware'): 15.0, ('gold', 'service'): 10.0, ('gold', 'subscription'): 12.0
        }

        for quote in self:
            worst_breach = 0.0
            total_discount_dollars = 0.0
            total_gross_dollars = 0.0

            for line in quote.line_ids:
                tier_rule = TierModel.search([
                    ('customer_tier', '=', quote.partner_tier),
                    ('category_type', '=', line.category_type)
                ], limit=1)
                allowed_limit = tier_rule.max_discount_allowed if tier_rule else default_ceilings.get((quote.partner_tier, line.category_type), 5.0)

                breach = max(0.0, line.discount - allowed_limit)
                if breach > worst_breach:
                    worst_breach = breach

                gross = line.quantity * line.price_unit
                total_gross_dollars += gross
                total_discount_dollars += gross * (line.discount / 100.0)

            margin_loss_pct = (total_discount_dollars / total_gross_dollars * 100.0) if total_gross_dollars > 0 else 0.0
            score = round((worst_breach * 0.6) + (margin_loss_pct * 0.4), 2)

            quote.blended_risk_score = score
            if score <= 0.0:
                quote.risk_level = 'low'
                quote.requires_manager_approval = False
                quote.requires_finance_approval = False
            elif score <= 10.0:
                quote.risk_level = 'medium'
                quote.requires_manager_approval = True
                quote.requires_finance_approval = False
            else:
                quote.risk_level = 'high'
                quote.requires_manager_approval = True
                quote.requires_finance_approval = True

    def action_submit_approval(self):
        self.ensure_one()
        self.action_compute_blended_risk()

        if self.risk_level == 'low':
            self.write({
                'state': 'approved',
                'approval_state': 'approved'
            })
            self._create_approval_log('requested', f"Auto-approved (Blended Risk Score {self.blended_risk_score} within limits).")
        elif self.risk_level == 'medium':
            self.write({
                'state': 'pending_manager',
                'approval_state': 'pending_manager'
            })
            self._create_approval_log('requested', f"Sent to Sales Manager for review (Risk Score: {self.blended_risk_score}).")
        else:
            self.write({
                'state': 'pending_manager',
                'approval_state': 'pending_manager'
            })
            self._create_approval_log('requested', f"High risk deal sent to Sales Manager + Finance (Risk Score: {self.blended_risk_score}).")

    def action_approve_manager(self):
        self.ensure_one()
        if self.requires_finance_approval:
            self.write({
                'state': 'pending_finance',
                'approval_state': 'pending_finance'
            })
            self._create_approval_log('manager_approved', "Sales Manager approved. Escalated to Finance.")
        else:
            self.write({
                'state': 'approved',
                'approval_state': 'approved'
            })
            self._create_approval_log('manager_approved', "Sales Manager signed off. Deal approved.")

    def action_approve_finance(self):
        self.ensure_one()
        self.write({
            'state': 'approved',
            'approval_state': 'approved'
        })
        self._create_approval_log('finance_approved', "Finance sign-off complete. Deal fully approved.")

    def action_reject(self, reason="Discount exceeds permissible margin guidelines."):
        self.ensure_one()
        self.write({
            'state': 'rejected',
            'approval_state': 'rejected'
        })
        self._create_approval_log('rejected', reason)

    def action_generate_portal_link(self):
        self.ensure_one()
        if not self.portal_token:
            self.portal_token = str(uuid.uuid4())[:16]
        self.write({'state': 'under_negotiation'})
        return {
            'type': 'ir.actions.act_url',
            'url': f"/dealflow/portal/{self.portal_token}",
            'target': 'new',
        }

    def action_apply_customer_counter(self, counter_discount, notes=""):
        self.ensure_one()
        self.portal_counter_discount = counter_discount
        self.portal_counter_notes = notes
        
        # Apply counter discount across lines
        for line in self.line_ids:
            line.discount = counter_discount
            line._compute_line_subtotal()
        self._compute_amounts()
        self.action_compute_blended_risk()

        self._create_approval_log('counter_proposed', f"Customer countered with {counter_discount}%: {notes}")
        if self.blended_risk_score > 0.0:
            self.write({
                'state': 'pending_manager',
                'approval_state': 'pending_manager'
            })
        else:
            self.write({
                'state': 'approved',
                'approval_state': 'approved'
            })

    def _create_approval_log(self, action, reason):
        self.env['dealflow.approval.log'].create({
            'quote_id': self.id,
            'user_id': self.env.user.id,
            'action': action,
            'reason': reason,
            'risk_score': self.blended_risk_score
        })


# Legacy shim
class HackathonItemFeatureA(models.Model):
    _inherit = 'hackathon.item'
    feature_a_score = fields.Float(string='Feature A Score')
