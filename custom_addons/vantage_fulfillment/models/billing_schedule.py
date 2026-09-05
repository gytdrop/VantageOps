from odoo import models, fields, api

from odoo.addons.vantage_core.models.vantage_config import CADENCE_SELECTION


class VantageBillingSchedule(models.Model):
    _name = 'vantage.billing.schedule'
    _description = 'Hybrid Deal Billing Schedule'
    _order = 'billing_date asc, sequence asc'

    order_id = fields.Many2one('sale.order', string='Sale Order', required=True, ondelete='cascade')
    source_line_id = fields.Many2one(
        'sale.order.line', string='Source Line', ondelete='set null',
        help="Subscription line this milestone was generated from."
    )
    sequence = fields.Integer(string='Seq', default=10)
    billing_date = fields.Date(string='Scheduled Invoice Date', required=True, default=fields.Date.context_today)
    description = fields.Char(string='Billing Description', required=True)
    amount = fields.Monetary(string='Period Amount', required=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='order_id.currency_id', store=True, readonly=True)
    billing_type = fields.Selection([
        ('one_time', 'One-Time Hardware / Setup'),
        ('recurring', 'Recurring SaaS / Subscription'),
        ('proration', 'Mid-Cycle Proration Adjustment'),
    ], string='Billing Category', default='recurring', required=True)
    state = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('invoiced', 'Invoiced'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='scheduled', required=True)

    # --- Cycle & proration audit trail ---
    cadence = fields.Selection(CADENCE_SELECTION, string='Cadence')
    period_start = fields.Date(string='Period Start')
    period_end = fields.Date(string='Period End')
    proration_factor = fields.Float(
        string='Proration Factor', digits=(12, 6), default=1.0,
        help="Fraction of the full cycle actually charged, computed on exact calendar days."
    )
    is_prorated = fields.Boolean(string='Prorated', default=False)
    proration_note = fields.Char(
        string='Proration Basis',
        help="Human-readable arithmetic behind a mid-cycle adjustment."
    )
    period_days = fields.Integer(string='Days Charged', compute='_compute_period_days')

    @api.depends('period_start', 'period_end')
    def _compute_period_days(self):
        for record in self:
            if record.period_start and record.period_end:
                record.period_days = (record.period_end - record.period_start).days + 1
            else:
                record.period_days = 0

    def action_mark_invoiced(self):
        for rec in self:
            rec.state = 'invoiced'
        return True

    def action_cancel_schedule(self):
        for rec in self:
            rec.state = 'cancelled'
        return True
